"""
TDD: Channel API 봇 관리 엔드포인트

POST /api/puco/game/{id}/add-bot
DELETE /api/puco/game/{id}/bots/{slot_index}
  - 게임 생성자(첫 번째 플레이어)가 빈 슬롯에 봇을 추가/삭제할 수 있어야 한다.
  - 인증 없이는 401을 반환해야 한다.
  - 이미 게임이 시작된 경우 409를 반환해야 한다.
  - 슬롯이 꽉 찬 경우 409를 반환해야 한다.
"""
import uuid

import pytest

from app.core.security import create_access_token
from app.db.models import GameSession, User


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _make_user(db, nickname="Host"):
    uid = uuid.uuid4()
    user = User(id=uid, google_id=f"gid_{uuid.uuid4().hex}", nickname=nickname)
    db.add(user)
    return uid


def _make_room(db, host_id, num_players=3, status="WAITING", players=None):
    gid = uuid.uuid4()
    if players is None:
        players = [str(host_id)]
    room = GameSession(
        id=gid,
        title="Bot Test Room",
        status=status,
        num_players=num_players,
        players=players,
        host_id=str(host_id),
    )
    db.add(room)
    db.flush()
    return gid


def _auth(user_id):
    return {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}


# ------------------------------------------------------------------ #
#  Feature 1: 인증 검사                                               #
# ------------------------------------------------------------------ #

class TestAddBotAuth:

    def test_add_bot_requires_auth(self, client, db):
        """인증 없이 POST하면 401이어야 한다."""
        host_id = _make_user(db)
        gid = _make_room(db, host_id)
        res = client.post(f"/api/puco/game/{gid}/add-bot", json={"bot_type": "random"})
        assert res.status_code == 401, f"expected 401, got {res.status_code}"

    def test_add_bot_requires_membership(self, client, db):
        """게임에 속하지 않은 유저가 봇 추가하면 403이어야 한다."""
        host_id = _make_user(db, "Host")
        stranger_id = _make_user(db, "Stranger")
        gid = _make_room(db, host_id)
        res = client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(stranger_id),
        )
        assert res.status_code == 403, f"expected 403, got {res.status_code}"

    def test_add_bot_requires_host_privileges(self, client, db):
        """방 참가자여도 방장이 아니면 봇을 추가할 수 없어야 한다."""
        host_id = _make_user(db, "Host")
        member_id = _make_user(db, "Member")
        gid = _make_room(
            db,
            host_id,
            players=[str(host_id), str(member_id)],
        )
        res = client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(member_id),
        )
        assert res.status_code == 403, f"expected 403, got {res.status_code}: {res.text}"
        assert "host" in res.json()["detail"].lower()


# ------------------------------------------------------------------ #
#  Feature 2: 정상 추가                                               #
# ------------------------------------------------------------------ #

class TestAddBotSuccess:

    def test_add_bot_returns_200(self, client, db):
        """빈 슬롯이 있는 대기 중인 방에 봇 추가 → 200."""
        host_id = _make_user(db)
        gid = _make_room(db, host_id, num_players=3)
        res = client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(host_id),
        )
        assert res.status_code == 200, res.text

    def test_add_bot_updates_players_list(self, client, db):
        """봇 추가 후 room.players 길이가 1 증가해야 한다."""
        host_id = _make_user(db)
        gid = _make_room(db, host_id, num_players=3)
        client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(host_id),
        )
        from app.db.models import GameSession
        room = db.query(GameSession).filter(GameSession.id == gid).first()
        assert len(room.players) == 2, f"expected 2 players, got {len(room.players)}"

    def test_add_bot_player_id_has_bot_prefix(self, client, db):
        """추가된 봇의 player ID는 'BOT_' 접두사를 가져야 한다."""
        host_id = _make_user(db)
        gid = _make_room(db, host_id, num_players=3)
        client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(host_id),
        )
        from app.db.models import GameSession
        room = db.query(GameSession).filter(GameSession.id == gid).first()
        bot_entries = [p for p in room.players if str(p).startswith("BOT_")]
        assert len(bot_entries) == 1, f"expected 1 BOT_ entry, got {bot_entries}"

    def test_add_bot_response_contains_slot_index(self, client, db):
        """응답에 bot이 추가된 slot_index가 있어야 한다."""
        host_id = _make_user(db)
        gid = _make_room(db, host_id, num_players=3)
        res = client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(host_id),
        )
        body = res.json()
        assert "slot_index" in body, f"slot_index 없음. 응답: {body}"
        assert body["slot_index"] == 1, f"첫 번째 봇은 슬롯 1에 추가돼야 함. 실제: {body['slot_index']}"


# ------------------------------------------------------------------ #
#  Feature 3: 오류 케이스                                             #
# ------------------------------------------------------------------ #

