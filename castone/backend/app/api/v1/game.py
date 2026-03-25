from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.dependencies import get_db
from app.schemas.game import GameAction
from app.services.game_service import GameService
from app.api.deps import get_current_user
from app.db.models import User, GameSession

router = APIRouter()

@router.post("/{game_id}/start")
async def start_game(
    game_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # IDOR: verify caller is a player in this game
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Game not found")
    if str(current_user.id) not in (room.players or []):
        raise HTTPException(status_code=403, detail="You are not a player in this game")

    service = GameService(db)
    try:
        result = service.start_game(game_id)
        return {"status": "started", "state": result["state"], "action_mask": result["action_mask"]}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/{game_id}/action")
async def perform_action(
    game_id: UUID,
    action_data: GameAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # IDOR: verify caller is a player in this game
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Game not found")
    if str(current_user.id) not in (room.players or []):
        raise HTTPException(status_code=403, detail="You are not a player in this game")

    actor_id = str(current_user.id)
    service = GameService(db)
    try:
        action_int = action_data.payload.get("action_index")
        if action_int is None:
            raise HTTPException(status_code=400, detail="action_index is required in payload")

        result = service.process_action(game_id, actor_id, action_int)
        return {"status": "success", "state": result["state"], "action_mask": result["action_mask"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
