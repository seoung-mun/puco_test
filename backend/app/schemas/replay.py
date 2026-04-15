from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class ReplayPlayerInfo(BaseModel):
    display_name: str
    is_bot: bool


class ReplayListItem(BaseModel):
    index: int
    game_id: UUID
    display_label: str
    human_player_names: List[str]
    played_date: str
    created_at: datetime
    num_players: int
    winner: Optional[str] = None
    players: List[ReplayPlayerInfo]


class ReplayListResponse(BaseModel):
    replays: List[ReplayListItem]
    page: int
    size: int
    total_items: int
    total_pages: int


class ReplayFrame(BaseModel):
    frame_index: int
    step: Optional[int] = None
    action: Optional[str] = None
    commentary: Optional[str] = None
    rich_state: Dict[str, Any]


class ReplayDetailResponse(BaseModel):
    game_id: UUID
    display_label: str
    players: List[ReplayPlayerInfo]
    replay_frames: List[ReplayFrame]
    total_frames: int
    final_scores: List[Dict[str, Any]] = []
