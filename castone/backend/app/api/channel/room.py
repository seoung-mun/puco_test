from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from uuid import UUID

from app.dependencies import get_db
from app.schemas.game import GameRoomCreate, GameRoomResponse, JoinRoomRequest, RoomPlayerInfo
from app.services.game_service import GameService
from app.api.deps import get_current_user
from app.db.models import User, GameSession

MAX_PLAYERS = 3

router = APIRouter()


def _resolve_player_names(room: GameSession, db: Session) -> List[RoomPlayerInfo]:
    result = []
    for pid in (room.players or []):
        pid_str = str(pid)
        if pid_str.startswith("BOT_"):
            bot_type = pid_str.split("_", 1)[1].capitalize() if "_" in pid_str else "Bot"
            result.append(RoomPlayerInfo(display_name=bot_type, is_bot=True))
        else:
            user = db.query(User).filter(User.id == pid_str).first()
            name = (user.nickname or user.email or "Player") if user else "Player"
            result.append(RoomPlayerInfo(display_name=name, is_bot=False))
    return result


def _to_response(room: GameSession, db: Session) -> GameRoomResponse:
    return GameRoomResponse(
        id=room.id,
        title=room.title,
        status=room.status,
        is_private=room.is_private,
        current_players=len(room.players or []),
        max_players=MAX_PLAYERS,
        player_names=_resolve_player_names(room, db),
    )


@router.post("/", response_model=GameRoomResponse)
async def create_room(
    room_info: GameRoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Private room requires password
    if room_info.is_private and not room_info.password:
        raise HTTPException(status_code=400, detail="비밀방은 비밀번호가 필요합니다")

    # Case-insensitive title uniqueness check among WAITING rooms
    existing = db.query(GameSession).filter(
        func.lower(GameSession.title) == room_info.title.lower(),
        GameSession.status == "WAITING",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="이미 같은 이름의 방이 있습니다")

    room = GameSession(
        title=room_info.title,
        status="WAITING",
        num_players=MAX_PLAYERS,
        is_private=room_info.is_private,
        password=room_info.password if room_info.is_private else None,
        players=[str(current_user.id)],
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return _to_response(room, db)


@router.get("/", response_model=List[GameRoomResponse])
async def list_rooms(db: Session = Depends(get_db)):
    rooms = db.query(GameSession).filter(GameSession.status == "WAITING").order_by(GameSession.created_at.desc()).all()
    return [_to_response(r, db) for r in rooms]


@router.post("/{room_id}/join", response_model=GameRoomResponse)
async def join_room(
    room_id: UUID,
    body: JoinRoomRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(GameSession).filter(GameSession.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="방을 찾을 수 없습니다")
    if room.status != "WAITING":
        raise HTTPException(status_code=409, detail="이미 시작된 게임입니다")

    players = list(room.players or [])
    if len(players) >= MAX_PLAYERS:
        raise HTTPException(status_code=409, detail="방이 꽉 찼습니다")

    # Password check for private rooms
    if room.is_private:
        if not body.password or body.password != room.password:
            raise HTTPException(status_code=403, detail="비밀번호가 올바르지 않습니다")

    # Idempotent: already in room
    if str(current_user.id) in players:
        return _to_response(room, db)

    players.append(str(current_user.id))
    room.players = players
    db.commit()
    db.refresh(room)
    return _to_response(room, db)
