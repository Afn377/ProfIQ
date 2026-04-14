"""Small Reddit helper used by the live professor detail view."""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

# Generic subs used after any school-specific subreddit.
DEFAULT_SUBREDDITS: tuple[str, ...] = ("college", "AskAcademia")

REQ_TIMEOUT = 8.0          # per-HTTP-call timeout
WALL_BUDGET_SECONDS = 14.0  # total wall budget across all calls
MIN_TEXT_LEN = 40           # filter out 1-line "lol" comments
MAX_POSTS_PER_SUB = 5       # only walk the first few search hits per sub


# School names that need an explicit subreddit.
INSTITUTION_SUBREDDITS: dict[str, str] = {
    "brigham young university": "BYU",
    "harvard university": "harvard",
    "yale university": "yale",
    "princeton university": "princeton",
    "columbia university": "columbia",
    "university of pennsylvania": "UPenn",
    "stanford university": "stanford",
    "massachusetts institute of technology": "mit",
    "california institute of technology": "Caltech",
    "university of california, berkeley": "berkeley",
    "university of california, los angeles": "ucla",
    "university of california, san diego": "UCSD",
    "university of california, davis": "UCDavis",
    "university of california, irvine": "UCI",
    "university of california, santa barbara": "UCSantaBarbara",
    "university of southern california": "USC",
    "new york university": "nyu",
    "cornell university": "Cornell",
    "duke university": "duke",
    "northwestern university": "NorthwesternU",
    "university of chicago": "uchicago",
    "university of michigan": "uofm",
    "michigan state university": "msu",
    "university of texas at austin": "UTAustin",
    "texas a&m university": "aggies",
    "university of washington": "udub",
    "university of wisconsin-madison": "UWMadison",
    "university of minnesota": "uofmn",
    "university of illinois at urbana-champaign": "UIUC",
    "purdue university": "Purdue",
    "indiana university": "IndianaUniversity",
    "ohio state university": "OSU",
    "pennsylvania state university": "PennStateUniversity",
    "rutgers - state university of new jersey": "rutgers",
    "boston university": "BostonU",
    "georgia institute of technology": "gatech",
    "university of georgia": "UGA",
    "university of florida": "ufl",
    "florida state university": "fsu",
    "university of north carolina at chapel hill": "UNC",
    "north carolina state university": "ncsu",
    "vanderbilt university": "VandyU",
    "university of virginia": "UVA",
    "virginia tech": "VirginiaTech",
    "university of maryland": "UMD",
    "rice university": "rice",
    "university of arizona": "UofArizona",
    "arizona state university": "ASU",
    "university of colorado boulder": "CUBoulder",
    "university of utah": "UofU",
    "utah state university": "USU",
    "university of oregon": "uoregon",
    "oregon state university": "OregonStateUniv",
    "carnegie mellon university": "cmu",
    "johns hopkins university": "jhu",
    "george washington university": "gwu",
    "university of notre dame": "notredame",
    "florida international university": "FIU",
    "university of central florida": "ucf",
    "rochester institute of technology": "rit",
    "drexel university": "Drexel",
    "temple university": "Temple",
    "university of pittsburgh": "Pitt",
    "university of cincinnati": "uofcincinnati",
    "university of houston": "UniversityOfHouston",
}


# Conservative first-name aliases for professor mention matching.
NICKNAME_MAP: dict[str, tuple[str, ...]] = {
    "alexander": ("alex", "lex", "xander"),
    "alexandra": ("alex", "ali", "sandra"),
    "andrew": ("andy", "drew"),
    "anthony": ("tony",),
    "benjamin": ("ben", "benny"),
    "catherine": ("kate", "cathy", "katie", "cat"),
    "charles": ("charlie", "chuck"),
    "christopher": ("chris", "topher"),
    "daniel": ("dan", "danny"),
    "david": ("dave", "davey"),
    "edward": ("ed", "eddie", "ted", "ned"),
    "elizabeth": ("liz", "beth", "betty", "lizzy", "eliza"),
    "frederick": ("fred", "freddie"),
    "gregory": ("greg",),
    "henry": ("hank", "harry"),
    "jacob": ("jake",),
    "james": ("jim", "jimmy", "jamie"),
    "jennifer": ("jen", "jenny", "jenn"),
    "joseph": ("joe", "joey"),
    "joshua": ("josh",),
    "kenneth": ("ken", "kenny"),
    "lawrence": ("larry",),
    "margaret": ("maggie", "meg", "peggy", "marge"),
    "matthew": ("matt", "matty"),
    "michael": ("mike", "mick", "mikey"),
    "nicholas": ("nick", "nicky"),
    "patricia": ("pat", "patty", "trisha"),
    "patrick": ("pat", "paddy"),
    "rebecca": ("becky", "becca"),
    "richard": ("rick", "rich", "dick"),
    "robert": ("rob", "bob", "bobby", "robbie"),
    "ronald": ("ron", "ronnie"),
    "russell": ("russ",),
    "samuel": ("sam", "sammy"),
    "stephen": ("steve", "stevie"),
    "steven": ("steve", "stevie"),
    "susan": ("sue", "susie"),
    "thomas": ("tom", "tommy"),
    "timothy": ("tim", "timmy"),
    "william": ("will", "bill", "billy", "willie", "liam"),
    "zachary": ("zach", "zack"),
}


