import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.dependencies import SessionLocal
from app.services.lobby_manager import lobby_manager, handle_leave, _build_lobby_payload
from app.db.models import GameSession
from app.core.security import decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter()

AUTH_TIMEOUT = 5.0
PING_INTERVAL = 30.0  # 방안 B: zombie connection detection interval (seconds)


@router.websocket("/{room_id}")
async def lobby_websocket(room_id: str, websocket: WebSocket):
    await websocket.accept()
    player_id: str | None = None

    try:
        # 방안 C: short-lived DB session only for setup — closed before entering the wait loop
        with SessionLocal() as db:
            # Auth handshake (5s timeout)
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT)
            except asyncio.TimeoutError:
                await websocket.close(code=4001)
                return

            try:
                msg = json.loads(raw)
                token = msg.get("token") or msg.get("accessToken")
                if not token:
                    raise ValueError("no token")
                payload = decode_access_token(token)
                if payload is None:
                    raise ValueError("invalid token")
                sub = payload.get("sub")
                if not sub:
                    raise ValueError("missing sub claim")
                player_id = str(sub)
            except Exception:
                await websocket.close(code=4003)
                return

            # Verify player is in this room
            room = db.query(GameSession).filter(GameSession.id == room_id).first()
            if not room or room.status != "WAITING" or player_id not in [str(p) for p in (room.players or [])]:
                player_id = None  # prevent finally block from running handle_leave
                await websocket.close(code=4004)
                return

            await lobby_manager.connect(room_id, player_id, websocket)

            # Broadcast full lobby state to all members
            lobby_payload = _build_lobby_payload(room, db)
            await lobby_manager.broadcast(room_id, {"type": "LOBBY_STATE", **lobby_payload})
        # DB session closed here — lobby is now live with no lingering connection

        # 방안 B: keep-alive loop with PING on timeout to detect zombie connections
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=PING_INTERVAL)
            except asyncio.TimeoutError:
                # No message from client for PING_INTERVAL seconds — send PING
                # If client is gone, the send raises WebSocketDisconnect → finally runs
                await websocket.send_text(json.dumps({"type": "PING"}))

    except WebSocketDisconnect:
        pass
    finally:
        if player_id:
            lobby_manager.disconnect(room_id, player_id)
            # 방안 C: fresh session for handle_leave — avoids stale long-lived session issues
            with SessionLocal() as leave_db:
                room = leave_db.query(GameSession).filter(GameSession.id == room_id).first()
                # 게임 시작 후 로비 소켓이 닫히는 것은 leave가 아니라 화면 전환이다.
                if room and room.status == "WAITING":
                    await handle_leave(room_id, player_id, leave_db, lobby_manager)
