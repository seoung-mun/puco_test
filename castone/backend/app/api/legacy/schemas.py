"""
Legacy API — Pydantic request body 모델.
"""
from typing import List, Optional

from pydantic import BaseModel


class NewGameBody(BaseModel):
    num_players: int = 3
    player_names: List[str] = []


class BotSetBody(BaseModel):
    player: str          # "player_0", "player_1", …
    bot_type: str = "random"


class MultiplayerInitBody(BaseModel):
    host_name: str


class LobbyJoinBody(BaseModel):
    key: str
    name: str
    role: str = "player"


class LobbyAddBotBody(BaseModel):
    key: str
    host_name: str
    bot_name: str
    bot_type: str = "random"


class LobbyRemoveBotBody(BaseModel):
    key: str
    host_name: str
    bot_name: str


class LobbyStartBody(BaseModel):
    key: str
    name: str


class HeartbeatBody(BaseModel):
    key: str
    name: str


class SelectRoleBody(BaseModel):
    player: str
    role: str


class SettlePlantationBody(BaseModel):
    player: str
    plantation: str
    use_hospice: bool = False


class MayorColonistBody(BaseModel):
    player: str
    target_type: str   # "island" | "city"
    target_index: int


class MayorPlaceAmountBody(BaseModel):
    player: str
    amount: int  # 0-3: colonists to place on CURRENT sequential slot


class MayorDistributeBody(BaseModel):
    player: str
    distribution: List[int]  # 길이 24: 인덱스 0-11=island slots, 12-23=city slots


class MayorFinishBody(BaseModel):
    player: str


class SellBody(BaseModel):
    good: str


class CraftsmanPrivBody(BaseModel):
    good: str


class LoadShipBody(BaseModel):
    player: str
    good: str
    ship_index: int
    use_wharf: bool = False


class CaptainPassBody(BaseModel):
    player: str


class DiscardGoodsBody(BaseModel):
    player: str
    protected: List[str] = []
    single_extra: Optional[str] = None


class BuildBody(BaseModel):
    player: str
    building: str
