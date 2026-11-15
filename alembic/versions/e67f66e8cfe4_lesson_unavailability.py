"""lesson_unavailability

Revision ID: e67f66e8cfe4
Revises: c73e8f21a94b
Create Date: 2026-11-15 17:31:34.770963

documents/plans/emess-radio-plan.md §4.4: the general "no longer available at source"
state, as row presence (database-schema.md §3.7, §4.5).

The check constraint's value list is frozen here, deliberately, rather than computed
from `UnavailabilityReason`: a migration has to keep meaning what it meant when it ran.
A new reason is a new migration that replaces the constraint.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e67f66e8cfe4"
down_revision: Union[str, Sequence[str], None] = "c73e8f21a94b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lesson_unavailability",
        sa.Column("lesson_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("superseded_by_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("reason IN ('source_url_reused')", name="ck_lesson_unavailability_reason"),
        sa.ForeignKeyConstraint(
            ["lesson_id"], ["lessons.id"], name="fk_lesson_unavailability_lesson_id_lessons"
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["lessons.id"],
            name="fk_lesson_unavailability_superseded_by_id_lessons",
        ),
        sa.PrimaryKeyConstraint("lesson_id", name="pk_lesson_unavailability"),
    )


def downgrade() -> None:
    op.drop_table("lesson_unavailability")
