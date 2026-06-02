from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import User
from app.dependencies import get_db
from app.schemas.analytics import LineupSummaryItem, RecentGameAnalyticsItem
from app.services.analytics import lineup_summary, recent_games


router = APIRouter()


@router.get("/me/lineup-summary", response_model=list[LineupSummaryItem])
async def get_my_lineup_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return lineup_summary(db, str(current_user.id))


@router.get("/me/recent-games", response_model=list[RecentGameAnalyticsItem])
async def get_my_recent_games(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return recent_games(db, str(current_user.id), limit=limit)
