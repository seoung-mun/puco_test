"""add email, created_at, unique nickname to users

Revision ID: 002
Revises: 001
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add email column (nullable — existing users don't have it yet)
    op.add_column("users", sa.Column("email", sa.String(), nullable=True))
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Add created_at column with default = now for existing rows
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Make nickname unique (NULL values are NOT considered duplicate in PostgreSQL)
    op.create_index("ix_users_nickname", "users", ["nickname"], unique=True)

    # Make google_id NOT NULL (should already be set for all rows)
    op.alter_column("users", "google_id", nullable=False)


def downgrade() -> None:
    op.alter_column("users", "google_id", nullable=True)
    op.drop_index("ix_users_nickname", "users")
    op.drop_column("users", "created_at")
    op.drop_index("ix_users_email", "users")
    op.drop_column("users", "email")
