"""One-off copy of the catalog tables into production CockroachDB.

Copies Source, Department, Professor and ProfessorStats from the local
database into the 'remote' alias, keeping primary keys intact so foreign
keys still line up. Requires DB_HOST (see recommender/settings.py) or fails
fast. Safe to re-run — rows already on 'remote' are skipped by primary key,
and --fix-timestamps repairs updated_at values an earlier run clobbered.
"""
from contextlib import contextmanager

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from professors.models import Department, Professor, ProfessorStats, Source

# Rows are read and written in chunks of this size. Kept modest so memory use
# stays flat while iterating over ~1.79M Professor rows.
CHUNK_SIZE = 5000

# (model, human label, show per-batch progress). Source/Department are tiny, so
# a single completion line is plenty; Professor/ProfessorStats are large and a
# human watches them run, so they get per-batch progress output.
TABLES = [
    (Source, "Source", False),
    (Department, "Department", False),
    (Professor, "Professor", True),
    (ProfessorStats, "ProfessorStats", True),
]

# (model, timestamp field) pairs repaired by --fix-timestamps. Only
# updated_at matters functionally (views.py compares it against
# LIVE_ANALYSIS_CUTOFF); Professor.created_at is cosmetic and left alone.
REPAIR_TARGETS = [
    (ProfessorStats, "updated_at"),
]


@contextmanager
def _suspend_auto_now(model):
    """Temporarily disable auto_now/auto_now_add on a model's fields.

    bulk_create() runs pre_save() on every insert, which would otherwise
    stamp copied timestamps with the current time instead of the original
    value. Restores the original flags afterward, even if the write raises.
    """
    fields = [
        f for f in model._meta.get_fields()
        if hasattr(f, "auto_now") and (f.auto_now or f.auto_now_add)
    ]
    originals = [(f, f.auto_now, f.auto_now_add) for f in fields]
    for field in fields:
        field.auto_now = False
        field.auto_now_add = False
    try:
        yield
    finally:
        for field, orig_auto_now, orig_auto_now_add in originals:
            field.auto_now = orig_auto_now
            field.auto_now_add = orig_auto_now_add


