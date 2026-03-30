import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.services.ws_manager import manager
from app.dependencies import SessionLocal
import jwt
from app.core.security import SECRET_KEY, ALGORITHM
from app.db.models import User

router = APIRouter()


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

    # Task 0.4: first-message JWT auth (token not in URL)
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        token = auth_msg.get("token") or auth_msg.get("accessToken")
        if not token:
            await websocket.close(code=1008, reason="Token required")
            return
    except asyncio.TimeoutError:
        await websocket.close(code=1008, reason="Auth timeout")
        return
    except Exception:
        await websocket.close(code=1008, reason="Invalid auth message")
        return

    with SessionLocal() as db:
        user = _get_ws_user(token, db)

    if not user:
        await websocket.close(code=1008, reason="Invalid token")
        return

    player_id = str(user.id)
    await websocket.send_json({"type": "auth_ok", "player_id": player_id})

    await manager.connect(game_id, websocket, player_id=player_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await manager.handle_client_message(game_id, player_id, message)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await manager.disconnect(game_id, websocket, player_id=player_id)
