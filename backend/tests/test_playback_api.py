"""TDD: Playback speed/pause API endpoints for bot-only spectator games."""
import uuid
import pytest
from app.core.security import create_access_token
from app.db.models import GameSession, User
from app.services.game_service import GameService


def _make_user(db, nickname="Tester"):
    uid = uuid.uuid4()
    user = User(id=uid, google_id=f"gid_{uuid.uuid4().hex}", nickname=nickname)
    db.add(user)
    return uid


def _make_bot_game(db, host_id, status="PROGRESS"):
    gid = uuid.uuid4()
    room = GameSession(
        id=gid,
        title="Bot Speed Test",
        status="WAITING" if status == "PROGRESS" else status,
        num_players=3,
        players=["BOT_ppo", "BOT_random", "BOT_random"],
        host_id=str(host_id),
    )
    db.add(room)
    db.flush()
    if status == "PROGRESS":
        GameService(db).start_game(gid)
    return gid


def _make_human_game(db, host_id, status="PROGRESS"):
    gid = uuid.uuid4()
    room = GameSession(
        id=gid,
        title="Human Game",
        status=status,
        num_players=3,
        players=[str(host_id), "BOT_random", "BOT_random"],
        host_id=str(host_id),
    )
    db.add(room)
    db.flush()
    return gid


def _auth(user_id):
    return {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}


class TestPlaybackRequiresAuth:
    def test_get_playback_requires_auth(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.get(f"/api/puco/games/{gid}/playback")
        assert res.status_code == 401

    def test_speed_requires_auth(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(f"/api/puco/games/{gid}/speed", json={"speed": 2})
        assert res.status_code == 401

    def test_pause_requires_auth(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(f"/api/puco/games/{gid}/pause", json={"paused": True})
        assert res.status_code == 401


class TestSpeedChangeBotGameOnly:
    def test_speed_change_human_game_returns_403(self, client, db):
        uid = _make_user(db)
        gid = _make_human_game(db, uid)
        res = client.post(
            f"/api/puco/games/{gid}/speed",
            json={"speed": 2},
            headers=_auth(uid),
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "speed_control_bot_game_only"


class TestSpeedInvalidValue:
    def test_speed_invalid_value_422(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(
            f"/api/puco/games/{gid}/speed",
            json={"speed": 3},
            headers=_auth(uid),
        )
        assert res.status_code == 422


class TestSpeedChangeAccepted:
    def test_speed_change_to_2(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(
            f"/api/puco/games/{gid}/speed",
            json={"speed": 2},
            headers=_auth(uid),
        )
        assert res.status_code == 200
        assert res.json()["speed"] == 2


class TestSpeedCycles:
    def test_speed_cycles_1_2_4(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        headers = _auth(uid)
        for spd in [1, 2, 4, 1]:
            client.post(f"/api/puco/games/{gid}/speed", json={"speed": spd}, headers=headers)
            res = client.get(f"/api/puco/games/{gid}/playback", headers=headers)
            assert res.json()["speed"] == spd


class TestPause:
    def test_pause_accepted(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(
            f"/api/puco/games/{gid}/pause",
            json={"paused": True},
            headers=_auth(uid),
        )
        assert res.status_code == 200
        assert res.json()["paused"] is True

    def test_resume_accepted(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        headers = _auth(uid)
        client.post(f"/api/puco/games/{gid}/pause", json={"paused": True}, headers=headers)
        res = client.post(f"/api/puco/games/{gid}/pause", json={"paused": False}, headers=headers)
        assert res.status_code == 200
        assert res.json()["paused"] is False


class TestGetPlayback:
    def test_get_playback_default(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.get(f"/api/puco/games/{gid}/playback", headers=_auth(uid))
        assert res.status_code == 200
        data = res.json()
        assert data["speed"] == 1
        assert data["paused"] is False

    def test_get_playback_after_change(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        headers = _auth(uid)
        client.post(f"/api/puco/games/{gid}/speed", json={"speed": 4}, headers=headers)
        client.post(f"/api/puco/games/{gid}/pause", json={"paused": True}, headers=headers)
        res = client.get(f"/api/puco/games/{gid}/playback", headers=headers)
        data = res.json()
        assert data["speed"] == 4
        assert data["paused"] is True


class TestNonexistentGame:
    def test_nonexistent_game_404(self, client, db):
        uid = _make_user(db)
        fake_id = uuid.uuid4()
        res = client.get(f"/api/puco/games/{fake_id}/playback", headers=_auth(uid))
        assert res.status_code == 404
