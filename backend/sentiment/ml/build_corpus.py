"""Build the review corpus used by ML training scripts."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Allow running as a plain script from the backend/ dir
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "recommender.settings")
django.setup()

import pandas as pd
from django.db.models import Count

from professors.models import Professor
from scrapers.rmp import RMPClient, teacher_gid_from_legacy

logger = logging.getLogger("build_corpus")


@dataclass(frozen=True)
class TargetProf:
    legacy_id: int
    name: str
    institution: str
    department: str
    source_num_ratings: int

    @property
    def gid(self) -> str:
        return teacher_gid_from_legacy(self.legacy_id)


def select_targets(
    schools: int,
    profs_per_school: int,
) -> list[TargetProf]:
    """Pick high-review professors from the largest schools.

    Only includes profs with ``external_ref`` matching ``rmp:<id>`` (so we
    can derive the GraphQL teacher gid) and ``source_num_ratings >= 5``
    (otherwise the rating page returns very little).
    """
    top_schools = (
        Professor.objects
        .filter(external_ref__startswith="rmp:", source_num_ratings__gte=5)
        .values("institution")
        .annotate(n=Count("id"))
        .order_by("-n")[:schools]
    )

    targets: list[TargetProf] = []
    for row in top_schools:
        inst = row["institution"]
        qs = (
            Professor.objects
            .filter(
                institution=inst,
                external_ref__startswith="rmp:",
                source_num_ratings__gte=5,
            )
            .order_by("-source_num_ratings")[:profs_per_school]
            .values(
                "external_ref", "name", "institution",
                "department__name", "source_num_ratings",
            )
        )
        for p in qs:
            ref = p["external_ref"]
            try:
                legacy = int(ref.split(":", 1)[1])
            except (ValueError, IndexError):
                continue
            targets.append(TargetProf(
                legacy_id=legacy,
                name=p["name"],
                institution=p["institution"],
                department=p["department__name"] or "",
                source_num_ratings=p["source_num_ratings"],
            ))
    return targets


def _quality_rating(rating: dict) -> float | None:
    """Average helpful + clarity to a 1-5 score (RMP doesn't expose a single overall)."""
    helpful = rating.get("helpfulRating")
    clarity = rating.get("clarityRating")
    vals = [v for v in (helpful, clarity) if isinstance(v, (int, float))]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def fetch_one(
    client: RMPClient,
    target: TargetProf,
    reviews_per_prof: int,
) -> list[dict]:
    rows: list[dict] = []
    try:
        for r in client.iter_ratings(target.gid, max_reviews=reviews_per_prof):
            text = (r.get("comment") or "").strip()
            if not text:
                continue
            rating = _quality_rating(r)
            if rating is None:
                continue
            rows.append({
                "professor_id_external": f"rmp:{target.legacy_id}",
                "professor_name": target.name,
                "institution": target.institution,
                "department": target.department,
                "course": (r.get("class") or "").strip(),
                "text": text,
                "rating": rating,
                "would_take_again": r.get("wouldTakeAgain"),
                "difficulty": r.get("difficultyRating"),
                "posted_at": r.get("date") or "",
                "source_url": (
                    f"https://www.ratemyprofessors.com/professor/"
                    f"{target.legacy_id}#rating-{r.get('legacyId')}"
                ),
            })
    except Exception as exc:
        logger.warning("scrape failed for %s (%s): %s",
                       target.name, target.legacy_id, exc)
    return rows


def load_checkpoint(path: Path) -> set[int]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text()).get("done", []))
    except Exception:
        return set()


def save_checkpoint(path: Path, done: set[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"done": sorted(done)}))


def write_partial(out: Path, rows: list[dict]) -> None:
    """Append rows to the JSONL sidecar."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def jsonl_to_parquet(jsonl: Path, parquet: Path) -> int:
    rows = []
    if jsonl.exists():
        with jsonl.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["source_url"]).reset_index(drop=True)
    parquet.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(parquet, index=False)
    return len(df)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--schools", type=int, default=40)
    p.add_argument("--profs-per-school", type=int, default=40)
    p.add_argument("--reviews-per-prof", type=int, default=50)
    p.add_argument("--throttle", type=float, default=0.4)
    p.add_argument("--out", type=Path, default=Path("data/ml/corpus.parquet"))
    p.add_argument("--jsonl", type=Path, default=Path("data/ml/corpus.jsonl"))
    p.add_argument("--checkpoint", type=Path, default=Path("data/ml/corpus_checkpoint.json"))
    p.add_argument("--resume", action="store_true")
    p.add_argument("--target-reviews", type=int, default=0,
                   help="Stop early once this many rows have been collected (0=disabled)")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    print(f"[corpus] selecting {args.profs_per_school} profs from "
          f"{args.schools} schools", flush=True)
    targets = select_targets(args.schools, args.profs_per_school)
    print(f"[corpus] selected {len(targets)} target professors", flush=True)

    done = load_checkpoint(args.checkpoint) if args.resume else set()
    if not args.resume and args.jsonl.exists():
        # Fresh run: clear old partial output.
        args.jsonl.unlink()

    client = RMPClient(throttle_seconds=args.throttle)

    total_rows = 0
    if args.resume and args.jsonl.exists():
        # Count existing rows for progress output.
        with args.jsonl.open("r", encoding="utf-8") as fh:
            total_rows = sum(1 for _ in fh)
    print(f"[corpus] resuming with {len(done)} profs done, {total_rows} rows in JSONL",
          flush=True)

    started = time.time()
    for i, t in enumerate(targets, 1):
        if t.legacy_id in done:
            continue
        rows = fetch_one(client, t, args.reviews_per_prof)
        if rows:
            write_partial(args.jsonl, rows)
            total_rows += len(rows)
        done.add(t.legacy_id)
        save_checkpoint(args.checkpoint, done)

        if i % 10 == 0 or i == len(targets):
            elapsed = time.time() - started
            rate = i / elapsed if elapsed > 0 else 0
            print(f"[corpus] {i}/{len(targets)} profs scraped "
                  f"| {total_rows} rows | {rate:.1f} profs/s "
                  f"| elapsed {elapsed/60:.1f}m",
                  flush=True)

        if args.target_reviews and total_rows >= args.target_reviews:
            print(f"[corpus] hit target {args.target_reviews}, stopping early",
                  flush=True)
            break

    n = jsonl_to_parquet(args.jsonl, args.out)
    print(f"[corpus] DONE - wrote {n} unique rows to {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
