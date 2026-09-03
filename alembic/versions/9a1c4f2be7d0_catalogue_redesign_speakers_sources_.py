"""catalogue redesign: speakers, sources, ingest_rules, per-lesson attribution

Revision ID: 9a1c4f2be7d0
Revises: b494219e3e2c
Create Date: 2026-09-03 12:10:00.000000

Step 2 of documents/plans/catalogue-redesign-plan.md §10. Splits the three jobs
`series` was doing at once — editorial grouping, attribution, and source location —
into `series`, `lesson_speakers`, and `sources` + `ingest_rules`.

Structure only: no lesson or audio row is deleted here. The rebuild (§10 steps 4-6)
re-keys S3 from the still-intact `audio_files` rows *before* anything is wiped, so this
migration deliberately keeps the derived data alive and backfills rather than truncates.
Everything it backfills is therefore correct on its own terms even if the rebuild is
never run.

Two columns are added nullable that the design wants NOT NULL — `lessons.source_id` and
(effectively) `lessons.lesson_type_id`. `source_id` has no value to backfill because
`sources` is seeded from the catalogue, not from here; a follow-up migration tightens it
once discover has repopulated every row. This is an ordinary two-phase column add, not
an unresolved question.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "9a1c4f2be7d0"
down_revision: Union[str, Sequence[str], None] = "b494219e3e2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Agreed vocabulary, catalogue-redesign-plan.md §3.3. Seeded here rather than left to the
# catalogue because `series.lesson_type_id` is NOT NULL and has to be backfilled in this
# same migration; seed_catalogue upserts the same rows harmlessly afterwards.
LESSON_TYPES = [
    ("halacha", "הלכה", "Halacha", 10),
    ("gemara", "גמרא", "Talmud", 20),
    ("tanach", 'תנ"ך', "Tanach", 30),
    ("parasha", "פרשת שבוע", "Weekly Parasha", 40),
    ("mishna", "משנה", "Mishna", 50),
    ("musar", "מוסר", "Musar", 60),
    ("machshava", "מחשבה ואמונה", "Jewish Thought", 70),
    ("chasidut", "חסידות", "Chasidut", 80),
    ("qa", "שאלות ותשובות", "Q&A", 90),
    ("hadracha", "הדרכה ומשפחה", "Guidance & Family", 100),
    ("moed", "מועדים ואירועים", "Occasions & Holidays", 110),
]

# The three free-string values that exist today. "Short Lesson" was a *length*, not a
# subject — Halacha Yomit is halacha that happens to run four minutes, and length is
# already in audio_files.duration_s.
OLD_TYPE_TO_SLUG = {
    "Halacha Lesson": "halacha",
    "Short Lesson": "halacha",
    "Q&A": "qa",
}


def upgrade() -> None:
    conn = op.get_bind()

    # --- lesson_types, seeded so the backfills below have something to point at ---
    op.create_table(
        "lesson_types",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name_he", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("slug", name="uq_lesson_types_slug"),
        sa.PrimaryKeyConstraint("id", name="pk_lesson_types")
    )
    for slug, name_he, name_en, order in LESSON_TYPES:
        conn.execute(
            sa.text(
                "INSERT INTO lesson_types (slug, name_he, name_en, sort_order)"
                " VALUES (:s, :h, :e, :o)"
            ),
            {"s": slug, "h": name_he, "e": name_en, "o": order},
        )

    # --- speakers, carrying the rabbis rows across with rewritten slugs ---
    op.create_table(
        "speakers",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name_he", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_speakers_slug"),
        sa.PrimaryKeyConstraint("id", name="pk_speakers")
    )
    # 'rabbi-butbul' -> 'r-butbul': the r- prefix is the speaker namespace, not a claim
    # about ordination (catalogue-redesign-plan.md §3.0).
    conn.execute(
        sa.text(
            "INSERT INTO speakers (id, name_he, name_en, slug, created_at)"
            " SELECT id, name_he, name_en,"
            "        CASE WHEN slug LIKE 'rabbi-%' THEN 'r-' || substring(slug from 7)"
            "             ELSE slug END,"
            "        created_at"
            " FROM rabbis"
        )
    )
    conn.execute(
        sa.text(
            "SELECT setval(pg_get_serial_sequence('speakers','id'),"
            " COALESCE((SELECT max(id) FROM speakers), 1))"
        )
    )

    op.create_table(
        "speaker_aliases",
        sa.Column("name_he", sa.Text(), nullable=False),
        sa.Column("speaker_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["speaker_id"], ["speakers.id"], name="fk_speaker_aliases_speaker_id_speakers"
        ),
        sa.PrimaryKeyConstraint("name_he", name="pk_speaker_aliases")
    )
    op.create_index("ix_speaker_aliases_speaker_id", "speaker_aliases", ["speaker_id"])
    conn.execute(
        sa.text("INSERT INTO speaker_aliases (name_he, speaker_id) SELECT name_he, id FROM speakers")
    )

    # --- sources and ingest_rules: structure now, rows from the catalogue later ---
    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("parser_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_sources_slug"),
        sa.PrimaryKeyConstraint("id", name="pk_sources")
    )
    op.create_table(
        "ingest_rules",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("series_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("default_speaker_id", sa.BigInteger(), nullable=True),
        sa.Column("priority", sa.BigInteger(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name="fk_ingest_rules_source_id_sources"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], name="fk_ingest_rules_series_id_series"),
        sa.ForeignKeyConstraint(
            ["default_speaker_id"], ["speakers.id"], name="fk_ingest_rules_default_speaker_id_speakers"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingest_rules")
    )
    op.create_index("ix_ingest_rules_source_id", "ingest_rules", ["source_id"])
    op.create_index("ix_ingest_rules_series_id", "ingest_rules", ["series_id"])

    # --- lesson_speakers, backfilled from series.rabbi_id while it still exists ---
    op.create_table(
        "lesson_speakers",
        sa.Column("lesson_id", sa.BigInteger(), nullable=False),
        sa.Column("speaker_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], name="fk_lesson_speakers_lesson_id_lessons"),
        sa.ForeignKeyConstraint(["speaker_id"], ["speakers.id"], name="fk_lesson_speakers_speaker_id_speakers"),
        sa.PrimaryKeyConstraint("lesson_id", "speaker_id", name="pk_lesson_speakers")
    )
    conn.execute(
        sa.text(
            "INSERT INTO lesson_speakers (lesson_id, speaker_id, position)"
            " SELECT l.id, s.rabbi_id, 1 FROM lessons l JOIN series s ON s.id = l.series_id"
        )
    )

    # --- series: gains a typed lesson type, loses its speaker and its adapter ---
    op.add_column("series", sa.Column("lesson_type_id", sa.BigInteger(), nullable=True))
    for old, slug in OLD_TYPE_TO_SLUG.items():
        conn.execute(
            sa.text(
                "UPDATE series SET lesson_type_id = (SELECT id FROM lesson_types WHERE slug = :slug)"
                " WHERE lesson_type = :old"
            ),
            {"slug": slug, "old": old},
        )
    op.alter_column("series", "lesson_type_id", nullable=False)
    op.create_foreign_key(
        "fk_series_lesson_type_id_lesson_types", "series", "lesson_types", ["lesson_type_id"], ["id"]
    )
    op.drop_constraint("fk_series_rabbi_id_rabbis", "series", type_="foreignkey")
    op.drop_column("series", "rabbi_id")
    op.drop_column("series", "adapter_key")
    op.drop_column("series", "lesson_type")

    # --- lessons: source, raw speaker string, typed lesson type, new unique key ---
    op.add_column("lessons", sa.Column("source_id", sa.BigInteger(), nullable=True))
    op.add_column("lessons", sa.Column("speaker_raw", sa.Text(), nullable=True))
    op.add_column("lessons", sa.Column("lesson_type_id", sa.BigInteger(), nullable=True))
    for old, slug in OLD_TYPE_TO_SLUG.items():
        conn.execute(
            sa.text(
                "UPDATE lessons SET lesson_type_id = (SELECT id FROM lesson_types WHERE slug = :slug)"
                " WHERE lesson_type = :old"
            ),
            {"slug": slug, "old": old},
        )
    op.create_foreign_key("fk_lessons_source_id_sources", "lessons", "sources", ["source_id"], ["id"])
    op.create_foreign_key(
        "fk_lessons_lesson_type_id_lesson_types", "lessons", "lesson_types", ["lesson_type_id"], ["id"]
    )
    op.create_index("ix_lessons_source_id", "lessons", ["source_id"])
    # series_id lost its index when the unique key moved off it, and it is now the main
    # lookup path for every per-series query in the discover pipeline.
    op.create_index("ix_lessons_series_id", "lessons", ["series_id"])
    op.drop_column("lessons", "lesson_type")
    op.drop_constraint("uq_lessons_series_id", "lessons", type_="unique")
    op.create_unique_constraint("uq_lessons_source_id", "lessons", ["source_id", "external_id"])

    op.drop_table("rabbis")

    # Derived, never stored (catalogue-redesign-plan.md §5). A view rather than a column
    # so it cannot drift; promote to a materialised view only if it ever gets slow.
    op.execute(
        "CREATE VIEW series_speakers AS"
        " SELECT l.series_id, ls.speaker_id, count(*) AS lesson_count"
        " FROM lessons l JOIN lesson_speakers ls ON ls.lesson_id = l.id"
        " GROUP BY l.series_id, ls.speaker_id"
    )


def downgrade() -> None:
    """Not implemented, deliberately.

    A faithful downgrade would have to invent `series.rabbi_id` for series that now have
    zero or several speakers, and re-derive `adapter_key` strings that no longer exist
    anywhere. Both would silently produce a catalogue that looks restored and isn't.
    Restore from the snapshot `data/backups/public-*.sql` taken in §10 step 1 instead.
    """
    raise NotImplementedError(
        "No downgrade: restore data/backups/public-*.sql (catalogue-redesign-plan.md §10 step 1)."
    )
