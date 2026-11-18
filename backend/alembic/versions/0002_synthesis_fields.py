"""synthesis evidence fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pain_points", sa.Column("source_field", sa.String(length=32), nullable=True))
    op.add_column(
        "pain_points",
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("theme_evidence", sa.Column("source_field", sa.String(length=32), nullable=True))
    op.add_column("themes", sa.Column("severity", sa.Integer(), server_default="3", nullable=False))


def downgrade() -> None:
    op.drop_column("themes", "severity")
    op.drop_column("theme_evidence", "source_field")
    op.drop_column("pain_points", "duplicate_count")
    op.drop_column("pain_points", "source_field")
