"""add state_summary JSONB column to game_logs

Revision ID: 003
Revises: 002
Create Date: 2026-03-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "game_logs",
        sa.Column("state_summary", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("game_logs", "state_summary")
