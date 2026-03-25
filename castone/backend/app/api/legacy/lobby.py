"""
Legacy API — 멀티플레이어 로비 엔드포인트.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.services.session_manager import session

from .deps import require_internal_key
from .schemas import (
    MultiplayerInitBody,
    LobbyJoinBody,
    LobbyAddBotBody,
    LobbyRemoveBotBody,
    LobbyStartBody,
)

router = APIRouter()


@router.post("/multiplayer/init")
def multiplayer_init(body: MultiplayerInitBody, _=Depends(require_internal_key)):
    key = session.init_multiplayer(body.host_name)
    return {"key": key, **session.server_info}


@router.post("/lobby/join")
def lobby_join(body: LobbyJoinBody):
    ok = session.lobby_join(body.key, body.name)
    if not ok:
        raise HTTPException(status_code=403, detail="Invalid key")
    return session.server_info


@router.post("/lobby/add-bot")
def lobby_add_bot(body: LobbyAddBotBody):
    ok = session.lobby_add_bot(body.key, body.host_name, body.bot_name, body.bot_type)
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")
    return session.server_info


@router.post("/lobby/remove-bot")
def lobby_remove_bot(body: LobbyRemoveBotBody):
    ok = session.lobby_remove_bot(body.key, body.host_name, body.bot_name)
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")
    return session.server_info


@router.post("/lobby/start")
def lobby_start(body: LobbyStartBody):
    try:
        session.lobby_start(body.key, body.name)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return session.server_info
