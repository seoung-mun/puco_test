import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.game_service import GameService


def test_sync_to_redis_skips_direct_broadcast_when_redis_publish_succeeds(monkeypatch):
    service = GameService(db=MagicMock())
    fake_redis = MagicMock()
    fake_loop = MagicMock()
    fake_loop.create_task.side_effect = lambda coro: coro.close()

    monkeypatch.setattr("app.services.game_service.redis_client", fake_redis)
    monkeypatch.setattr("app.services.game_service.manager", SimpleNamespace(broadcast_to_game=AsyncMock()))
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: fake_loop)

    service._sync_to_redis("game-1", {"meta": {"phase": "role_selection"}})

    fake_redis.publish.assert_called_once()
    fake_loop.create_task.assert_not_called()


def test_sync_to_redis_falls_back_to_direct_broadcast_when_redis_publish_fails(monkeypatch):
    service = GameService(db=MagicMock())
    fake_redis = MagicMock()
    fake_redis.set.side_effect = RuntimeError("redis down")
    fake_loop = MagicMock()
    fake_loop.create_task.side_effect = lambda coro: coro.close()

    monkeypatch.setattr("app.services.game_service.redis_client", fake_redis)
    monkeypatch.setattr("app.services.game_service.manager", SimpleNamespace(broadcast_to_game=AsyncMock()))
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: fake_loop)

    service._sync_to_redis("game-2", {"meta": {"phase": "role_selection"}})

    fake_loop.create_task.assert_called_once()
