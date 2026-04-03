import json
import logging
from typing import Dict

from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.db.models import GameSession

logger = logging.getLogger(__name__)


class LobbyConnectionManager:
    def __init__(self):
        # room_id -> { player_id -> WebSocket }
        self.connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, room_id: str, player_id: str, ws: WebSocket) -> None:
        if room_id not in self.connections:
            self.connections[room_id] = {}
        self.connections[room_id][player_id] = ws
        logger.info("Lobby WS connected: room=%s player=%s", room_id, player_id)

    def disconnect(self, room_id: str, player_id: str) -> None:
        if room_id in self.connections:
            self.connections[room_id].pop(player_id, None)
            if not self.connections[room_id]:
                del self.connections[room_id]
        logger.info("Lobby WS disconnected: room=%s player=%s", room_id, player_id)

    async def broadcast(self, room_id: str, message: dict) -> None:
        conns = self.connections.get(room_id, {})
        text = json.dumps(message)
        dead = []
        for player_id, ws in list(conns.items()):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(player_id)
        for pid in dead:
            conns.pop(pid, None)
        if dead:
            logger.debug("Removed %d dead lobby sockets for room %s", len(dead), room_id)
        if room_id in self.connections and not self.connections[room_id]:
            del self.connections[room_id]

    async def close_all(self, room_id: str) -> None:
        """Send ROOM_DELETED to all members and clean up."""
        await self.broadcast(room_id, {"type": "ROOM_DELETED"})
        self.connections.pop(room_id, None)

    async def broadcast_game_started(self, room_id: str, game_state: dict) -> None:
        """Send GAME_STARTED to all lobby members so they transition to the game screen."""
        await self.broadcast(room_id, {"type": "GAME_STARTED", "state": game_state})


def _count_humans(players: list[str]) -> int:
    return sum(1 for p in players if not str(p).startswith("BOT_"))


def _build_lobby_payload(room: GameSession, db: Session) -> dict:
    from app.db.models import User
    players_out = []
    for idx, raw_pid in enumerate(room.players or []):
        pid = str(raw_pid)
        if pid.startswith("BOT_"):
            bot_type = pid[4:]
            players_out.append({
                "name": f"Bot ({bot_type})",
                "player_id": f"BOT_{bot_type}_{idx}",
                "is_bot": True,
                "is_host": False,
                "connected": True,
            })
        else:
            user = db.query(User).filter(User.id == pid).first()
            name = str(user.nickname) if (user and isinstance(user.nickname, str)) else pid[:8]
            players_out.append({
                "name": name,
                "player_id": pid,
                "is_bot": False,
                "is_host": (pid == str(room.host_id)),
                "connected": True,
            })
    return {"players": players_out, "host_id": str(room.host_id) if room.host_id else None}


async def handle_leave(
    room_id: str,
    player_id: str,
    db: Session,
    manager: "LobbyConnectionManager",
) -> None:
    """Shared leave logic for both WS disconnect and explicit /leave endpoint."""
    room = (
        db.query(GameSession)
        .filter(GameSession.id == room_id)
        .with_for_update()
        .first()
    )
    if room is None:
        return

    # 게임이 진행 중이면 로비 떠남 처리를 하지 않음 (lobby WS disconnect는 게임 시작 시 정상적으로 발생)
    if room.status != "WAITING":
        return

    players = [str(p) for p in (room.players or [])]
    if player_id not in players:
        return  # idempotent

    # Check if host is leaving
    is_host_leaving = (str(room.host_id) == player_id)

    players.remove(player_id)
    room.players = players

    human_count = _count_humans(players)

    # 1. If no humans left, delete room
    # 2. If host leaves a WAITING room, delete it (prevents ghost rooms)
    if human_count == 0 or is_host_leaving:
        db.delete(room)
        db.commit()
        await manager.close_all(room_id)
        logger.info("Room %s deleted (host left or no humans left)", room_id)
        return

    # If host leaves an active game, transfer host (though lobby_ws only handles WAITING)
    if is_host_leaving:
        new_host = next((p for p in players if not p.startswith("BOT_")), None)
        room.host_id = new_host

    db.commit()
    db.refresh(room)

    payload = _build_lobby_payload(room, db)
    await manager.broadcast(room_id, {"type": "LOBBY_UPDATE", **payload})


# Singleton used by the WS endpoint and leave endpoint
lobby_manager = LobbyConnectionManager()
