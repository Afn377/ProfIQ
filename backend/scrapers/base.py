"""Shared pieces for scrapers: throttling and plain record types."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


class Throttle:
    """Enforce a minimum gap between calls to ``wait()``.

    Uses ``time.monotonic()`` so a wall-clock change can't confuse it.
    """

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self._last: float | None = None

    def wait(self) -> None:
        if self._last is not None:
            elapsed = time.monotonic() - self._last
            remaining = self.seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last = time.monotonic()


@dataclass
class ScrapedProfessor:
    name: str
    institution: str
    department: str = ""
    bio: str = ""
    courses: list[str] = field(default_factory=list)


@dataclass
class ScrapedReview:
    professor: str
    source: str
    text: str
    source_url: str = ""
    rating: float | None = None
    course: str = ""
    posted_at: str | None = None
