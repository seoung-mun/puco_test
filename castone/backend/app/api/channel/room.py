from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from uuid import UUID, uuid4

from app.dependencies import get_db, get_current_user
from app.schemas.game import (
    BotGameCreateRequest,
    GameRoomCreate,
    GameRoomResponse,
    JoinRoomRequest,
    RoomPlayerInfo,
)
from app.services.game_service import GameService
from app.db.models import User, GameSession
from app.services.lobby_manager import lobby_manager, handle_leave
from app.services.agent_registry import make_bot_player_id, normalize_bot_types, resolve_bot_type_from_actor_id

MAX_PLAYERS = 3

router = APIRouter()


def _resolve_player_names(room: GameSession, db: Session) -> List[RoomPlayerInfo]:
    result = []
    for pid in (room.players or []):
        pid_str = str(pid)
        if pid_str.startswith("BOT_"):
            bot_type = resolve_bot_type_from_actor_id(pid_str).capitalize()
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

    # Block if already hosting a WAITING room
    existing_host = db.query(GameSession).filter(
        GameSession.host_id == str(current_user.id),
        GameSession.status == "WAITING",
    ).first()
    if existing_host:
        raise HTTPException(status_code=409, detail="이미 방장인 방이 있습니다")

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
        host_id=str(current_user.id),
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


@router.post("/bot-game")
async def create_bot_game(
    body: BotGameCreateRequest = BotGameCreateRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """봇×3 관전 게임 즉시 생성 및 시작. 사용자는 host_id만 가지며 관전자로 참여."""
    # Block if already hosting a WAITING room
    existing_host = db.query(GameSession).filter(
        GameSession.host_id == str(current_user.id),
        GameSession.status == "WAITING",
    ).first()
    if existing_host:
        raise HTTPException(status_code=409, detail="이미 방장인 방이 있습니다")

    try:
        bot_types = normalize_bot_types(body.bot_types, max_players=MAX_PLAYERS)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    room = GameSession(
        id=uuid4(),
        title=f"{current_user.nickname}의 봇전",
        status="WAITING",
        num_players=3,
        is_private=False,
        players=[make_bot_player_id(bot_type) for bot_type in bot_types],
        host_id=str(current_user.id),
    )
    db.add(room)
    db.commit()
    db.refresh(room)

    service = GameService(db)
    try:
        result = service.start_game(room.id)
    except ValueError as e:
        db.delete(room)
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    return {"game_id": str(room.id), "state": result["state"]}


@router.post("/{room_id}/leave")
async def leave_room(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(GameSession).filter(GameSession.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="방을 찾을 수 없습니다")
    await handle_leave(str(room_id), str(current_user.id), db, lobby_manager)
    return {"status": "ok"}
