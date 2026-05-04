"""add action intent id

Revision ID: 4f9c8f4d4b2a
Revises: 097bcf0bc911
Create Date: 2026-05-04 09:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4f9c8f4d4b2a"
down_revision: Union[str, None] = "097bcf0bc911"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_logs", sa.Column("action_intent_id", sa.String(length=64), nullable=True))
    op.create_index(
        "ux_game_logs_game_intent",
        "game_logs",
        ["game_id", "action_intent_id"],
        unique=True,
        postgresql_where=sa.text("action_intent_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_game_logs_game_intent", table_name="game_logs")
    op.drop_column("game_logs", "action_intent_id")
