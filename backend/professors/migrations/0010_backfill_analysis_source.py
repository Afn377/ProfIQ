"""Mark stats rows that came from the seed loader.

0009 gave every existing row the default "live_rmp". That's wrong for
professors whose reviews come from the Seed source. Fix the data, not
just the schema.
"""
from django.db import migrations


def mark_seed_rows(apps, schema_editor):
    ProfessorStats = apps.get_model("professors", "ProfessorStats")
    ProfessorStats.objects.filter(professor__reviews__source__name="Seed").distinct().update(
        analysis_source="seed"
    )


def noop(apps, schema_editor):
    # Reversing 0009 drops the column anyway; nothing to undo here.
    pass


class Migration(migrations.Migration):
    dependencies = [("professors", "0009_professorstats_analysis_source")]
    operations = [migrations.RunPython(mark_seed_rows, noop)]
