import uuid

from unittest.mock import AsyncMock

import pytest

from app.core.security import create_access_token
from app.db.models import GameSession, User
from app.services.serving_health import ServingHealth


def _make_user(db, nickname="ActiveGameUser"):
    user = User(
        id=uuid.uuid4(),
        google_id=f"active_game_gid_{uuid.uuid4().hex}",
        nickname=nickname,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture(autouse=True)
def _mock_startup_health(monkeypatch):
    mock_async_redis = AsyncMock()
    mock_async_redis.ping.return_value = True
    monkeypatch.setattr("app.main.async_redis_client", mock_async_redis)
    monkeypatch.setattr(
        "app.main.validate_serving_health",
        lambda: ServingHealth(
            ok=True,
            bot_type="ppo",
            source="bundle_v2",
            artifact_name="ppo-pr-server-semantic293-20260419",
            detail=None,
        ),
    )


def test_active_game_session_returns_waiting_room_for_host(client, db):
    host = _make_user(db, "Host")
    room = GameSession(
        id=uuid.uuid4(),
        title="Waiting Room",
        status="WAITING",
        num_players=3,
        players=[str(host.id)],
        host_id=str(host.id),
    )
    db.add(room)
    db.commit()

    headers = {"Authorization": f"Bearer {create_access_token(subject=str(host.id))}"}
    response = client.get("/api/puco/session/active-game", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "has_active_game": True,
        "game_id": str(room.id),
        "status": "WAITING",
        "is_host": True,
        "is_player": True,
    }


def test_active_game_session_returns_progress_game_for_spectator_host(client, db):
    host = _make_user(db, "Host")
    room = GameSession(
        id=uuid.uuid4(),
        title="Bot Spectator Game",
        status="PROGRESS",
        num_players=3,
        players=["BOT_random", "BOT_random", "BOT_random"],
        host_id=str(host.id),
    )
    db.add(room)
    db.commit()

    headers = {"Authorization": f"Bearer {create_access_token(subject=str(host.id))}"}
    response = client.get("/api/puco/session/active-game", headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "has_active_game": True,
        "game_id": str(room.id),
        "status": "PROGRESS",
        "is_host": True,
        "is_player": False,
    }


def test_active_game_session_returns_no_active_game_when_user_has_none(client, db):
    user = _make_user(db, "Viewer")
    other = _make_user(db, "Other")
    room = GameSession(
        id=uuid.uuid4(),
        title="Other Room",
        status="WAITING",
        num_players=3,
        players=[str(other.id)],
        host_id=str(other.id),
    )
    db.add(room)
    db.commit()

    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    response = client.get("/api/puco/session/active-game", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"has_active_game": False}
