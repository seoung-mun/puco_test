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

    await manager.connect(game_id, websocket)
    try:
        while True:
            # TDD: WebSocket Payload validation placeholder
            data = await websocket.receive_text()
            pass
    except WebSocketDisconnect:
        manager.disconnect(game_id, websocket)
