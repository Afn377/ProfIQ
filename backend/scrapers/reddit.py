"""Reddit scraper used for optional seed-data collection."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import requests

from .base import ScrapedProfessor, ScrapedReview, Throttle

logger = logging.getLogger(__name__)

# Ignore tiny comments with no useful review signal.
MIN_TEXT_LEN = 40
# Longer posts are treated as mixed-topic.
SHORT_POST_CHAR_LIMIT = 400


def _should_cascade_trust(
    post_title: str,
    post_selftext: str,
    matcher: "_NameMatcher",
) -> bool:
    """Return True when replies can inherit the post-level match."""
    if matcher.matches(post_title):
        return True
    if matcher.matches(post_selftext) and len(post_selftext) < SHORT_POST_CHAR_LIMIT:
        return True
    return False


@dataclass(frozen=True)
class _NameMatcher:
    full_lower: str
    last_lower: str

    @classmethod
    def for_name(cls, name: str) -> "_NameMatcher":
        return cls(
            full_lower=name.casefold(),
            last_lower=name.rsplit(" ", 1)[-1].casefold(),
        )

    def matches(self, text: str) -> bool:
        if not text:
            return False
        hay = text.casefold()
        if self.full_lower and self.full_lower in hay:
            return True
        if self.last_lower and re.search(rf"\b{re.escape(self.last_lower)}\b", hay):
            return True
        return False


def scrape_reddit(
    professors: Iterable[ScrapedProfessor],
    subreddits: Iterable[str],
    per_query_limit: int = 25,
    include_comments: bool = True,
    max_comments_per_post: int = 60,
    throttle_seconds: float = 1.5,
) -> list[ScrapedReview]:
    """Search Reddit posts and comments for professor mentions."""
    subreddits = list(subreddits)
    professors = list(professors)

    reviews: list[ScrapedReview] = []
    client = _try_make_praw_client()

    if client is not None:
        logger.info("Using PRAW (authenticated Reddit API)")
        reviews.extend(
            _scrape_via_praw(
                client, professors, subreddits,
                per_query_limit=per_query_limit,
                include_comments=include_comments,
                max_comments_per_post=max_comments_per_post,
            )
        )
    else:
        logger.info("PRAW creds not found — falling back to public JSON API")
        reviews.extend(
            _scrape_via_http(
                professors, subreddits,
                per_query_limit=per_query_limit,
                include_comments=include_comments,
                max_comments_per_post=max_comments_per_post,
                throttle_seconds=throttle_seconds,
            )
        )
    return reviews


def _try_make_praw_client():
    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and csec):
        return None
    try:
        import praw  # type: ignore
    except ImportError:
        logger.warning("praw is not installed — falling back to public API")
        return None

    user_agent = os.environ.get("REDDIT_USER_AGENT", "profiq/0.1 by unknown")
    return praw.Reddit(
        client_id=cid,
        client_secret=csec,
        user_agent=user_agent,
        check_for_async=False,
    )


