"""
TDD tests for startup ghost-room cleanup logic.
"""
import uuid
import pytest
from app.db.models import GameSession, User


def _make_user(db, nickname="User"):
    u = User(
        id=str(uuid.uuid4()),
        google_id=str(uuid.uuid4()),
        email=f"{nickname}@test.com",
        nickname=nickname,
    )
    db.add(u)
    db.flush()
    return u


def _make_room(db, host_user, players, status="WAITING"):
    room = GameSession(
        id=uuid.uuid4(),
        title=f"Room-{uuid.uuid4().hex[:4]}",
        status=status,
        num_players=3,
        is_private=False,
        players=players,
        host_id=str(host_user.id),
    )
    db.add(room)
    db.flush()
    return room


class TestStartupCleanup:

    def test_host_only_room_is_deleted(self, db):
        """사람이 방장만 있는 방 → 삭제"""
        from app.services.startup_cleanup import cleanup_stale_rooms
        host = _make_user(db, "Host")
        room = _make_room(db, host, [str(host.id)])

        cleanup_stale_rooms(db)

        assert db.query(GameSession).filter(GameSession.id == room.id).first() is None

    def test_host_plus_bots_room_is_deleted(self, db):
        """방장 + 봇만 있는 방 → 삭제 (현재 고스트 방 케이스)"""
        from app.services.startup_cleanup import cleanup_stale_rooms
        host = _make_user(db, "Host")
        room = _make_room(db, host, [str(host.id), "BOT_random", "BOT_ppo"])

        cleanup_stale_rooms(db)

        assert db.query(GameSession).filter(GameSession.id == room.id).first() is None

    def test_host_plus_human_room_transfers_host(self, db):
        """방장 + 다른 사람 플레이어가 있는 방 → 방장 이전, 방 유지"""
        from app.services.startup_cleanup import cleanup_stale_rooms
        host = _make_user(db, "Host")
        other = _make_user(db, "Other")
        room = _make_room(db, host, [str(host.id), str(other.id)])

        cleanup_stale_rooms(db)

        db.refresh(room)
        assert db.query(GameSession).filter(GameSession.id == room.id).first() is not None
        assert str(room.host_id) == str(other.id)
        assert str(host.id) not in [str(p) for p in room.players]

    def test_host_plus_human_and_bots_transfers_host(self, db):
        """방장 + 사람 + 봇 구성 → 방장 이전, 봇 유지, 방 유지"""
        from app.services.startup_cleanup import cleanup_stale_rooms
        host = _make_user(db, "Host")
        other = _make_user(db, "Other")
        room = _make_room(db, host, [str(host.id), str(other.id), "BOT_random"])

        cleanup_stale_rooms(db)

        db.refresh(room)
        assert db.query(GameSession).filter(GameSession.id == room.id).first() is not None
        assert str(room.host_id) == str(other.id)
        assert "BOT_random" in [str(p) for p in room.players]

    def test_progress_room_is_not_touched(self, db):
        """PROGRESS 방은 건드리지 않음"""
        from app.services.startup_cleanup import cleanup_stale_rooms
        host = _make_user(db, "Host")
        room = _make_room(db, host, [str(host.id), "BOT_random"], status="PROGRESS")

        cleanup_stale_rooms(db)

        assert db.query(GameSession).filter(GameSession.id == room.id).first() is not None

    def test_empty_room_is_deleted(self, db):
        """players가 비어있는 방 → 삭제"""
        from app.services.startup_cleanup import cleanup_stale_rooms
        host = _make_user(db, "Host")
        room = _make_room(db, host, [])

        cleanup_stale_rooms(db)

        assert db.query(GameSession).filter(GameSession.id == room.id).first() is None

    def test_host_id_none_room_is_deleted(self, db):
        """host_id가 None인 방 → 삭제"""
        from app.services.startup_cleanup import cleanup_stale_rooms
        host = _make_user(db, "Host")
        room = _make_room(db, host, ["BOT_random"])
        room.host_id = None
        db.flush()

        cleanup_stale_rooms(db)

        assert db.query(GameSession).filter(GameSession.id == room.id).first() is None
