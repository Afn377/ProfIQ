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

