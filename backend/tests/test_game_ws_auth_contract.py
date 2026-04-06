import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token
from app.db.models import GameSession, User


class _SessionContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, exc_type, exc, tb):
        return False


def _session_local_factory(db):
    def _factory():
        return _SessionContext(db)

    return _factory


def _make_user(db, nickname: str) -> User:
    user = User(
        id=uuid.uuid4(),
        google_id=f"gid_{uuid.uuid4().hex}",
        nickname=nickname,
    )
    db.add(user)
    db.flush()
    return user


@pytest.mark.asyncio
async def test_game_ws_auth_ok_for_room_player(monkeypatch, db):
    from app.api.channel import ws as ws_module

    player = _make_user(db, "Player")
    room = GameSession(
        id=uuid.uuid4(),
        title="WS Room",
        status="PROGRESS",
        num_players=3,
        players=[str(player.id), "BOT_random", "BOT_random"],
        host_id=str(player.id),
    )
    db.add(room)
    db.flush()

    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.receive_json = AsyncMock(
        return_value={"token": create_access_token(subject=str(player.id))}
    )
    websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect(code=1000))
    websocket.send_json = AsyncMock()
    websocket.close = AsyncMock()

    connect_mock = AsyncMock()
    disconnect_mock = AsyncMock()
    monkeypatch.setattr(ws_module, "SessionLocal", _session_local_factory(db))
    monkeypatch.setattr(ws_module.manager, "connect", connect_mock)
    monkeypatch.setattr(ws_module.manager, "disconnect", disconnect_mock)

    await ws_module.websocket_endpoint(websocket, str(room.id))

    websocket.send_json.assert_awaited_once_with(
        {"type": "auth_ok", "player_id": str(player.id)}
    )
    connect_mock.assert_awaited_once_with(str(room.id), websocket, player_id=str(player.id))
    disconnect_mock.assert_awaited_once_with(str(room.id), websocket, player_id=str(player.id))


@pytest.mark.asyncio
async def test_game_ws_rejects_authenticated_stranger(monkeypatch, db):
    from app.api.channel import ws as ws_module

    host = _make_user(db, "Host")
    stranger = _make_user(db, "Stranger")
    room = GameSession(
        id=uuid.uuid4(),
        title="Private WS Room",
        status="PROGRESS",
        num_players=3,
        players=[str(host.id), "BOT_random", "BOT_random"],
        host_id=str(host.id),
    )
    db.add(room)
    db.flush()

    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.receive_json = AsyncMock(
        return_value={"token": create_access_token(subject=str(stranger.id))}
    )
    websocket.send_json = AsyncMock()
    websocket.close = AsyncMock()

    connect_mock = AsyncMock()
    monkeypatch.setattr(ws_module, "SessionLocal", _session_local_factory(db))
    monkeypatch.setattr(ws_module.manager, "connect", connect_mock)

    await ws_module.websocket_endpoint(websocket, str(room.id))

    websocket.send_json.assert_not_called()
    connect_mock.assert_not_awaited()
    websocket.close.assert_awaited_once_with(code=1008, reason="Forbidden")


@pytest.mark.asyncio
async def test_game_ws_allows_host_spectator_for_bot_only_game(monkeypatch, db):
    from app.api.channel import ws as ws_module

    host = _make_user(db, "SpectatorHost")
    room = GameSession(
        id=uuid.uuid4(),
        title="Bot Only WS Room",
        status="PROGRESS",
        num_players=3,
        players=["BOT_random", "BOT_ppo", "BOT_random"],
        host_id=str(host.id),
    )
    db.add(room)
    db.flush()

    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.receive_json = AsyncMock(
        return_value={"token": create_access_token(subject=str(host.id))}
    )
    websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect(code=1000))
    websocket.send_json = AsyncMock()
    websocket.close = AsyncMock()

    connect_mock = AsyncMock()
    disconnect_mock = AsyncMock()
    monkeypatch.setattr(ws_module, "SessionLocal", _session_local_factory(db))
    monkeypatch.setattr(ws_module.manager, "connect", connect_mock)
    monkeypatch.setattr(ws_module.manager, "disconnect", disconnect_mock)

    await ws_module.websocket_endpoint(websocket, str(room.id))

    websocket.send_json.assert_awaited_once_with(
        {"type": "auth_ok", "player_id": str(host.id)}
    )
    connect_mock.assert_awaited_once_with(str(room.id), websocket, player_id=str(host.id))
    disconnect_mock.assert_awaited_once_with(str(room.id), websocket, player_id=str(host.id))
