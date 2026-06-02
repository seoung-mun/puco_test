from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LineupSummaryItem(BaseModel):
    lineup: str
    ordered_players: list[str]
    my_seat: int
    games: int
    wins: int
    losses: int
    draws: int
    win_rate: float
    avg_vp_gap: Optional[float] = None
    vp_gap_games: int
    last_played_at: Optional[datetime] = None


class RecentGameAnalyticsItem(BaseModel):
    game_id: str
    created_at: datetime
    result: str
    opponent_bots: list[str]
    winner_id: Optional[str] = None
    ordered_players: Optional[list[str]] = None
    my_seat: Optional[int] = None
    my_rank: Optional[int] = None
    winner_display_name: Optional[str] = None
    my_vp: Optional[int] = None
    benchmark_vp: Optional[int] = None
    vp_gap: Optional[int] = None
    score_data_available: Optional[bool] = None
