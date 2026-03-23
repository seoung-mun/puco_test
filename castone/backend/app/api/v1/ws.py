import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from sqlalchemy.orm import Session
from app.services.ws_manager import manager
from app.dependencies import get_db
from jose import jwt, JWTError
from app.core.security import SECRET_KEY, ALGORITHM
from app.db.models import User

router = APIRouter()

def get_ws_user(token: str, db: Session) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return db.query(User).filter(User.id == user_id).first()
    except JWTError:
        return None

@router.websocket("/{game_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    game_id: str,
    token: str = Query(None),
    db: Session = Depends(get_db)
):
    if not token:
        await websocket.close(code=1008)
        return

    user = get_ws_user(token, db)
    if not user:
        await websocket.close(code=1008)
        return

    player_id = str(user.id)
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
