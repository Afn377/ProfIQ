"""RateMyProfessors GraphQL client."""
from __future__ import annotations

import base64
import logging
import time

import requests

from .base import Throttle

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"

# RMP's server rejects python-requests' default User-Agent with a 403; a
# browser-looking one is the only header that was actually required.
# The Basic token is what the site's own JS sends (it decodes to "test:test").
DEFAULT_HEADERS = {
    "Authorization": "Basic dGVzdDp0ZXN0",
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def teacher_gid_from_legacy(legacy_id: int | str) -> str:
    """Turn RMP's numeric teacher id into the Relay gid its GraphQL API uses.

    RMP shows ``/professor/12345`` in URLs but its API wants
    ``base64("Teacher-12345")``. We store the small number and compute this.
    """
    raw = f"Teacher-{legacy_id}".encode("ascii")
    return base64.b64encode(raw).decode("ascii")


SCHOOL_SEARCH_QUERY = """
query ($query: SchoolSearchQuery!) {
  newSearch {
    schools(query: $query) {
      edges { node { id legacyId name city state } }
    }
  }
}
"""

TEACHERS_QUERY = """
query ($query: TeacherSearchQuery!, $count: Int, $cursor: String) {
  newSearch {
    teachers(query: $query, first: $count, after: $cursor) {
      edges { node { id legacyId firstName lastName department school { name } avgRating numRatings } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

RATINGS_QUERY = """
query ($id: ID!, $count: Int!, $cursor: String) {
  node(id: $id) {
    ... on Teacher {
      ratings(first: $count, after: $cursor) {
        edges {
          node { id legacyId comment date class helpfulRating clarityRating difficultyRating }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""


class RMPClient:
    """Thin GraphQL client with throttling and one reused session."""

    # Worth retrying: the server might answer differently in a moment.
    _TRANSIENT = frozenset({429, 500, 502, 503, 504})

    def __init__(self, throttle_seconds: float = 1.0, timeout: int = 20, max_retries: int = 4) -> None:
        self._session = requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)
        self._throttle = Throttle(throttle_seconds)
        self._timeout = timeout
        self._max_retries = max_retries

    def _post(self, query: str, variables: dict) -> dict:
        """POST a query, retrying transient failures with exponential backoff.

        Connection errors, timeouts and 429/5xx get retried with waits of
        0.5s, 1s, 2s, 4s. Anything else (400, 403, 404...) raises at once.
        """
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            self._throttle.wait()
            try:
                resp = self._session.post(
                    GRAPHQL_URL,
                    json={"query": query, "variables": variables},
                    timeout=self._timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == attempts - 1:
                    raise
                delay = 0.5 * (2 ** attempt)
                logger.info("RMP %s, retrying in %.1fs", type(exc).__name__, delay)
                time.sleep(delay)
                continue

            if resp.status_code in self._TRANSIENT and attempt < attempts - 1:
                delay = 0.5 * (2 ** attempt)
                logger.info("RMP HTTP %d, retrying in %.1fs", resp.status_code, delay)
                time.sleep(delay)
                continue

            resp.raise_for_status()
            return resp.json().get("data", {}) or {}
        raise RuntimeError("unreachable")

    def find_school_id(self, school_name: str) -> str | None:
        data = self._post(SCHOOL_SEARCH_QUERY, {"query": {"text": school_name}})
        edges = data.get("newSearch", {}).get("schools", {}).get("edges", [])
        if not edges:
            return None
        for e in edges:
            if e["node"]["name"].casefold() == school_name.casefold():
                return e["node"]["id"]
        return edges[0]["node"]["id"]

    def iter_ratings(self, teacher_gid: str, page_size: int = 20, max_reviews: int | None = None):
        """Yield one rating dict at a time, fetching pages as needed.

        Follows RMP's cursor: each page says whether there is a next one and
        where it starts. The caller just iterates; the paging is invisible.
        """
        cursor = None
        fetched = 0
        while True:
            data = self._post(RATINGS_QUERY, {"id": teacher_gid, "count": page_size, "cursor": cursor})
            ratings = (data.get("node") or {}).get("ratings") or {}
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

    def iter_teachers(self, school_id: str, page_size: int = 100, max_teachers: int | None = None,
                      start_cursor: str | None = None, on_page=None):
        """Yield every teacher at a school, paging with the cursor.

        ``start_cursor`` resumes from a saved position. ``on_page(cursor)`` is
        called after each page with the cursor that a later run should resume
        from, so the caller can checkpoint.
        """
        cursor = start_cursor
        fetched = 0
        while True:
            data = self._post(TEACHERS_QUERY, {"query": {"text": "", "schoolID": school_id}, "count": page_size, "cursor": cursor})
            teachers = (data.get("newSearch") or {}).get("teachers") or {}
            edges = teachers.get("edges") or []
            if not edges:
                return
            for e in edges:
                n = e.get("node") or {}
                first = (n.get("firstName") or "").strip()
                if not any(c.isalnum() for c in first):
                    first = ""   # rmp sometimes stores "." as a placeholder first name
                yield {
                    "legacy_id": n.get("legacyId") or 0,
                    "name": f"{first} {(n.get('lastName') or '').strip()}".strip(),
                    "department": (n.get("department") or "").strip(),
                    "school": (n.get("school") or {}).get("name", ""),
                    "avg_rating": n.get("avgRating"),
                    "num_ratings": n.get("numRatings") or 0,
                }
                fetched += 1
                if max_teachers and fetched >= max_teachers:
                    return
            page_info = teachers.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                if on_page:
                    on_page(None)   # done: nothing to resume from
                return
            cursor = page_info.get("endCursor")
            if on_page:
                on_page(cursor)
