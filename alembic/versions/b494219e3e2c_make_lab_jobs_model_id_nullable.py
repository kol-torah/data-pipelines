"""make lab_jobs.model_id nullable

Revision ID: b494219e3e2c
Revises: a12032085f36
Create Date: 2026-08-17 20:40:54.723571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b494219e3e2c'
down_revision: Union[str, Sequence[str], None] = 'a12032085f36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """The merge job (lab/merge.py) runs no model, and a sentinel string would
    pollute the one column that exists to be queried without JSON paths."""
    op.alter_column("lab_jobs", "model_id", existing_type=sa.Text(), nullable=True, schema="lab")


def downgrade() -> None:
    """Fails if any modelless job (merge) rows exist by then — acceptable for a
    lab table of disposable rows; delete them first if this is ever needed."""
    op.alter_column("lab_jobs", "model_id", existing_type=sa.Text(), nullable=False, schema="lab")
