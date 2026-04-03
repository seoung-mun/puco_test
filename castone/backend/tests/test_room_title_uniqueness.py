"""
TDD: 방 제목 중복 제약 조건 검증

버그: ix_games_title_lower가 전역 unique index라서
FINISHED 상태 게임의 제목도 새 방 생성을 막음.
해결: Partial Unique Index (WHERE status = 'WAITING') 로 교체.
"""
import uuid
import pytest

from app.core.security import create_access_token
from app.db.models import User, GameSession


@pytest.fixture
def user_and_headers(db):
    user = User(id=uuid.uuid4(), google_id=f"gid_{uuid.uuid4().hex}", nickname="Tester1")
    db.add(user)
    db.flush()
    token = create_access_token(subject=str(user.id))
    return user, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user2_and_headers(db):
    user = User(id=uuid.uuid4(), google_id=f"gid_{uuid.uuid4().hex}", nickname="Tester2")
    db.add(user)
    db.flush()
    token = create_access_token(subject=str(user.id))
    return user, {"Authorization": f"Bearer {token}"}


def test_create_room_with_same_title_as_finished_game(client, db, user_and_headers, user2_and_headers):
    """FINISHED 상태 게임의 제목은 재사용할 수 있어야 한다."""
    _, headers1 = user_and_headers
    _, headers2 = user2_and_headers

    # 1. 방 생성
    res = client.post(
        "/api/puco/rooms/",
        json={"title": "reusable-title", "is_private": False},
        headers=headers1,
    )
    assert res.status_code == 200, res.text
    room_id = res.json()["id"]

    # 2. 게임 종료 상태로 변경 (DB 직접)
    game = db.query(GameSession).filter(GameSession.id == room_id).first()
    game.status = "FINISHED"
    db.commit()

    # 3. 다른 유저가 동일 제목으로 새 방 생성 → 200이어야 함 (현재: 500)
    res2 = client.post(
        "/api/puco/rooms/",
        json={"title": "reusable-title", "is_private": False},
        headers=headers2,
    )
    assert res2.status_code == 200, f"Expected 200 but got {res2.status_code}: {res2.text}"


def test_create_room_with_same_title_as_progress_game(client, db, user_and_headers, user2_and_headers):
    """PROGRESS 상태 게임의 제목도 재사용할 수 있어야 한다."""
    _, headers1 = user_and_headers
    _, headers2 = user2_and_headers

    res = client.post(
        "/api/puco/rooms/",
        json={"title": "in-progress-title", "is_private": False},
        headers=headers1,
    )
    assert res.status_code == 200, res.text
    room_id = res.json()["id"]

    game = db.query(GameSession).filter(GameSession.id == room_id).first()
    game.status = "PROGRESS"
    db.commit()

    res2 = client.post(
        "/api/puco/rooms/",
        json={"title": "in-progress-title", "is_private": False},
        headers=headers2,
    )
    assert res2.status_code == 200, f"Expected 200 but got {res2.status_code}: {res2.text}"


def test_cannot_create_room_with_same_title_as_waiting_room(client, db, user_and_headers, user2_and_headers):
    """WAITING 상태 방과 동일 제목은 409를 반환해야 한다 (기존 동작 유지)."""
    _, headers1 = user_and_headers
    _, headers2 = user2_and_headers

    res1 = client.post(
        "/api/puco/rooms/",
        json={"title": "unique-waiting-room", "is_private": False},
        headers=headers1,
    )
    assert res1.status_code == 200, res1.text

    res2 = client.post(
        "/api/puco/rooms/",
        json={"title": "unique-waiting-room", "is_private": False},
        headers=headers2,
    )
    assert res2.status_code == 409, f"Expected 409 but got {res2.status_code}: {res2.text}"


def test_title_uniqueness_is_case_insensitive_for_waiting_rooms(client, db, user_and_headers, user2_and_headers):
    """WAITING 방 제목 중복 검사는 대소문자를 구분하지 않아야 한다."""
    _, headers1 = user_and_headers
    _, headers2 = user2_and_headers

    res1 = client.post(
        "/api/puco/rooms/",
        json={"title": "MyRoom", "is_private": False},
        headers=headers1,
    )
    assert res1.status_code == 200, res1.text

    res2 = client.post(
        "/api/puco/rooms/",
        json={"title": "myroom", "is_private": False},
        headers=headers2,
    )
    assert res2.status_code == 409, f"Expected 409 but got {res2.status_code}: {res2.text}"
