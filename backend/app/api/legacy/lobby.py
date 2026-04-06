"""
Legacy API — 멀티플레이어 로비 엔드포인트.
"""
import json

from fastapi import APIRouter, Depends, HTTPException

from app.services.session_manager import session
from app.services.state_serializer import serialize_game_state
from app.services.event_bus import event_bus

from .deps import require_internal_key, _run_pending_bots
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
    return {"session_key": key, **session.server_info}


@router.post("/lobby/join")
async def lobby_join(body: LobbyJoinBody):
    ok = session.lobby_join(body.key, body.name)
    if not ok:
        raise HTTPException(status_code=403, detail="Invalid key")
    await event_bus.publish(body.key, "lobby_update", json.dumps(session.server_info))
    return session.server_info


@router.post("/lobby/add-bot")
async def lobby_add_bot(body: LobbyAddBotBody):
    ok = session.lobby_add_bot(body.key, body.host_name, body.bot_name, body.bot_type)
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")
    await event_bus.publish(body.key, "lobby_update", json.dumps(session.server_info))
    return session.server_info


@router.post("/lobby/remove-bot")
async def lobby_remove_bot(body: LobbyRemoveBotBody):
    ok = session.lobby_remove_bot(body.key, body.host_name, body.bot_name)
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")
    await event_bus.publish(body.key, "lobby_update", json.dumps(session.server_info))
    return session.server_info


@router.post("/lobby/start")
async def lobby_start(body: LobbyStartBody):
    try:
        session.lobby_start(body.key, body.name)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    _run_pending_bots()
    gs = serialize_game_state(session)
    await event_bus.publish(body.key, "state_update", json.dumps(gs))
    return gs
