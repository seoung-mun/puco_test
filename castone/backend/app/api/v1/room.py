from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.dependencies import get_db
from app.schemas.game import GameRoomCreate, GameRoomResponse
from app.services.game_service import GameService

router = APIRouter()

@router.post("/", response_model=GameRoomResponse)
async def create_room(room_info: GameRoomCreate, db: Session = Depends(get_db)):
    service = GameService(db)
    room = service.create_room(room_info)
    return GameRoomResponse(
        id=room.id,
        title=room.title,
        status=room.status,
        current_players=0,
        max_players=room.num_players
    )

@router.get("/", response_model=List[GameRoomResponse])
async def list_rooms(db: Session = Depends(get_db)):
    service = GameService(db)
    rooms = service.get_room_list()
    return [
        GameRoomResponse(
            id=r.id,
            title=r.title,
            status=r.status,
            current_players=0,
            max_players=r.num_players
        ) for r in rooms
    ]
