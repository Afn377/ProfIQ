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


def _scrape_via_praw(
    reddit,
    professors: list[ScrapedProfessor],
    subreddits: list[str],
    per_query_limit: int,
    include_comments: bool,
    max_comments_per_post: int,
) -> list[ScrapedReview]:
    out: list[ScrapedReview] = []
    for prof in professors:
        matcher = _NameMatcher.for_name(prof.name)
        query = f'"{prof.name}"'

        for sub in subreddits:
            try:
                submissions = reddit.subreddit(sub).search(
                    query, limit=per_query_limit, sort="relevance",
                )
            except Exception as exc:
                logger.warning("Reddit search failed in r/%s: %s", sub, exc)
                continue

            for s in submissions:
                title = s.title or ""
                selftext = s.selftext or ""
                post_text = (title + "\n" + selftext).strip()
                post_mentions = matcher.matches(post_text)
                cascade = _should_cascade_trust(title, selftext, matcher)
                permalink = f"https://www.reddit.com{s.permalink}"

                if post_mentions and len(post_text) >= MIN_TEXT_LEN:
                    out.append(ScrapedReview(
                        professor=prof.name,
                        source="Reddit",
                        text=_clean_body(post_text),
                        source_url=permalink,
                        posted_at=_to_iso(getattr(s, "created_utc", None)),
                    ))

                if not include_comments:
                    continue

                try:
                    s.comments.replace_more(limit=0)
                    forest = list(s.comments)
                except Exception as exc:
                    logger.warning("failed to load comments for %s: %s", s.id, exc)
                    continue

                budget = [max_comments_per_post]
                _walk_praw_forest(
                    forest, matcher,
                    chain_mentioned=cascade,
                    budget=budget,
                    out=out,
                    prof_name=prof.name,
                    post_permalink=permalink,
                )
    return out


def _walk_praw_forest(
    forest,
    matcher: _NameMatcher,
    chain_mentioned: bool,
    budget: list[int],
    out: list[ScrapedReview],
    prof_name: str,
    post_permalink: str,
    depth: int = 0,
    depth_limit: int = 10,
) -> None:
    """Walk a PRAW comment tree."""
    if depth > depth_limit:
        return
    for c in forest:
        if budget[0] <= 0:
            return
        # Skip MoreComments-like objects.
        body = _clean_body(getattr(c, "body", "") or "")
        direct = matcher.matches(body)
        here_in_ctx = chain_mentioned or direct
        if here_in_ctx and body and len(body) >= MIN_TEXT_LEN:
            out.append(ScrapedReview(
                professor=prof_name,
                source="Reddit",
                text=body,
                source_url=f"{post_permalink}{getattr(c, 'id', '')}/",
                posted_at=_to_iso(getattr(c, "created_utc", None)),
            ))
            budget[0] -= 1
        replies = getattr(c, "replies", None)
        if replies:
            _walk_praw_forest(
                list(replies), matcher, here_in_ctx, budget, out,
                prof_name, post_permalink, depth + 1, depth_limit,
            )


# ---------------------------------------------------------------------------
# Public JSON fallback path


def _scrape_via_http(
    professors: list[ScrapedProfessor],
    subreddits: list[str],
    per_query_limit: int,
    include_comments: bool,
    max_comments_per_post: int,
    throttle_seconds: float,
) -> list[ScrapedReview]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": os.environ.get(
            "REDDIT_USER_AGENT", "profiq/0.1 (research script)"
        ),
    })
    throttle = Throttle(throttle_seconds)
    out: list[ScrapedReview] = []

    for prof in professors:
        matcher = _NameMatcher.for_name(prof.name)
        query = f'"{prof.name}"'

        for sub in subreddits:
            posts = _http_search(session, throttle, sub, query, per_query_limit)
            if posts is None:
                continue

            for post in posts:
                post_id = post.get("id") or ""
                permalink = post.get("permalink") or ""
                title = post.get("title") or ""
                selftext = post.get("selftext") or ""
                post_text = (title + "\n" + selftext).strip()
                post_mentions = matcher.matches(post_text)
                cascade = _should_cascade_trust(title, selftext, matcher)
                post_url = (
                    f"https://www.reddit.com{permalink}" if permalink else ""
                )

                if post_mentions and len(post_text) >= MIN_TEXT_LEN:
                    out.append(ScrapedReview(
                        professor=prof.name,
                        source="Reddit",
                        text=_clean_body(post_text),
                        source_url=post_url,
                        posted_at=_to_iso(post.get("created_utc")),
                    ))

                if not include_comments or not post_id:
                    continue

                top_children = _http_fetch_comment_forest(
                    session, throttle, sub, post_id,
                )
                if not top_children:
                    continue

                budget = [max_comments_per_post]
                _walk_http_forest(
                    top_children, matcher,
                    chain_mentioned=cascade,
                    budget=budget,
                    out=out,
                    prof_name=prof.name,
                    post_url=post_url,
                )
    return out


