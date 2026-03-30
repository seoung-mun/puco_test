"""add is_private, password, unique title index to games

Revision ID: 004
Revises: 003
Create Date: 2026-03-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("games", sa.Column("is_private", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("games", sa.Column("password", sa.String(4), nullable=True))
    # Case-insensitive unique index on title (only for WAITING rooms enforced at app level)
    op.create_index("ix_games_title_lower", "games", [sa.text("lower(title)")], unique=True)


def downgrade() -> None:
    op.drop_index("ix_games_title_lower", table_name="games")
    op.drop_column("games", "password")
    op.drop_column("games", "is_private")
