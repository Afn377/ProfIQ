"""RateMyProfessors GraphQL client."""
from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Iterator

import requests

from .base import ScrapedProfessor, ScrapedReview, Throttle


def teacher_gid_from_legacy(legacy_id: int | str) -> str:
    """Encode an RMP numeric teacher ID as a Relay gid."""
    raw = f"Teacher-{legacy_id}".encode("ascii")
    return base64.b64encode(raw).decode("ascii")


def _normalize_rmp_date(raw: str | None) -> str | None:
    """Convert RMP timestamps to ISO-8601."""
    if not raw:
        return None
    s = raw.strip()
    # The timezone name is redundant with the numeric offset.
    s = re.sub(r"\s+UTC$", "", s)
    for fmt in (
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return None

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"
# Public token used by RMP's web client.
AUTH_HEADER = "Basic dGVzdDp0ZXN0"

DEFAULT_HEADERS = {
    "Authorization": AUTH_HEADER,
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.ratemyprofessors.com",
    "Referer": "https://www.ratemyprofessors.com/",
}

SCHOOL_SEARCH_QUERY = """
query NewSearchSchoolsQuery($query: SchoolSearchQuery!) {
  newSearch {
    schools(query: $query) {
      edges {
        node {
          id
          legacyId
          name
          city
          state
        }
      }
    }
  }
}
"""

SCHOOL_LIST_QUERY = """
query SchoolListQuery($query: SchoolSearchQuery!, $count: Int, $cursor: String) {
  newSearch {
    schools(query: $query, first: $count, after: $cursor) {
      edges {
        cursor
        node {
          id
          legacyId
          name
          city
          state
          country
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

TEACHER_SEARCH_QUERY = """
query NewSearchTeachersQuery($query: TeacherSearchQuery!, $count: Int) {
  newSearch {
    teachers(query: $query, first: $count) {
      edges {
        cursor
        node {
          id
          legacyId
          firstName
          lastName
          department
          school { name }
          avgRating
          numRatings
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

RATINGS_QUERY = """
query RatingsListQuery($id: ID!, $count: Int!, $cursor: String) {
  node(id: $id) {
    ... on Teacher {
      ratings(first: $count, after: $cursor) {
        edges {
          cursor
          node {
            id
            legacyId
            comment
            date
            class
            helpfulRating
            clarityRating
            difficultyRating
            wouldTakeAgain
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""


US_STATE_CODES = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR",
})

# Broad text queries used by :meth:`RMPClient.iter_schools` when discovering
# schools. RMP's schools endpoint requires a non-empty ``text`` so we cover
# the space by issuing a set of common institutional keywords.
_DISCOVERY_TEXTS = (
    "university", "college", "institute", "school", "state",
    "academy", "community", "technical", "polytechnic", "seminary",
)


@dataclass
class RMPSchool:
    gid: str
    legacy_id: int
    name: str
    city: str
    state: str
    country: str

    @property
    def is_us(self) -> bool:
        return self.state.upper() in US_STATE_CODES


@dataclass
class RMPTeacher:
    gid: str              # Relay-style GraphQL id (base64)
    legacy_id: int
    first_name: str
    last_name: str
    department: str
    school_name: str
    avg_rating: float | None
    num_ratings: int

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def profile_url(self) -> str:
        return f"https://www.ratemyprofessors.com/professor/{self.legacy_id}"


class RMPClient:
    """Thin GraphQL client with throttling, retries + single-session reuse."""

    # HTTP status codes we treat as transient and retry.
    _TRANSIENT_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        throttle_seconds: float = 1.0,
        timeout: int = 20,
        max_retries: int = 4,
    ) -> None:
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._throttle = Throttle(throttle_seconds)
        self._timeout = timeout
        self._max_retries = max_retries

    def _post(self, query: str, variables: dict) -> dict:
        """POST a GraphQL query with retry-on-transient-error.

        Retries up to ``self._max_retries`` times on connection errors,
        timeouts, or transient HTTP statuses (429/5xx). Backoff is
        exponential starting at 0.5s. Non-retryable failures (4xx other
        than 429, malformed JSON) raise immediately.
        """
        attempts = self._max_retries + 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            self._throttle.wait()
            try:
                resp = self._session.post(
                    GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                    timeout=self._timeout,
                )
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    delay = 0.5 * (2 ** attempt)
                    logger.info(
                        "RMP transient %s (attempt %d/%d) — sleeping %.1fs",
                        type(exc).__name__, attempt + 1, attempts, delay,
                    )
                    time.sleep(delay)
                    continue
                raise

            if resp.status_code in self._TRANSIENT_STATUSES and attempt < attempts - 1:
                delay = 0.5 * (2 ** attempt)
                logger.info(
                    "RMP HTTP %d (attempt %d/%d) — sleeping %.1fs",
                    resp.status_code, attempt + 1, attempts, delay,
                )
                time.sleep(delay)
                continue

            resp.raise_for_status()
            try:
                payload = resp.json()
            except ValueError as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                raise
            if "errors" in payload:
                logger.warning("GraphQL errors: %s", payload["errors"])
            return payload.get("data", {}) or {}

        # Loop only exits via ``return`` or raise; this is defensive.
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("RMP request retries exhausted")

    # ------------------------------------------------------------------ API

    def find_school_id(self, school_name: str) -> str | None:
        """Return the Relay school ID (or None) for the closest name match."""
        data = self._post(
            SCHOOL_SEARCH_QUERY,
            {"query": {"text": school_name}},
        )
        edges = (
            data.get("newSearch", {})
            .get("schools", {})
            .get("edges", [])
        )
        if not edges:
            return None
        target = school_name.casefold()
        for e in edges:
            node = e.get("node") or {}
            if node.get("name", "").casefold() == target:
                return node["id"]
        return edges[0]["node"]["id"]

    def search_teachers(
        self,
        school_id: str,
        text: str = "",
        limit: int = 20,
    ) -> list[RMPTeacher]:
        data = self._post(
            TEACHER_SEARCH_QUERY,
            {
                "query": {"text": text, "schoolID": school_id},
                "count": limit,
            },
        )
        edges = (
            data.get("newSearch", {})
            .get("teachers", {})
            .get("edges", [])
        )
        result: list[RMPTeacher] = []
        for e in edges:
            n = e.get("node") or {}
            result.append(RMPTeacher(
                gid=n.get("id", ""),
                legacy_id=n.get("legacyId") or 0,
                first_name=n.get("firstName", ""),
                last_name=n.get("lastName", ""),
                department=n.get("department", "") or "",
                school_name=(n.get("school") or {}).get("name", ""),
                avg_rating=n.get("avgRating"),
                num_ratings=n.get("numRatings") or 0,
            ))
        return result

    def iter_schools(
        self,
        texts: Iterable[str] = _DISCOVERY_TEXTS,
        page_size: int = 100,
        us_only: bool = True,
    ) -> Iterator[RMPSchool]:
        """Yield schools matching a set of broad discovery queries.

        RMP's schools endpoint requires a non-empty ``text`` so we rotate
        through ``_DISCOVERY_TEXTS`` (``"university"``, ``"college"`` etc.) to
        cover the space. Duplicates are suppressed by school ID. When
        ``us_only`` is True, results are filtered by state-abbreviation.
        """
        seen: set[str] = set()
        for text in texts:
            cursor = None
            while True:
                data = self._post(
                    SCHOOL_LIST_QUERY,
                    {
                        "query": {"text": text},
                        "count": page_size,
                        "cursor": cursor,
                    },
                )
                schools = (data.get("newSearch") or {}).get("schools") or {}
                edges = schools.get("edges") or []
                if not edges:
                    break
                for e in edges:
                    n = e.get("node") or {}
                    gid = n.get("id") or ""
                    if not gid or gid in seen:
                        continue
                    seen.add(gid)
                    school = RMPSchool(
                        gid=gid,
                        legacy_id=n.get("legacyId") or 0,
                        name=n.get("name") or "",
                        city=n.get("city") or "",
                        state=(n.get("state") or "").strip(),
                        country=n.get("country") or "",
                    )
                    if us_only and not school.is_us:
                        continue
                    yield school
                page_info = schools.get("pageInfo") or {}
                if not page_info.get("hasNextPage"):
                    break
                cursor = page_info.get("endCursor")

    def iter_teachers_all(
        self,
        school_id: str,
        page_size: int = 1000,
        max_teachers: int | None = None,
    ) -> Iterator[RMPTeacher]:
        """Yield every teacher at ``school_id``, paginating until exhausted."""
        cursor = None
        fetched = 0
        while True:
            data = self._post(
                """
                query BulkTeachersQuery(
                    $query: TeacherSearchQuery!,
                    $count: Int,
                    $cursor: String
                ) {
                  newSearch {
                    teachers(query: $query, first: $count, after: $cursor) {
                      edges {
                        cursor
                        node {
                          id
                          legacyId
                          firstName
                          lastName
                          department
                          school { name }
                          avgRating
                          numRatings
                        }
                      }
                      pageInfo { hasNextPage endCursor }
                    }
                  }
                }
                """,
                {
                    "query": {"text": "", "schoolID": school_id},
                    "count": page_size,
                    "cursor": cursor,
                },
            )
            teachers = (data.get("newSearch") or {}).get("teachers") or {}
            edges = teachers.get("edges") or []
            if not edges:
                return
            for e in edges:
                n = e.get("node") or {}
                yield RMPTeacher(
                    gid=n.get("id", ""),
                    legacy_id=n.get("legacyId") or 0,
                    first_name=n.get("firstName", "") or "",
                    last_name=n.get("lastName", "") or "",
                    department=(n.get("department") or "").strip(),
                    school_name=(n.get("school") or {}).get("name", "") or "",
                    avg_rating=n.get("avgRating"),
                    num_ratings=n.get("numRatings") or 0,
                )
                fetched += 1
                if max_teachers and fetched >= max_teachers:
                    return
            page_info = teachers.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                return
            cursor = page_info.get("endCursor")

    def iter_ratings(
        self,
        teacher_gid: str,
        page_size: int = 20,
        max_reviews: int | None = None,
    ) -> Iterator[dict]:
        cursor = None
        fetched = 0
        while True:
            data = self._post(
                RATINGS_QUERY,
                {"id": teacher_gid, "count": page_size, "cursor": cursor},
            )
            node = (data.get("node") or {})
            ratings = node.get("ratings") or {}
            edges = ratings.get("edges") or []
            if not edges:
                return
            for e in edges:
                yield e.get("node") or {}
                fetched += 1
                if max_reviews and fetched >= max_reviews:
                    return
            page_info = ratings.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                return
            cursor = page_info.get("endCursor")

    def fetch_ratings_page(
        self,
        teacher_gid: str,
        cursor: str | None = None,
        count: int = 25,
    ) -> tuple[list[dict], str | None, bool]:
        """Fetch a single page of ratings for ``teacher_gid``.

        Returns ``(nodes, next_cursor, has_more)``. Used by the live
        review-fetch endpoint so the client can thread cursor state for
        infinite-scroll pagination.
        """
        data = self._post(
            RATINGS_QUERY,
            {"id": teacher_gid, "count": count, "cursor": cursor},
        )
        node = (data.get("node") or {})
        ratings = node.get("ratings") or {}
        edges = ratings.get("edges") or []
        page_info = ratings.get("pageInfo") or {}
        nodes = [e.get("node") or {} for e in edges]
        next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None
        return nodes, next_cursor, bool(page_info.get("hasNextPage"))


# ---------------------------------------------------------------------------
# High-level scrape function


def scrape_rmp(
    school_name: str,
    teacher_names: Iterable[str] | None = None,
    max_teachers: int = 10,
    max_reviews_per_teacher: int = 30,
    throttle_seconds: float = 1.0,
) -> tuple[list[ScrapedProfessor], list[ScrapedReview]]:
    """Scrape RMP for professors at ``school_name``.

    - If ``teacher_names`` is provided, one search is issued per name (more
      precise).
    - Otherwise the top ``max_teachers`` teachers at the school are fetched.
    """
    client = RMPClient(throttle_seconds=throttle_seconds)
    school_id = client.find_school_id(school_name)
    if not school_id:
        raise RuntimeError(f"No RMP school found matching: {school_name!r}")

    teachers: list[RMPTeacher] = []
    if teacher_names:
        seen: set[int] = set()
        for name in teacher_names:
            for t in client.search_teachers(school_id, text=name, limit=5):
                if t.legacy_id in seen:
                    continue
                # Keep only reasonably close name matches
                hay = (t.full_name or "").casefold()
                needle = name.casefold()
                if needle in hay or hay in needle:
                    seen.add(t.legacy_id)
                    teachers.append(t)
    else:
        teachers = client.search_teachers(school_id, text="", limit=max_teachers)

    profs: list[ScrapedProfessor] = []
    reviews: list[ScrapedReview] = []

    for t in teachers:
        profs.append(ScrapedProfessor(
            name=t.full_name,
            institution=t.school_name or school_name,
            department=t.department,
            bio=(
                f"Listed on RateMyProfessors with {t.num_ratings} ratings"
                + (f" · avg {t.avg_rating:.1f}" if t.avg_rating else "")
            ),
            courses=[],
        ))
        for rating in client.iter_ratings(
            t.gid, max_reviews=max_reviews_per_teacher
        ):
            comment = (rating.get("comment") or "").strip()
            if not comment:
                continue
            course_code = (rating.get("class") or "").strip()
            reviews.append(ScrapedReview(
                professor=t.full_name,
                source="RateMyProfessors",
                text=comment,
                source_url=(
                    f"{t.profile_url}#rating-{rating.get('legacyId')}"
                    if rating.get("legacyId") else t.profile_url
                ),
                rating=_quality_rating(rating),
                course=course_code,
                posted_at=_normalize_rmp_date(rating.get("date")),
            ))
    return profs, reviews


def _quality_rating(rating: dict) -> float | None:
    """RMP doesn't expose a single 1–5 overall in this query; approximate
    using the average of helpful + clarity (and subtract difficulty nothing).
    """
    helpful = rating.get("helpfulRating")
    clarity = rating.get("clarityRating")
    vals = [v for v in (helpful, clarity) if isinstance(v, (int, float))]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)