def _walk_http_forest(
    children: list[dict],
    matcher: _NameMatcher,
    chain_mentioned: bool,
    budget: list[int],
    out: list[ScrapedReview],
    prof_name: str,
    post_url: str,
    depth: int = 0,
    depth_limit: int = 10,
) -> None:
    """Walk raw Reddit JSON comments."""
    if depth > depth_limit:
        return
    for c in children:
        if budget[0] <= 0:
            return
        if c.get("kind") != "t1":
            # Skip unexpanded placeholders.
            continue
        data = c.get("data") or {}
        body = _clean_body(data.get("body") or "")
        direct = matcher.matches(body)
        here_in_ctx = chain_mentioned or direct
        if here_in_ctx and body and len(body) >= MIN_TEXT_LEN:
            c_permalink = data.get("permalink") or ""
            c_url = (
                f"https://www.reddit.com{c_permalink}"
                if c_permalink else
                f"{post_url}{data.get('id', '')}/"
            )
            out.append(ScrapedReview(
                professor=prof_name,
                source="Reddit",
                text=body,
                source_url=c_url,
                posted_at=_to_iso(data.get("created_utc")),
            ))
            budget[0] -= 1
        replies = data.get("replies")
        if isinstance(replies, dict):
            sub_children = (replies.get("data") or {}).get("children") or []
            if sub_children:
                _walk_http_forest(
                    sub_children, matcher, here_in_ctx, budget, out,
                    prof_name, post_url, depth + 1, depth_limit,
                )


def _http_search(
    session: requests.Session,
    throttle: Throttle,
    sub: str,
    query: str,
    limit: int,
) -> list[dict] | None:
    url = f"https://www.reddit.com/r/{sub}/search.json"
    params = {
        "q": query,
        "restrict_sr": 1,
        "limit": limit,
        "sort": "relevance",
        "t": "all",
    }
    throttle.wait()
    try:
        resp = session.get(url, params=params, timeout=20)
        if resp.status_code == 429:
            logger.warning("Reddit rate-limited (429) on search r/%s", sub)
            return None
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("HTTP error searching r/%s: %s", sub, exc)
        return None

    children = (data.get("data") or {}).get("children") or []
    return [(c.get("data") or {}) for c in children]


def _http_fetch_comment_forest(
    session: requests.Session,
    throttle: Throttle,
    sub: str,
    post_id: str,
) -> list[dict]:
    """Fetch raw comment children for one post."""
    url = f"https://www.reddit.com/r/{sub}/comments/{post_id}.json"
    throttle.wait()
    try:
        resp = session.get(url, params={"limit": 500, "raw_json": 1}, timeout=25)
        if resp.status_code == 429:
            logger.warning("Reddit rate-limited (429) on comments %s", post_id)
            return []
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("HTTP error fetching comments %s: %s", post_id, exc)
        return []

    if not isinstance(payload, list) or len(payload) < 2:
        return []
    # Second listing contains comments.
    return (payload[1].get("data") or {}).get("children") or []


_DEAD_BODIES = {"[deleted]", "[removed]", "[ deleted by user ]"}


def _clean_body(text: str) -> str:
    """Normalize a Reddit comment body."""
    if not text:
        return ""
    stripped = text.strip()
    if stripped.casefold() in _DEAD_BODIES:
        return ""
    # Strip leading markdown quote markers.
    stripped = re.sub(r"^\s*>\s?", "", stripped, flags=re.MULTILINE)
    # Collapse long blank sections.
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped.strip()


def _to_iso(ts) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None
