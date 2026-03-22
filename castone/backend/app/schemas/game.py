from pydantic import BaseModel, Field
from typing import Any, Dict, List
from datetime import datetime
from uuid import UUID

class GameAction(BaseModel):
    game_id: UUID
    action_type: str
    payload: Dict[str, Any]

class ActionLog(BaseModel):
    game_id: UUID
    round: int
    step: int
    actor_id: str
    action_data: Dict[str, Any]
    available_options: List[int]  # Action Mask
    state_before: Dict[str, Any]
    state_after: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class GameRoomCreate(BaseModel):
    title: str
    agent_count: int = Field(ge=0, le=2, default=1)
    agent_difficulty: str = "MEDIUM"
    max_players: int = 3

class GameRoomResponse(BaseModel):
    id: UUID
    title: str
    status: str
    current_players: int
    max_players: int
