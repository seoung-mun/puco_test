from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import GameSession, User
from app.dependencies import get_db

router = APIRouter()


@router.get("/active-game")
async def get_active_game(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    active_rooms = (
        db.query(GameSession)
        .filter(GameSession.status.in_(("WAITING", "PROGRESS", "RECOVERY_BLOCKED")))
        .order_by(GameSession.updated_at.desc(), GameSession.created_at.desc())
        .all()
    )

    current_user_id = str(current_user.id)
    for room in active_rooms:
        players = [str(player) for player in (room.players or [])]
        is_host = str(room.host_id) == current_user_id
        is_player = current_user_id in players
        if not (is_host or is_player):
            continue
        return {
            "has_active_game": True,
            "game_id": str(room.id),
            "status": room.status,
            "is_host": is_host,
            "is_player": is_player,
        }

    return {"has_active_game": False}
