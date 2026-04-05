"""
Integration tests for:
- POST /api/puco/rooms/{id}/leave
- POST /api/puco/rooms/ host uniqueness restriction
"""
import uuid
import pytest


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
