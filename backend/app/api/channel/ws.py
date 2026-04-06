import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.services.ws_manager import manager
from app.dependencies import SessionLocal
import jwt
from app.core.security import SECRET_KEY, ALGORITHM
from app.db.models import GameSession, User

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_ws_user(token: str, db: Session) -> User | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return db.query(User).filter(User.id == user_id).first()
    except jwt.PyJWTError:
        return None


@router.websocket("/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    await websocket.accept()
    connection_id = f"preauth-{id(websocket)}"
    logger.warning("[WS_TRACE] ws_connect game=%s connection_id=%s user_id=%s", game_id, connection_id, None)

    # Task 0.4: first-message JWT auth (token not in URL)
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        logger.warning(
            "[WS_TRACE] ws_receive game=%s connection_id=%s user_id=%s message_type=%s",
            game_id,
            connection_id,
            None,
            auth_msg.get("type", "auth"),
        )
        token = auth_msg.get("token") or auth_msg.get("accessToken")
        if not token:
            await websocket.close(code=1008, reason="Token required")
            logger.warning("[WS_TRACE] ws_disconnect game=%s connection_id=%s user_id=%s", game_id, connection_id, None)
            return
    except asyncio.TimeoutError:
        await websocket.close(code=1008, reason="Auth timeout")
        logger.warning("[WS_TRACE] ws_disconnect game=%s connection_id=%s user_id=%s", game_id, connection_id, None)
        return
    except Exception:
        await websocket.close(code=1008, reason="Invalid auth message")
        logger.warning("[WS_TRACE] ws_disconnect game=%s connection_id=%s user_id=%s", game_id, connection_id, None)
        return

    with SessionLocal() as db:
        user = _get_ws_user(token, db)
        room = db.query(GameSession).filter(GameSession.id == game_id).first()

    if not user:
        await websocket.close(code=1008, reason="Invalid token")
        logger.warning("[WS_TRACE] ws_disconnect game=%s connection_id=%s user_id=%s", game_id, connection_id, None)
        return

    if room is None:
        await websocket.close(code=1008, reason="Game not found")
        logger.warning("[WS_TRACE] ws_disconnect game=%s connection_id=%s user_id=%s", game_id, connection_id, str(user.id))
        return

    user_id = str(user.id)
    is_player = user_id in [str(player_id) for player_id in (room.players or [])]
    is_host = user_id == str(room.host_id)
    if not (is_player or is_host):
        await websocket.close(code=1008, reason="Forbidden")
        logger.warning("[WS_TRACE] ws_disconnect game=%s connection_id=%s user_id=%s", game_id, connection_id, user_id)
        return

    player_id = user_id
    await websocket.send_json({"type": "auth_ok", "player_id": player_id})
    logger.warning("[WS_TRACE] ws_auth_ok_sent game=%s connection_id=%s user_id=%s", game_id, connection_id, player_id)

    await manager.connect(game_id, websocket, player_id=player_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                logger.warning(
                    "[WS_TRACE] ws_receive game=%s connection_id=%s user_id=%s message_type=%s",
                    game_id,
                    connection_id,
                    player_id,
                    message.get("type", "unknown"),
                )
                await manager.handle_client_message(game_id, player_id, message)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        logger.warning("[WS_TRACE] ws_disconnect game=%s connection_id=%s user_id=%s", game_id, connection_id, player_id)
        await manager.disconnect(game_id, websocket, player_id=player_id)
