"""lessons.source_id NOT NULL

Revision ID: c73e8f21a94b
Revises: 9a1c4f2be7d0
Create Date: 2026-09-03 15:55:00.000000

The second half of a two-phase column add. 9a1c4f2be7d0 could only add `source_id`
nullable: `sources` is seeded from the catalogue rather than from a migration, so at
that point there was nothing to backfill from. The rebuild
(documents/plans/catalogue-redesign-plan.md §10, steps 5-6) has since repopulated every
lesson through an ingest rule, which always knows its source.

A lesson without a source is now meaningless — it is what `(source_id, external_id)`
is unique on, and what decides how the audio gets fetched — so the column should say so.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c73e8f21a94b"
down_revision: Union[str, Sequence[str], None] = "9a1c4f2be7d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("lessons", "source_id", existing_type=sa.BigInteger(), nullable=False)


def downgrade() -> None:
    op.alter_column("lessons", "source_id", existing_type=sa.BigInteger(), nullable=True)
