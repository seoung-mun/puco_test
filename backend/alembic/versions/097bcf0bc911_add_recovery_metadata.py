"""add recovery metadata

Revision ID: 097bcf0bc911
Revises: 007
Create Date: 2026-05-04 05:46:37.043204

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "097bcf0bc911"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("games", sa.Column("game_seed", sa.BigInteger(), nullable=True))
    op.add_column("games", sa.Column("governor_idx", sa.Integer(), nullable=True))
    op.add_column("games", sa.Column("engine_compat_version", sa.Integer(), nullable=True))
    op.add_column(
        "games",
        sa.Column("state_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("games", sa.Column("recovery_blocked_reason", sa.String(length=64), nullable=True))

    op.add_column("game_logs", sa.Column("revision", sa.Integer(), nullable=True))
    op.add_column("game_logs", sa.Column("phase_before", sa.String(length=32), nullable=True))
    op.add_column(
        "game_logs",
        sa.Column("active_player_before", sa.String(length=16), nullable=True),
    )

    op.create_index(
        "ux_game_logs_game_revision",
        "game_logs",
        ["game_id", "revision"],
        unique=True,
        postgresql_where=sa.text("revision IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_game_logs_game_revision", table_name="game_logs")
    op.drop_column("game_logs", "active_player_before")
    op.drop_column("game_logs", "phase_before")
    op.drop_column("game_logs", "revision")
    op.drop_column("games", "recovery_blocked_reason")
    op.drop_column("games", "state_revision")
    op.drop_column("games", "engine_compat_version")
    op.drop_column("games", "governor_idx")
    op.drop_column("games", "game_seed")
