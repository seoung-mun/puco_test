"""add host_id to games

Revision ID: 005
Revises: 004
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('games', sa.Column('host_id', sa.String(), nullable=True))
    op.create_index('ix_games_host_id', 'games', ['host_id'])
    # Backfill WAITING rooms only: host_id = players[0] (must be a human, not BOT_*)
    op.execute(text("""
        UPDATE games
        SET host_id = players->>0
        WHERE status = 'WAITING'
          AND players IS NOT NULL
          AND jsonb_array_length(players) > 0
          AND players->>0 NOT LIKE 'BOT_%'
    """))


def downgrade() -> None:
    op.drop_index('ix_games_host_id', table_name='games')
    op.drop_column('games', 'host_id')
