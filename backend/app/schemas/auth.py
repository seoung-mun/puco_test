import re
from typing import Optional
from pydantic import BaseModel, field_validator


class GoogleTokenRequest(BaseModel):
    """Frontend sends the id_token obtained from Google Sign-In."""
    credential: str  # Google id_token (JWT)


class NicknameSetRequest(BaseModel):
    nickname: str

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("닉네임은 2자 이상이어야 합니다")
        if len(v) > 20:
            raise ValueError("닉네임은 20자 이하여야 합니다")
        if not re.match(r"^[a-zA-Z0-9가-힣_-]+$", v):
            raise ValueError("닉네임에는 영문, 한글, 숫자, _, - 만 사용할 수 있습니다")
        return v


class UserResponse(BaseModel):
    id: str
    nickname: Optional[str]
    email: Optional[str]
    total_games: int = 0
    win_rate: float = 0.0
    needs_nickname: bool  # True if user hasn't set a nickname yet

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