_DEAD_BODIES = {"[deleted]", "[removed]", "[ deleted by user ]"}

# Abbreviations that should not end a sentence.
_ABBREVIATIONS: frozenset[str] = frozenset({
    "dr", "drs", "mr", "mrs", "ms", "mx", "prof", "profs", "sr", "jr",
    "ph", "phd", "vs", "etc", "inc", "ltd", "co", "u.s", "u.k", "i.e",
    "e.g", "a.m", "p.m", "no", "vol", "ch", "fig", "st", "mt",
})

# Temporary marker used while splitting sentences.
_ABBREV_SENTINEL = "\x00"


def _split_sentences(text: str) -> list[str]:
    """Split Reddit text without breaking common titles like Dr."""
    if not text:
        return []

    # Hide protected periods before the split.
    def _protect(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.casefold() in _ABBREVIATIONS:
            return token + _ABBREV_SENTINEL
        return match.group(0)

    protected = re.sub(r"\b([A-Za-z]{1,5}(?:\.[A-Za-z]{1,3})?)\.", _protect, text)

    # Keep paragraph breaks from creating empty fragments.
    protected = re.sub(r"\n{2,}", "\n", protected)

    # Split on sentence punctuation or line breaks.
    pieces = re.split(
        r"(?<=[.!?])\s+(?=[\"'\(\[A-Z0-9])|\n+",
        protected,
    )

    out: list[str] = []
    for piece in pieces:
        s = piece.replace(_ABBREV_SENTINEL, ".").strip()
        if s:
            out.append(s)
    return out


def _clean_body(text: str) -> str:
    if not text:
        return ""
    s = text.strip()
    if s.casefold() in _DEAD_BODIES:
        return ""
    s = re.sub(r"^\s*>\s?", "", s, flags=re.MULTILINE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _to_iso(ts) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


class _AliasMatcher:
    """Find sentences that mention the target professor."""

    # Titles students commonly use in posts.
    _TITLES = ("dr", "prof", "professor", "mr", "mrs", "ms", "mx")

    def __init__(
        self,
        name: str,
        institution: str | None = None,
        extra_aliases: Iterable[str] | None = None,
    ) -> None:
        full = (name or "").strip()
        parts = full.split()
        self.full = full
        self.first = parts[0] if parts else ""
        self.last = parts[-1] if len(parts) > 1 else ""
        # Kept for logging and future matching tweaks.
        self.institution = (institution or "").strip()

        first_lower = self.first.casefold()
        nicknames = list(NICKNAME_MAP.get(first_lower, ()))
        if extra_aliases:
            nicknames.extend(a.strip() for a in extra_aliases if a and a.strip())
        # Include the real first name along with nickname aliases.
        first_aliases: list[str] = []
        seen_aliases: set[str] = set()
        for candidate in [self.first, *nicknames]:
            key = candidate.casefold().strip()
            if key and key not in seen_aliases:
                seen_aliases.add(key)
                first_aliases.append(candidate)
        self.first_aliases = first_aliases

        self.patterns = self._build_patterns()

    def _build_patterns(self) -> list[re.Pattern[str]]:
        patterns: list[re.Pattern[str]] = []
        titles_alt = "|".join(self._TITLES)

        if self.full and " " in self.full:
            patterns.append(re.compile(
                rf"\b{re.escape(self.full)}\b", re.IGNORECASE,
            ))

        if self.last:
            last_re = re.escape(self.last)
            patterns.append(re.compile(rf"\b{last_re}\b", re.IGNORECASE))

            if self.first:
                # First initial plus last name.
                initial = re.escape(self.first[0])
                patterns.append(re.compile(
                    rf"\b{initial}\.?\s+{last_re}\b", re.IGNORECASE,
                ))

            for alias in self.first_aliases:
                if not alias:
                    continue
                a = re.escape(alias)
                # First name or nickname plus last name.
                patterns.append(re.compile(
                    rf"\b{a}\s+{last_re}\b", re.IGNORECASE,
                ))

        if self.first_aliases:
            alts = "|".join(re.escape(a) for a in self.first_aliases if a)
            if alts:
                # Title plus first name.
                patterns.append(re.compile(
                    rf"\b(?:{titles_alt})\.?\s+(?:{alts})\b",
                    re.IGNORECASE,
                ))

        return patterns

    def matches(self, text: str | None) -> bool:
        if not text:
            return False
        for pat in self.patterns:
            if pat.search(text):
                return True
        return False

    def select_sentences(self, text: str | None) -> list[str]:
        """Return only sentences that match this professor."""
        if not text:
            return []
        return [s for s in _split_sentences(text) if self.matches(s)]


def _institution_keyword(institution: str | None) -> str | None:
    """Pick one institution keyword for generic subreddit searches."""
    if not institution:
        return None
    cleaned = re.sub(
        r"\b(?:university|college|institute|school|of|the|state|community|technology|technical)\b",
        " ", institution, flags=re.I,
    )
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", cleaned)
    parts = [p for p in cleaned.split() if len(p) > 2]
    if not parts:
        return None
    return max(parts, key=len)


def _subreddits_for_institution(institution: str | None) -> list[str]:
    """Return school-specific subreddit first, then generic subs."""
    candidates: list[str] = []
    if institution:
        norm = institution.casefold().strip()
        # Prefer the longest configured school-name match.
        best_key: str | None = None
        for key in INSTITUTION_SUBREDDITS:
            if norm == key or norm.startswith(key + " ") or norm.startswith(key + ","):
                if best_key is None or len(key) > len(best_key):
                    best_key = key
        if best_key:
            candidates.append(INSTITUTION_SUBREDDITS[best_key])

    candidates.extend(DEFAULT_SUBREDDITS)
    # Keep order while removing duplicates.
    seen: set[str] = set()
    out: list[str] = []
    for sub in candidates:
        key = sub.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(sub)
    return out


def _query_for_sub(
    name: str,
    institution_kw: str | None,
    sub: str,
) -> str:
    """Build a Reddit search query for one subreddit."""
    last_name = name.rsplit(" ", 1)[-1].strip()
    is_generic = sub.casefold() in {s.casefold() for s in DEFAULT_SUBREDDITS}
    if is_generic:
        q = f'"{name}"'
        if institution_kw:
            q = f"{q} {institution_kw}"
        return q
    # School subs usually have enough context for last-name search.
    return last_name or name


def fetch_for_professor(
    name: str,
    institution: str | None = None,
    *,
    max_comments: int = 25,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    user_agent: str | None = None,
    deadline: float | None = None,
    extra_aliases: Iterable[str] | None = None,
) -> list[dict]:
    """Fetch a small batch of Reddit comments for one professor."""
    if not name or not name.strip():
        return []

    if deadline is None:
        deadline = time.monotonic() + WALL_BUDGET_SECONDS

    matcher = _AliasMatcher(name, institution, extra_aliases=extra_aliases)
    inst_kw = _institution_keyword(institution)

    # Use school-aware subreddit order unless the caller supplied one.
    if subreddits is DEFAULT_SUBREDDITS:
        subreddit_list = _subreddits_for_institution(institution)
    else:
        subreddit_list = list(subreddits)

    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent
        or os.environ.get("REDDIT_USER_AGENT", "profiq-lazy/0.1"),
    })

    out: list[dict] = []

    for sub in subreddit_list:
        if time.monotonic() >= deadline or len(out) >= max_comments:
            break
        query = _query_for_sub(name, inst_kw, sub)
        try:
            posts = _search(session, sub, query, deadline)
        except Exception as exc:
            logger.debug("Reddit lazy: search r/%s failed: %s", sub, exc)
            continue

        for post in posts[:MAX_POSTS_PER_SUB]:
            if time.monotonic() >= deadline or len(out) >= max_comments:
                break
            post_id = post.get("id") or ""
            permalink = post.get("permalink") or ""
            title = post.get("title") or ""
            selftext = post.get("selftext") or ""
            post_text = (title + "\n" + selftext).strip()
            post_url = (
                f"https://www.reddit.com{permalink}" if permalink else ""
            )

            # Keep only the title/body pieces that mention this professor.
            kept_lines: list[str] = []
            if matcher.matches(title):
                kept_lines.append(title.strip())
            kept_lines.extend(matcher.select_sentences(selftext))
            sliced_post = "\n".join(line for line in kept_lines if line).strip()

            if len(sliced_post) >= MIN_TEXT_LEN:
                out.append({
                    "text": _clean_body(sliced_post),
                    "source": "reddit",
                    "source_url": post_url,
                    "posted_at": _to_iso(post.get("created_utc")),
                })
                if len(out) >= max_comments:
                    break

            if not post_id:
                continue

            try:
                children = _fetch_comments(session, sub, post_id, deadline)
            except Exception as exc:
                logger.debug(
                    "Reddit lazy: comments fetch %s failed: %s", post_id, exc,
                )
                continue

            _walk(
                children,
                matcher=matcher,
                out=out,
                post_url=post_url,
                max_comments=max_comments,
                deadline=deadline,
            )

    return out[:max_comments]


