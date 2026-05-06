import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models import GameSession, User
from app.services.game_service import GameService
from app.services.serving_health import ServingHealth


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


def _make_user(db, nickname="RuntimeHealthUser"):
    user = User(
        id=uuid.uuid4(),
        google_id=f"runtime_health_gid_{uuid.uuid4().hex}",
        nickname=nickname,
    )
    db.add(user)
    db.flush()
    return user


def _healthy_serving_health() -> ServingHealth:
    return ServingHealth(
        ok=True,
        bot_type="ppo",
        source="bundle_v2",
        artifact_name="ppo-pr-server-semantic293-20260419",
        detail=None,
    )


def _seed_baseline_progress_engines(
    db,
    *,
    exclude_game_ids: set[uuid.UUID] | None = None,
) -> None:
    excluded = exclude_game_ids or set()
    progress_game_ids = [
        game_id
        for (game_id,) in db.query(GameSession.id)
        .filter(GameSession.status == "PROGRESS")
        .all()
    ]
    for game_id in progress_game_ids:
        if game_id in excluded:
            continue
        GameService.active_engines[game_id] = object()


@pytest.fixture(autouse=True)
def _mock_startup_health(monkeypatch):
    mock_async_redis = AsyncMock()
    mock_async_redis.ping.return_value = True
    monkeypatch.setattr("app.main.async_redis_client", mock_async_redis)
    monkeypatch.setattr(
        "app.main.validate_serving_health",
        _healthy_serving_health,
    )


@pytest.fixture(autouse=True)
def _reset_game_service_runtime_state():
    GameService.active_engines.clear()
    GameService._bot_tasks.clear()
    GameService._bot_stall_watchdogs.clear()
    yield
    GameService.active_engines.clear()
    GameService._bot_tasks.clear()
    GameService._bot_stall_watchdogs.clear()


def test_runtime_health_returns_ok_with_runtime_counts(client, db, monkeypatch):
    monkeypatch.setattr("app.main.SessionLocal", _session_local_factory(db))
    monkeypatch.setattr(
        "app.main.validate_serving_health",
        _healthy_serving_health,
    )
    GameService._bot_tasks.clear()
    GameService._bot_stall_watchdogs.clear()
    GameService.active_engines.clear()
    _seed_baseline_progress_engines(db)

    response = client.get("/health/runtime")
    data = response.json()

    assert response.status_code == 200
    assert data["checks"] == {
        "postgresql": "ok",
        "redis": "ok",
        "serving": {
            "status": "ok",
            "artifact_name": "ppo-pr-server-semantic293-20260419",
            "metadata_source": "bundle_v2",
        },
    }
    assert data["runtime"] == {
        "progress_games_without_engine": 0,
        "running_bot_tasks": 0,
        "active_bot_stall_watchdogs": 0,
    }
    assert data["status"] == "ok"


def test_runtime_health_degrades_when_progress_game_has_no_engine(client, db, monkeypatch):
    host = _make_user(db, "Host")
    room = GameSession(
        id=uuid.uuid4(),
        title="Stalled Progress Room",
        status="PROGRESS",
        num_players=3,
        players=[str(host.id), "BOT_random", "BOT_random"],
        host_id=str(host.id),
    )
    db.add(room)
    db.commit()

    monkeypatch.setattr("app.main.SessionLocal", _session_local_factory(db))
    monkeypatch.setattr(
        "app.main.validate_serving_health",
        _healthy_serving_health,
    )
    GameService.active_engines.clear()
    GameService._bot_tasks.clear()
    GameService._bot_stall_watchdogs.clear()
    _seed_baseline_progress_engines(db, exclude_game_ids={room.id})

    response = client.get("/health/runtime")

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "degraded"
    assert data["runtime"]["progress_games_without_engine"] == 1


def test_runtime_health_degrades_when_runtime_dependencies_fail(client, db, monkeypatch):
    monkeypatch.setattr("app.main.SessionLocal", _session_local_factory(db))
    broken_redis = AsyncMock()
    broken_redis.ping = AsyncMock(side_effect=ConnectionError("redis down"))
    monkeypatch.setattr("app.main.async_redis_client", broken_redis)
    monkeypatch.setattr(
        "app.main.validate_serving_health",
        lambda: ServingHealth(
            ok=False,
            bot_type="ppo",
            source="bundle_v2",
            artifact_name="ppo-pr-server-semantic293-20260419",
            detail="bundle missing",
        ),
    )

    running_bot_task = MagicMock()
    running_bot_task.done.return_value = False
    watchdog_task = MagicMock()
    watchdog_task.done.return_value = False
    GameService._bot_tasks = {uuid.uuid4(): running_bot_task}
    GameService._bot_stall_watchdogs = {"watchdog": watchdog_task}
    GameService.active_engines.clear()

    response = client.get("/health/runtime")

    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "degraded"
    assert data["checks"]["postgresql"] == "ok"
    assert "error:" in data["checks"]["redis"]
    assert data["checks"]["serving"]["status"] == "degraded"
    assert data["checks"]["serving"]["detail"] == "bundle missing"
    assert data["runtime"]["running_bot_tasks"] == 1
    assert data["runtime"]["active_bot_stall_watchdogs"] == 1
