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