def _search(
    session: requests.Session,
    sub: str,
    query: str,
    deadline: float,
) -> list[dict]:
    if time.monotonic() >= deadline:
        return []
    url = f"https://www.reddit.com/r/{sub}/search.json"
    params = {
        "q": query,
        "restrict_sr": 1,
        "limit": MAX_POSTS_PER_SUB * 2,
        "sort": "relevance",
        "t": "all",
    }
    timeout = min(REQ_TIMEOUT, max(1.0, deadline - time.monotonic()))
    resp = session.get(url, params=params, timeout=timeout)
    if resp.status_code == 429:
        logger.debug("Reddit lazy: 429 on search r/%s", sub)
        return []
    resp.raise_for_status()
    data = resp.json()
    children = (data.get("data") or {}).get("children") or []
    return [(c.get("data") or {}) for c in children]


def _fetch_comments(
    session: requests.Session,
    sub: str,
    post_id: str,
    deadline: float,
) -> list[dict]:
    if time.monotonic() >= deadline:
        return []
    url = f"https://www.reddit.com/r/{sub}/comments/{post_id}.json"
    timeout = min(REQ_TIMEOUT, max(1.0, deadline - time.monotonic()))
    resp = session.get(
        url, params={"limit": 200, "raw_json": 1}, timeout=timeout,
    )
    if resp.status_code == 429:
        return []
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list) or len(payload) < 2:
        return []
    return (payload[1].get("data") or {}).get("children") or []


