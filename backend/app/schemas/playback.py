from pydantic import BaseModel, field_validator
from typing import Literal


class PlaybackState(BaseModel):
    speed: int = 1
    paused: bool = False


class SpeedRequest(BaseModel):
    speed: int

    @field_validator("speed")
    @classmethod
    def validate_speed(cls, v: int) -> int:
        if v not in (1, 2, 4):
            raise ValueError("speed must be 1, 2, or 4")
        return v


class PauseRequest(BaseModel):
    paused: bool