class Command(BaseCommand):
    help = (
        "Copy Source, Department, Professor and ProfessorStats rows from the "
        "local 'default' database into the 'remote' database (CockroachDB), "
        "preserving primary keys. Requires the DB_HOST env var (plus the other "
        "DB_* vars) so that settings.py defines the 'remote' alias. Fails fast "
        "if 'remote' is not configured. Pass --yes to actually write; without "
        "it the command is a read-only dry run that prints row counts."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help=(
                "Perform the copy. Without this flag the command runs as a dry "
                "run only: it prints each table's source and remote row counts "
                "and writes nothing."
            ),
        )
        parser.add_argument(
            "--fix-timestamps",
            action="store_true",
            help=(
                "Repair mode instead of copy mode: for every row of "
                "ProfessorStats, copy the local 'default' updated_at value onto "
                "the matching 'remote' row (matched by id), undoing the "
                "auto_now override that stamped every remote row with the push "
                "date. Requires --yes and writes nothing without it. No rows "
                "are copied in this mode."
            ),
        )

    # -- helpers -----------------------------------------------------------

    def _require_remote_alias(self):
        """Fail fast unless settings.py defined a 'remote' database alias."""
        if "remote" not in connections.databases:
            raise CommandError(
                "The 'remote' database alias is not configured, so there is "
                "nothing to copy into. Set the DB_HOST environment variable "
                "(along with DB_NAME, DB_USER, DB_PASSWORD, DB_PORT and, if "
                "needed, DB_SSLMODE / DB_SSLROOTCERT) so that "
                "recommender/settings.py defines the 'remote' connection, then "
                "re-run this command."
            )

    def _count(self, model, alias):
        """Row count for a model on a given database alias."""
        return model.objects.using(alias).count()

    def _copy_table(self, model, label, progress):
        """Copy every row of ``model`` from 'default' to 'remote'.

        Primary keys (and every other field, including nullable FKs such as
        ``Professor.department_id``) are copied explicitly. Returns nothing;
        prints a completion summary line.
        """
        src_qs = model.objects.using("default").order_by("pk")
        total = src_qs.count()
        before = self._count(model, "remote")

        # attname gives the DB column name: plain field name for normal fields
        # and the "<field>_id" attribute for foreign keys (so nullable FKs come
        # through as None with no special casing). Include every concrete field
        # — including the primary key — so bulk_create keeps source PKs.
        field_names = [field.attname for field in model._meta.concrete_fields]

        remote_mgr = model.objects.using("remote")
        written = 0
        batch = []
        # Suspend auto_now/auto_now_add while inserting: bulk_create runs each
        # field's pre_save(), which would otherwise overwrite the explicitly
        # copied historical timestamps (Professor.created_at,
        # ProfessorStats.updated_at) with "now".
        with _suspend_auto_now(model):
            for row in src_qs.iterator(chunk_size=CHUNK_SIZE):
                batch.append(model(**{name: getattr(row, name) for name in field_names}))
                if len(batch) >= CHUNK_SIZE:
                    remote_mgr.bulk_create(
                        batch, batch_size=CHUNK_SIZE, ignore_conflicts=True,
                    )
                    written += len(batch)
                    batch = []
                    if progress:
                        self.stdout.write(
                            f"{label}: {written}/{total} ({written / total:.1%})"
                        )
            if batch:
                remote_mgr.bulk_create(
                    batch, batch_size=CHUNK_SIZE, ignore_conflicts=True,
                )
                written += len(batch)
                if progress:
                    self.stdout.write(
                        f"{label}: {written}/{total} ({written / total:.1%})"
                    )

        after = self._count(model, "remote")
        inserted = after - before
        skipped = written - inserted
        self.stdout.write(
            self.style.SUCCESS(
                f"{label}: processed {written} source row(s); remote {before} -> "
                f"{after} ({inserted} new, {skipped} skipped as already present)."
            )
        )

    def _repair_timestamp_field(self, model, field_name):
        """Copy one timestamp field from 'default' onto 'remote', matched by id.

        Reads every source row's primary key and ``field_name`` value and pushes
        the value onto the corresponding remote row with ``bulk_update``, so only
        that one column is touched and every other remote column is left alone.
        Rows that do not exist on remote are skipped by the ``pk__in`` filter.
        Prints per-batch progress and a summary.
        """
        label = f"{model.__name__}.{field_name}"
        src_qs = (
            model.objects.using("default")
            .order_by("pk")
            .values_list("pk", field_name)
        )
        total = src_qs.count()
        remote_mgr = model.objects.using("remote")

        read = 0
        repaired = 0
        batch = []

        # bulk_update reads each field's value with getattr(obj, field.attname)
        # and never calls pre_save(), so auto_now should not clobber these
        # values — but the toggle is applied unconditionally anyway so this path
        # can never regress into the bulk_create-style overwrite.
        with _suspend_auto_now(model):
            for pk, value in src_qs.iterator(chunk_size=CHUNK_SIZE):
                batch.append(model(pk=pk, **{field_name: value}))
                if len(batch) >= CHUNK_SIZE:
                    repaired += remote_mgr.bulk_update(
                        batch, [field_name], batch_size=CHUNK_SIZE,
                    )
                    read += len(batch)
                    batch = []
                    if total:
                        self.stdout.write(
                            f"{label}: {read}/{total} ({read / total:.1%})"
                        )
                    else:
                        self.stdout.write(f"{label}: {read} row(s) processed")
            if batch:
                repaired += remote_mgr.bulk_update(
                    batch, [field_name], batch_size=CHUNK_SIZE,
                )
                read += len(batch)
                if total:
                    self.stdout.write(
                        f"{label}: {read}/{total} ({read / total:.1%})"
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"{label}: repaired {repaired} row(s) on 'remote' "
                f"({read} source row(s) read, "
                f"{read - repaired} had no matching remote row)."
            )
        )
        return repaired

    def _fix_timestamps(self):
        """Repair timestamps already corrupted on 'remote' by an earlier copy."""
        self.stdout.write(
            "Repair mode (--fix-timestamps): writing local timestamp values "
            "onto 'remote'. No rows are copied."
        )
        total_repaired = 0
        for model, field_name in REPAIR_TARGETS:
            total_repaired += self._repair_timestamp_field(model, field_name)
        self.stdout.write(
            self.style.SUCCESS(
                f"Timestamp repair complete: {total_repaired} row(s) repaired."
            )
        )

    # -- entry point -------------------------------------------------------

    def handle(self, *args, **options):
        # The 'remote' alias must exist even for a dry run (the dry run reads
        # its current row counts), so this check comes first either way.
        self._require_remote_alias()

        if not options["yes"]:
            self.stdout.write(
                "Dry run (no --yes given): nothing will be written. "
                "Row counts below; re-run with --yes to perform the copy."
            )
            for model, label, _ in TABLES:
                src = self._count(model, "default")
                dst = self._count(model, "remote")
                self.stdout.write(f"  {label}: source={src}, remote={dst}")
            self.stdout.write("Dry run complete — no rows were written.")
            return

        self.stdout.write("Starting copy: 'default' -> 'remote' (order: "
                          + " -> ".join(label for _, label, _ in TABLES) + ").")
        completed = []
        try:
            for model, label, progress in TABLES:
                self._copy_table(model, label, progress)
                completed.append(label)
        except KeyboardInterrupt:
            self.stderr.write(self.style.WARNING(
                "Interrupted by user. Completed tables: "
                f"{', '.join(completed) if completed else 'none'}. "
                "Re-run the command to continue — rows already present on "
                "'remote' are skipped via ignore_conflicts."
            ))
            raise

        self.stdout.write(self.style.SUCCESS("Copy complete."))
