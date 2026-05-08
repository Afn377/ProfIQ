"""Shared helpers used by the scrape_* management commands."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from django.core.management import call_command

from scrapers.base import write_json


def timestamped_output(name: str) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).resolve().parents[3] / "data" / "scraped"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{name}_{stamp}.json"


def dump_and_maybe_ingest(
    command, payload: dict, out_path: Path, ingest: bool,
) -> None:
    write_json(out_path, payload)
    command.stdout.write(command.style.SUCCESS(
        f"Wrote {sum(len(p['reviews']) for p in payload['professors'])} "
        f"reviews across {len(payload['professors'])} professors → {out_path}"
    ))
    if ingest:
        command.stdout.write("Ingesting into the database…")
        call_command("ingest_seed", path=str(out_path))
