"""One-time backfill of ProfessorStats.analysis_source from the old
updated_at-based heuristic (rows before 2026-05-09 were the bulk seed
import). Going forward, analysis_source is set explicitly by the seed
loader and the live-analysis paths, so this heuristic is never needed again.
"""
from datetime import datetime, timezone

from django.db import migrations

_OLD_LIVE_ANALYSIS_CUTOFF = datetime(2026, 5, 9, tzinfo=timezone.utc)


def backfill_seed_rows(apps, schema_editor):
    ProfessorStats = apps.get_model("professors", "ProfessorStats")
    ProfessorStats.objects.filter(
        updated_at__lt=_OLD_LIVE_ANALYSIS_CUTOFF
    ).update(analysis_source="seed")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("professors", "0004_professorstats_analysis_source"),
    ]

    operations = [
        migrations.RunPython(backfill_seed_rows, noop),
    ]
