from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.dependencies import get_db
from app.schemas.game import GameAction
from app.services.game_service import GameService
from app.api.deps import get_current_user
from app.db.models import User

router = APIRouter()

@router.post("/{game_id}/start")
async def start_game(
    game_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    actor_id = str(current_user.id)
    
    service = GameService(db)
    try:
        # Action is expected to be an integer based on PuCo_RL action space
        # payload might contain additional info but PuCo_RL uses discrete action ints
        action_int = action_data.payload.get("action_index")
        if action_int is None:
            raise HTTPException(status_code=400, detail="action_index is required in payload")
            
        result = service.process_action(game_id, actor_id, action_int)
        return {"status": "success", "state": result["state"], "action_mask": result["action_mask"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
