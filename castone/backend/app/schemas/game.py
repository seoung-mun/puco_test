from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID


class GameAction(BaseModel):
    game_id: UUID | None = None
    action_type: str | None = None
    payload: Dict[str, Any]


class MayorPlacementItem(BaseModel):
    slot_id: str
    count: int = Field(ge=0, le=3)


class MayorDistributeRequest(BaseModel):
    placements: List[MayorPlacementItem]


class ActionLog(BaseModel):
    game_id: UUID
    round: int
    step: int
    actor_id: str
    action_data: Dict[str, Any]
    available_options: List[int]
    state_before: Dict[str, Any]
    state_after: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class GameRoomCreate(BaseModel):
    title: str = Field(min_length=1, max_length=30)
    is_private: bool = False
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: Optional[str], info) -> Optional[str]:
        if v is None:
            return v
        if not v.isdigit() or len(v) != 4:
            raise ValueError("비밀번호는 4자리 숫자여야 합니다")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return v.strip()


class JoinRoomRequest(BaseModel):
    password: Optional[str] = None


class RoomPlayerInfo(BaseModel):
    display_name: str
    is_bot: bool


class GameRoomResponse(BaseModel):
    id: UUID
    title: str
    status: str
    is_private: bool
    current_players: int
    max_players: int
    player_names: List[RoomPlayerInfo] = []
