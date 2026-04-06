"""
Integration tests for:
- POST /api/puco/rooms/{id}/leave
- POST /api/puco/rooms/ host uniqueness restriction
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect


def _create_user(db, nickname="Alice"):
    from app.db.models import User
    u = User(
        id=str(uuid.uuid4()),
        google_id=str(uuid.uuid4()),
        email=f"{nickname}@test.com",
        nickname=nickname,
    )
    db.add(u)
    db.flush()
    return u


def _create_room_for(db, host_user):
    from app.db.models import GameSession
    room = GameSession(
        id=uuid.uuid4(),
        title=f"Room-{uuid.uuid4().hex[:4]}",
        status="WAITING",
        num_players=3,
        is_private=False,
        players=[str(host_user.id)],
        host_id=str(host_user.id),
    )
    db.add(room)
    db.flush()
    return room


@pytest.fixture
def alice(db):
    return _create_user(db, "Alice")


@pytest.fixture
def bob(db):
    return _create_user(db, "Bob")


class TestLeaveEndpoint:

    def test_leave_removes_player_from_room(self, client, db, alice, bob):
        from app.main import app
        from app.dependencies import get_current_user
        room = _create_room_for(db, alice)
        room.players = [str(alice.id), str(bob.id)]
        db.flush()

        app.dependency_overrides[get_current_user] = lambda: bob
        res = client.post(f"/api/puco/rooms/{room.id}/leave")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        db.refresh(room)
        assert str(bob.id) not in [str(p) for p in room.players]

    def test_leave_transfers_host_when_host_exits_progress_room(self, client, db, alice, bob):
        from app.main import app
        from app.dependencies import get_current_user
        room = _create_room_for(db, alice)
        room.players = [str(alice.id), str(bob.id)]
        room.status = "PROGRESS"
        db.flush()

        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post(f"/api/puco/rooms/{room.id}/leave")
        assert res.status_code == 200
        db.refresh(room)
        assert str(room.host_id) == str(bob.id)

    def test_leave_host_deletes_waiting_room(self, client, db, alice, bob):
        from app.main import app
        from app.dependencies import get_current_user
        from app.db.models import GameSession
        room = _create_room_for(db, alice)
        room.players = [str(alice.id), str(bob.id)]
        db.flush()
        room_id = room.id

        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post(f"/api/puco/rooms/{room_id}/leave")
        assert res.status_code == 200
        assert db.query(GameSession).filter(GameSession.id == room_id).first() is None

    def test_leave_nonexistent_room_returns_404(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post(f"/api/puco/rooms/{uuid.uuid4()}/leave")
        assert res.status_code == 404

    def test_leave_idempotent_when_not_in_room(self, client, db, alice, bob):
        from app.main import app
        from app.dependencies import get_current_user
        room = _create_room_for(db, alice)
        app.dependency_overrides[get_current_user] = lambda: bob  # bob not in room
        res = client.post(f"/api/puco/rooms/{room.id}/leave")
        assert res.status_code == 200  # idempotent


class TestHostCreationRestriction:

    def test_cannot_create_second_room_as_host(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        _create_room_for(db, alice)
        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post("/api/puco/rooms/", json={"title": "Another Room"})
        assert res.status_code == 409
        assert "방장" in res.json()["detail"]

    def test_can_create_room_when_no_waiting_room_as_host(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        room = _create_room_for(db, alice)
        room.status = "FINISHED"
        db.flush()
        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post("/api/puco/rooms/", json={"title": "New Room"})
        assert res.status_code == 200


class TestBotGame:

    def test_create_bot_game_returns_200(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post("/api/puco/rooms/bot-game")
        assert res.status_code == 200

    def test_create_bot_game_players_are_all_bots(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        from app.db.models import GameSession
        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post("/api/puco/rooms/bot-game")
        assert res.status_code == 200
        game_id = res.json()["game_id"]
        room = db.query(GameSession).filter(GameSession.id == game_id).first()
        assert room is not None
        assert all(str(p).startswith("BOT_") for p in room.players)
        assert len(room.players) == 3

    def test_create_bot_game_host_is_creator(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        from app.db.models import GameSession
        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post("/api/puco/rooms/bot-game")
        assert res.status_code == 200
        game_id = res.json()["game_id"]
        room = db.query(GameSession).filter(GameSession.id == game_id).first()
        assert str(room.host_id) == str(alice.id)

    def test_create_bot_game_status_is_progress(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        from app.db.models import GameSession
        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post("/api/puco/rooms/bot-game")
        assert res.status_code == 200
        game_id = res.json()["game_id"]
        room = db.query(GameSession).filter(GameSession.id == game_id).first()
        assert room.status == "PROGRESS"

    def test_create_bot_game_response_has_state(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post("/api/puco/rooms/bot-game")
        assert res.status_code == 200
        data = res.json()
        assert "game_id" in data
        assert "state" in data

    def test_create_bot_game_accepts_explicit_bot_types(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        from app.db.models import GameSession

        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post(
            "/api/puco/rooms/bot-game",
            json={"bot_types": ["ppo", "random", "ppo"]},
        )
        assert res.status_code == 200, res.text

        game_id = res.json()["game_id"]
        room = db.query(GameSession).filter(GameSession.id == game_id).first()
        assert room is not None
        assert list(room.players) == ["BOT_ppo", "BOT_random", "BOT_ppo"]

    def test_create_bot_game_rejects_unknown_bot_type(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post(
            "/api/puco/rooms/bot-game",
            json={"bot_types": ["random", "gpt4", "ppo"]},
        )
        assert res.status_code == 400
        assert "Unknown bot type" in res.json()["detail"]

    def test_create_bot_game_defaults_to_three_random_bots_with_empty_body(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        from app.db.models import GameSession

        app.dependency_overrides[get_current_user] = lambda: alice
        res = client.post("/api/puco/rooms/bot-game", json={})
        assert res.status_code == 200, res.text

        game_id = res.json()["game_id"]
        room = db.query(GameSession).filter(GameSession.id == game_id).first()
        assert room is not None
        assert list(room.players) == ["BOT_random", "BOT_random", "BOT_random"]


class TestAddBotBroadcast:

    def test_add_bot_broadcasts_lobby_update(self, client, db, alice, bob):
        """봇 추가 후 같은 방 WS 클라이언트 전체에 LOBBY_UPDATE가 전송되어야 한다."""
        from app.main import app
        from app.dependencies import get_current_user
        from app.services.lobby_manager import lobby_manager
        from unittest.mock import AsyncMock, patch
        import json

        room = _create_room_for(db, alice)
        db.flush()

        # Mock lobby_manager.broadcast to capture calls
        broadcast_calls = []
        original_broadcast = lobby_manager.broadcast

        async def capturing_broadcast(room_id, message):
            broadcast_calls.append((room_id, message))
            return await original_broadcast(room_id, message)

        with patch.object(lobby_manager, 'broadcast', side_effect=capturing_broadcast):
            app.dependency_overrides[get_current_user] = lambda: alice
            res = client.post(f"/api/puco/game/{room.id}/add-bot", json={"bot_type": "random"})

        assert res.status_code == 200
        lobby_updates = [m for (_, m) in broadcast_calls if m.get("type") == "LOBBY_UPDATE"]
        assert len(lobby_updates) >= 1, "add-bot 후 LOBBY_UPDATE가 브로드캐스트되어야 합니다"


class TestStartGame:

    def test_non_host_cannot_start_game(self, client, db, alice, bob):
        from app.main import app
        from app.dependencies import get_current_user
        room = _create_room_for(db, alice)
        room.players = [str(alice.id), str(bob.id)]
        db.flush()

        app.dependency_overrides[get_current_user] = lambda: bob  # bob is NOT host
        res = client.post(f"/api/puco/game/{room.id}/start")
        assert res.status_code == 403

    def test_host_can_start_game(self, client, db, alice):
        from app.main import app
        from app.dependencies import get_current_user
        room = _create_room_for(db, alice)
        room.players = [str(alice.id), "BOT_random", "BOT_random"]
        db.flush()

        app.dependency_overrides[get_current_user] = lambda: alice  # alice IS host
        res = client.post(f"/api/puco/game/{room.id}/start")
        assert res.status_code != 403


class _SessionContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, exc_type, exc, tb):
        return False


def _session_local_factory(*dbs):
    db_iter = iter(dbs)

    def _factory():
        return _SessionContext(next(db_iter))

    return _factory


class TestLobbyWebSocketCleanup:

    @pytest.mark.asyncio
    async def test_started_room_disconnect_skips_leave_cleanup(self, monkeypatch):
        from app.api.channel import lobby_ws as lobby_ws_module

        room_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        websocket = MagicMock()
        websocket.accept = AsyncMock()
        websocket.receive_text = AsyncMock(
            side_effect=[json.dumps({"token": "test-token"}), WebSocketDisconnect(code=1000)]
        )
        websocket.send_text = AsyncMock()
        websocket.close = AsyncMock()

        setup_room = MagicMock()
        setup_room.status = "WAITING"
        setup_room.players = [player_id]

        leave_room = MagicMock()
        leave_room.status = "PROGRESS"
        leave_room.players = [player_id]

        setup_db = MagicMock()
        setup_db.query.return_value.filter.return_value.first.return_value = setup_room

        leave_db = MagicMock()
        leave_db.query.return_value.filter.return_value.first.return_value = leave_room

        monkeypatch.setattr(
            lobby_ws_module,
            "SessionLocal",
            _session_local_factory(setup_db, leave_db),
        )
        monkeypatch.setattr(
            lobby_ws_module,
            "decode_access_token",
            lambda token: {"sub": player_id},
        )
        monkeypatch.setattr(
            lobby_ws_module,
            "_build_lobby_payload",
            lambda room, db: {"players": [], "host_id": player_id},
        )

        connect_mock = AsyncMock()
        broadcast_mock = AsyncMock()
        disconnect_mock = MagicMock()
        handle_leave_mock = AsyncMock()

        monkeypatch.setattr(lobby_ws_module.lobby_manager, "connect", connect_mock)
        monkeypatch.setattr(lobby_ws_module.lobby_manager, "broadcast", broadcast_mock)
        monkeypatch.setattr(lobby_ws_module.lobby_manager, "disconnect", disconnect_mock)
        monkeypatch.setattr(lobby_ws_module, "handle_leave", handle_leave_mock)

        await lobby_ws_module.lobby_websocket(room_id, websocket)

        connect_mock.assert_awaited_once()
        broadcast_mock.assert_awaited_once()
        disconnect_mock.assert_called_once_with(room_id, player_id)
        handle_leave_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_waiting_room_disconnect_still_runs_leave_cleanup(self, monkeypatch):
        from app.api.channel import lobby_ws as lobby_ws_module

        room_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        websocket = MagicMock()
        websocket.accept = AsyncMock()
        websocket.receive_text = AsyncMock(
            side_effect=[json.dumps({"token": "test-token"}), WebSocketDisconnect(code=1000)]
        )
        websocket.send_text = AsyncMock()
        websocket.close = AsyncMock()

        room = MagicMock()
        room.status = "WAITING"
        room.players = [player_id]

        setup_db = MagicMock()
        setup_db.query.return_value.filter.return_value.first.return_value = room

        leave_db = MagicMock()
        leave_db.query.return_value.filter.return_value.first.return_value = room

        monkeypatch.setattr(
            lobby_ws_module,
            "SessionLocal",
            _session_local_factory(setup_db, leave_db),
        )
        monkeypatch.setattr(
            lobby_ws_module,
            "decode_access_token",
            lambda token: {"sub": player_id},
        )
        monkeypatch.setattr(
            lobby_ws_module,
            "_build_lobby_payload",
            lambda room, db: {"players": [], "host_id": player_id},
        )

        monkeypatch.setattr(lobby_ws_module.lobby_manager, "connect", AsyncMock())
        monkeypatch.setattr(lobby_ws_module.lobby_manager, "broadcast", AsyncMock())
        monkeypatch.setattr(lobby_ws_module.lobby_manager, "disconnect", MagicMock())
        handle_leave_mock = AsyncMock()
        monkeypatch.setattr(lobby_ws_module, "handle_leave", handle_leave_mock)

        await lobby_ws_module.lobby_websocket(room_id, websocket)

        handle_leave_mock.assert_awaited_once_with(
            room_id,
            player_id,
            leave_db,
            lobby_ws_module.lobby_manager,
        )


class TestLobbyWebSocketAuthContract:

    @pytest.mark.asyncio
    async def test_missing_lobby_ws_token_closes_with_auth_error(self, monkeypatch):
        from app.api.channel import lobby_ws as lobby_ws_module

        room_id = str(uuid.uuid4())
        websocket = MagicMock()
        websocket.accept = AsyncMock()
        websocket.receive_text = AsyncMock(return_value=json.dumps({}))
        websocket.close = AsyncMock()

        connect_mock = AsyncMock()
        monkeypatch.setattr(lobby_ws_module.lobby_manager, "connect", connect_mock)

        await lobby_ws_module.lobby_websocket(room_id, websocket)

        connect_mock.assert_not_awaited()
        websocket.close.assert_awaited_once_with(code=4003)

    @pytest.mark.asyncio
    async def test_player_not_in_waiting_room_is_rejected(self, monkeypatch):
        from app.api.channel import lobby_ws as lobby_ws_module

        room_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        other_player_id = str(uuid.uuid4())

        websocket = MagicMock()
        websocket.accept = AsyncMock()
        websocket.receive_text = AsyncMock(
            return_value=json.dumps({"token": "valid-token"})
        )
        websocket.close = AsyncMock()

        room = MagicMock()
        room.status = "WAITING"
        room.players = [other_player_id]
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = room

        monkeypatch.setattr(lobby_ws_module, "SessionLocal", _session_local_factory(db))
        monkeypatch.setattr(lobby_ws_module, "decode_access_token", lambda token: {"sub": player_id})
        connect_mock = AsyncMock()
        monkeypatch.setattr(lobby_ws_module.lobby_manager, "connect", connect_mock)

        await lobby_ws_module.lobby_websocket(room_id, websocket)

        connect_mock.assert_not_awaited()
        websocket.close.assert_awaited_once_with(code=4004)
