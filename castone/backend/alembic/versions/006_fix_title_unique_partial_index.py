"""fix ix_games_title_lower to partial index (WAITING only)

배경: 004 마이그레이션에서 ix_games_title_lower를 전역 unique index로 생성했으나
앱 레벨 중복 검사는 WAITING 상태 방만 대상으로 한다.
FINISHED/PROGRESS 게임의 제목이 DB에 남아 새 방 생성을 막는 버그 수정.

해결: WAITING 상태에만 적용되는 partial unique index로 교체.

Revision ID: 006
Revises: 005
Create Date: 2026-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 전역 unique index 제거
    op.drop_index("ix_games_title_lower", table_name="games")
    # WAITING 상태에만 적용되는 partial unique index 생성
    op.create_index(
        "ix_games_title_lower",
        "games",
        [sa.text("lower(title)")],
        unique=True,
        postgresql_where=sa.text("status = 'WAITING'"),
    )


def downgrade() -> None:
    op.drop_index("ix_games_title_lower", table_name="games")
    op.create_index(
        "ix_games_title_lower",
        "games",
        [sa.text("lower(title)")],
        unique=True,
    )
