"""Remove high-confidence placeholder professor records."""
from __future__ import annotations

import logging
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from professors.canary_data import (
    BORDERLINE_FICTIONAL,
    FICTIONAL_INSTITUTIONS,
    KNOWN_FICTIONAL,
    KNOWN_JOKES,
    OBVIOUS_FICTIONAL,
    normalise_name,
)
from professors.models import Professor

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Delete high-confidence canary professors. Dry-run by default; "
        "pass --confirm to actually write."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--l1-fic-jokes", action="store_true",
            help="Scope: rows whose name matches the fictional-character "
                 "or joke-name blacklist.",
        )
        parser.add_argument(
            "--obvious-only", action="store_true",
            help="Modifier on --l1-fic-jokes: restrict the fictional set "
                 "to OBVIOUS franchises only (Harry Potter, LOTR, GoT, "
                 "Star Wars, anime, video games, Disney/Pixar). Excludes "
                 "Marvel/DC/Sherlock/classic-lit names which can plausibly "
                 "belong to real people. Joke names are always kept.",
        )
        parser.add_argument(
            "--fake-institutions", action="store_true",
            help="Scope: every row at a curated fictional institution "
                 "(Hogwarts, Xavier's School for Gifted Youngsters, etc.).",
        )
        parser.add_argument(
            "--confirm", action="store_true",
            help="Actually perform the deletes. Without this flag the "
                 "command prints what it would do and exits.",
        )

    def handle(self, *args, **opts):
        scope_l1 = opts["l1_fic_jokes"]
        scope_inst = opts["fake_institutions"]
        if not (scope_l1 or scope_inst):
            raise CommandError(
                "No scope selected. Pass --l1-fic-jokes and/or "
                "--fake-institutions."
            )
        confirm = opts["confirm"]

        ids_to_delete: set[int] = set()
        per_scope_counts: dict[str, int] = {}

        if scope_l1:
            obvious_only = opts["obvious_only"]
            fictional_set = OBVIOUS_FICTIONAL if obvious_only else KNOWN_FICTIONAL
            label = (
                "l1_fic_jokes (obvious franchises only)"
                if obvious_only else "l1_fic_jokes"
            )
            l1_ids = self._collect_l1_fic_joke_ids(fictional_set)
            per_scope_counts[label] = len(l1_ids)
            ids_to_delete.update(l1_ids)
            if obvious_only:
                skipped = self._collect_l1_fic_joke_ids(BORDERLINE_FICTIONAL)
                # Borderline IDs *not* already on the obvious side need to
                # be reported so the operator knows what was spared.
                spared = set(skipped) - set(l1_ids)
                per_scope_counts["_spared_borderline_fictional"] = len(spared)

        if scope_inst:
            inst_ids = self._collect_fake_institution_ids()
            per_scope_counts["fake_institutions"] = len(inst_ids)
            ids_to_delete.update(inst_ids)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Purge plan"))
        for scope, n in per_scope_counts.items():
            self.stdout.write(f"  {scope}: {n} matches")
        self.stdout.write(f"  unique professors to delete: {len(ids_to_delete)}")
        self.stdout.write("")

        if not ids_to_delete:
            self.stdout.write(self.style.WARNING("Nothing to delete."))
            return

        # Always print a sample (and full breakdown for fake-institution scope
        # since that one is small enough to enumerate).
        self._print_sample(ids_to_delete)

        if not confirm:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "DRY-RUN. No rows were deleted. Re-run with --confirm to "
                "execute the deletion."
            ))
            return

        # Live deletion path.
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Deleting {len(ids_to_delete)} professors"
        ))
        with transaction.atomic():
            qs = Professor.objects.filter(id__in=ids_to_delete)
            deleted, by_model = qs.delete()
        self.stdout.write(self.style.SUCCESS(
            f"  deleted total: {deleted}  (per-model: {by_model})"
        ))

    def _collect_l1_fic_joke_ids(
        self, fictional_set: frozenset[str] | None = None,
    ) -> list[int]:
        """Return ids matching the selected name lists."""
        if fictional_set is None:
            fictional_set = KNOWN_FICTIONAL
        rows = Professor.objects.exclude(name="").values_list("id", "name")
        out: list[int] = []
        for pk, name in rows.iterator(chunk_size=10_000):
            norm = normalise_name(name)
            if not norm:
                continue
            if norm in fictional_set or norm in KNOWN_JOKES:
                out.append(pk)
        return out

    def _collect_fake_institution_ids(self) -> list[int]:
        """Return ids at known fictional institutions."""
        return list(
            Professor.objects.filter(
                institution__in=FICTIONAL_INSTITUTIONS,
            ).values_list("id", flat=True)
        )

    def _print_sample(self, ids: set[int]) -> None:
        """Print a short deletion preview."""
        sample = list(
            Professor.objects.filter(id__in=ids)
            .order_by("institution", "name")
            .values("id", "name", "institution")[:50]
        )
        self.stdout.write("First 50 rows that match (alphabetical by institution):")
        self.stdout.write("")
        for r in sample:
            self.stdout.write(
                f"  #{r['id']:>7}  {r['name']:<35}  @ {r['institution']}"
            )

        institutions = Counter(
            Professor.objects.filter(id__in=ids)
            .values_list("institution", flat=True)
        )
        if len(institutions) > 1:
            self.stdout.write("")
            self.stdout.write("Per-institution breakdown:")
            for inst, c in institutions.most_common():
                inst_label = inst or "_(empty institution)_"
                self.stdout.write(f"  {c:>5}  {inst_label}")
