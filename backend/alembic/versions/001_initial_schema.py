"""initial schema with JSONB and indexes

Revision ID: 001
Revises:
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("google_id", sa.String(), nullable=True),
        sa.Column("nickname", sa.String(), nullable=True),
        sa.Column("total_games", sa.Integer(), server_default="0"),
        sa.Column("win_rate", sa.Float(), server_default="0.0"),
    )
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)

    op.create_table(
        "games",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("num_players", sa.Integer(), nullable=True),
        sa.Column("players", postgresql.JSONB(), server_default="[]"),
        sa.Column("model_versions", postgresql.JSONB(), server_default="{}"),
        sa.Column("winner_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_games_status", "games", ["status"])

    op.create_table(
        "game_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("round", sa.Integer(), nullable=True),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("action_data", postgresql.JSONB(), nullable=True),
        sa.Column("available_options", postgresql.JSONB(), nullable=True),
        sa.Column("state_before", postgresql.JSONB(), nullable=True),
        sa.Column("state_after", postgresql.JSONB(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_game_logs_game_id", "game_logs", ["game_id"])
    op.create_index("ix_game_logs_round", "game_logs", ["round"])
    op.create_index("ix_game_logs_timestamp", "game_logs", ["timestamp"])
    op.create_index("ix_game_logs_game_round", "game_logs", ["game_id", "round"])


def downgrade() -> None:
    op.drop_table("game_logs")
    op.drop_table("games")
    op.drop_table("users")
