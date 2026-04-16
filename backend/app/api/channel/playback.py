import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.dependencies import get_db
from app.api.deps import get_current_user
from app.db.models import User, GameSession
from app.schemas.playback import PlaybackState, SpeedRequest, PauseRequest
from app.services.game_service import GameService

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_bot_game(db: Session, game_id: UUID) -> GameSession:
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room or room.status != "PROGRESS":
        raise HTTPException(status_code=404, detail="Game not found or not in progress")
    players = room.players or []
    if not all(str(p).startswith("BOT_") for p in players):
        raise HTTPException(status_code=403, detail="speed_control_bot_game_only")
    return room


@router.get("/{game_id}/playback", response_model=PlaybackState)
def get_playback(
    game_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_bot_game(db, game_id)
    return PlaybackState(
        speed=GameService.get_game_speed(game_id),
        paused=GameService.get_game_paused(game_id),
    )


@router.post("/{game_id}/speed")
def set_speed(
    game_id: UUID,
    body: SpeedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_bot_game(db, game_id)
    GameService.set_game_speed(game_id, body.speed)
    return {"speed": body.speed}


@router.post("/{game_id}/pause")
def set_pause(
    game_id: UUID,
    body: PauseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_bot_game(db, game_id)
    GameService.set_game_paused(game_id, body.paused)
    if not body.paused:
        _try_resume_bot(game_id, db)
    return {"paused": body.paused}


def _try_resume_bot(game_id: UUID, db: Session):
    """When unpausing, schedule the next bot turn if one is pending."""
    engine = GameService.active_engines.get(game_id)
    if not engine:
        return
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        return
    service = GameService(db)
    service._schedule_next_bot_turn_if_needed(game_id, room, engine)
