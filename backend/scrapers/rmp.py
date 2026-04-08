"""RateMyProfessors GraphQL client."""
from __future__ import annotations

import base64

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
