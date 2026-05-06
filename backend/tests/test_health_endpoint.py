"""Contract tests for the lightweight liveness endpoint."""

from unittest.mock import AsyncMock

import pytest

from app.services.serving_health import ServingHealth


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


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")

        assert response.status_code == 200

    def test_health_reports_only_liveness_checks(self, client):
        response = client.get("/health")

        data = response.json()
        assert data["status"] == "ok"
        assert data["checks"] == {
            "process": "ok",
            "event_loop": "ok",
        }

    def test_health_stays_ok_without_touching_runtime_dependencies(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.main.SessionLocal",
            lambda: (_ for _ in ()).throw(AssertionError("liveness must not touch DB")),
        )
        monkeypatch.setattr(
            "app.main.async_redis_client",
            type("BrokenRedis", (), {"ping": lambda self: (_ for _ in ()).throw(AssertionError("liveness must not touch Redis"))})(),
        )

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_handler_reports_event_loop_ok_when_called_in_request_context(self, client):
        response = client.get("/health")

        assert response.json()["checks"]["event_loop"] == "ok"