class TestAddBotErrors:

    def test_add_bot_to_full_room_returns_409(self, client, db):
        """이미 슬롯이 꽉 찬 경우 409를 반환해야 한다."""
        host_id = _make_user(db)
        gid = _make_room(
            db, host_id, num_players=3,
            players=[str(host_id), "BOT_random", "BOT_random"],
        )
        res = client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(host_id),
        )
        assert res.status_code == 409, f"expected 409, got {res.status_code}: {res.text}"

    def test_add_bot_to_in_progress_game_returns_409(self, client, db):
        """게임이 이미 시작된 경우 409를 반환해야 한다."""
        host_id = _make_user(db)
        gid = _make_room(db, host_id, num_players=3, status="PROGRESS")
        res = client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(host_id),
        )
        assert res.status_code == 409, f"expected 409, got {res.status_code}: {res.text}"

    def test_add_bot_to_nonexistent_game_returns_404(self, client, db):
        """존재하지 않는 게임 ID → 404."""
        host_id = _make_user(db)
        db.flush()
        res = client.post(
            f"/api/puco/game/{uuid.uuid4()}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(host_id),
        )
        assert res.status_code == 404, f"expected 404, got {res.status_code}"

    def test_add_bot_default_type_is_random(self, client, db):
        """bot_type을 생략하면 random으로 추가돼야 한다."""
        host_id = _make_user(db)
        gid = _make_room(db, host_id, num_players=3)
        res = client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={},
            headers=_auth(host_id),
        )
        assert res.status_code == 200, res.text
        from app.db.models import GameSession
        room = db.query(GameSession).filter(GameSession.id == gid).first()
        assert any(str(p) == "BOT_random" for p in room.players)

    def test_add_bot_rejects_unknown_bot_type(self, client, db):
        """등록되지 않은 bot_type은 400으로 거절되어야 한다."""
        host_id = _make_user(db)
        gid = _make_room(db, host_id, num_players=3)
        res = client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "gpt4"},
            headers=_auth(host_id),
        )
        assert res.status_code == 400, res.text
        assert "Unknown bot type" in res.json()["detail"]


class TestRemoveBot:

    def test_remove_bot_requires_auth(self, client, db):
        host_id = _make_user(db)
        gid = _make_room(db, host_id, players=[str(host_id), "BOT_random"])
        res = client.delete(f"/api/puco/game/{gid}/bots/1")
        assert res.status_code == 401, f"expected 401, got {res.status_code}"

    def test_remove_bot_requires_host_privileges(self, client, db):
        host_id = _make_user(db, "Host")
        member_id = _make_user(db, "Member")
        gid = _make_room(db, host_id, players=[str(host_id), str(member_id), "BOT_random"])
        res = client.delete(
            f"/api/puco/game/{gid}/bots/2",
            headers=_auth(member_id),
        )
        assert res.status_code == 403, f"expected 403, got {res.status_code}: {res.text}"

    def test_remove_bot_returns_200(self, client, db):
        host_id = _make_user(db)
        gid = _make_room(db, host_id, players=[str(host_id), "BOT_random"])
        res = client.delete(
            f"/api/puco/game/{gid}/bots/1",
            headers=_auth(host_id),
        )
        assert res.status_code == 200, res.text

    def test_remove_bot_updates_players_list(self, client, db):
        host_id = _make_user(db)
        gid = _make_room(db, host_id, players=[str(host_id), "BOT_random", "BOT_ppo"])
        client.delete(
            f"/api/puco/game/{gid}/bots/1",
            headers=_auth(host_id),
        )
        room = db.query(GameSession).filter(GameSession.id == gid).first()
        assert room is not None
        assert list(room.players) == [str(host_id), "BOT_ppo"]

    def test_remove_bot_then_add_bot_succeeds(self, client, db):
        host_id = _make_user(db)
        gid = _make_room(db, host_id, players=[str(host_id), "BOT_random", "BOT_ppo"])

        remove_res = client.delete(
            f"/api/puco/game/{gid}/bots/1",
            headers=_auth(host_id),
        )
        assert remove_res.status_code == 200, remove_res.text

        add_res = client.post(
            f"/api/puco/game/{gid}/add-bot",
            json={"bot_type": "random"},
            headers=_auth(host_id),
        )
        assert add_res.status_code == 200, add_res.text

    def test_remove_bot_from_in_progress_game_returns_409(self, client, db):
        host_id = _make_user(db)
        gid = _make_room(db, host_id, status="PROGRESS", players=[str(host_id), "BOT_random"])
        res = client.delete(
            f"/api/puco/game/{gid}/bots/1",
            headers=_auth(host_id),
        )
        assert res.status_code == 409, f"expected 409, got {res.status_code}: {res.text}"

    def test_remove_bot_from_nonexistent_game_returns_404(self, client, db):
        host_id = _make_user(db)
        res = client.delete(
            f"/api/puco/game/{uuid.uuid4()}/bots/1",
            headers=_auth(host_id),
        )
        assert res.status_code == 404, f"expected 404, got {res.status_code}"

    def test_remove_bot_rejects_human_slot(self, client, db):
        host_id = _make_user(db)
        gid = _make_room(db, host_id, players=[str(host_id), str(uuid.uuid4()), "BOT_random"])
        res = client.delete(
            f"/api/puco/game/{gid}/bots/1",
            headers=_auth(host_id),
        )
        assert res.status_code == 400, f"expected 400, got {res.status_code}: {res.text}"

    def test_remove_bot_rejects_invalid_slot(self, client, db):
        host_id = _make_user(db)
        gid = _make_room(db, host_id, players=[str(host_id), "BOT_random"])
        res = client.delete(
            f"/api/puco/game/{gid}/bots/9",
            headers=_auth(host_id),
        )
        assert res.status_code == 404, f"expected 404, got {res.status_code}: {res.text}"