def _walk(
    children: list[dict],
    *,
    matcher: _AliasMatcher,
    out: list[dict],
    post_url: str,
    max_comments: int,
    deadline: float,
    depth: int = 0,
    depth_limit: int = 8,
) -> None:
    """Walk comments and keep only professor-matching sentence slices."""
    if depth > depth_limit:
        return
    for c in children:
        if len(out) >= max_comments or time.monotonic() >= deadline:
            return
        if c.get("kind") != "t1":
            continue  # 'more' stub — can't expand without OAuth
        data = c.get("data") or {}
        body = _clean_body(data.get("body") or "")
        if body:
            relevant = matcher.select_sentences(body)
            sliced = " ".join(relevant).strip()
            if sliced and len(sliced) >= MIN_TEXT_LEN:
                c_permalink = data.get("permalink") or ""
                c_url = (
                    f"https://www.reddit.com{c_permalink}"
                    if c_permalink
                    else f"{post_url}{data.get('id', '')}/"
                )
                out.append({
                    "text": sliced,
                    "source": "reddit",
                    "source_url": c_url,
                    "posted_at": _to_iso(data.get("created_utc")),
                })
                if len(out) >= max_comments:
                    return
        replies = data.get("replies")
        if isinstance(replies, dict):
            sub_children = (replies.get("data") or {}).get("children") or []
            if sub_children:
                _walk(
                    sub_children,
                    matcher=matcher,
                    out=out,
                    post_url=post_url,
                    max_comments=max_comments,
                    deadline=deadline,
                    depth=depth + 1,
                    depth_limit=depth_limit,
                )
