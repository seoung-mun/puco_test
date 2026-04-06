"""
TDD tests for /health endpoint:
- Returns 200 with {"status": "ok"} when DB and Redis are healthy
- Returns 503 with {"status": "degraded"} when PostgreSQL is down
- Returns 503 with {"status": "degraded"} when Redis is down
- Response includes per-service check results
"""
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy.exc import OperationalError


class TestHealthEndpointSuccess:
    def test_health_returns_200_when_all_services_ok(self, client):
        """Health endpoint must return 200 when PostgreSQL and Redis are both up."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_status_is_ok_when_all_services_ok(self, client):
        """Health response body must have status='ok' when all services are healthy."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "ok"

    def test_health_includes_postgresql_check(self, client):
        """Health response must include 'postgresql' in checks."""
        response = client.get("/health")
        data = response.json()
        assert "checks" in data
        assert "postgresql" in data["checks"]

    def test_health_includes_redis_check(self, client):
        """Health response must include 'redis' in checks."""
        response = client.get("/health")
        data = response.json()
        assert "checks" in data
        assert "redis" in data["checks"]

    def test_health_postgresql_check_is_ok(self, client):
        """PostgreSQL check value must be 'ok' when DB is healthy."""
        response = client.get("/health")
        assert response.json()["checks"]["postgresql"] == "ok"

    def test_health_redis_check_is_ok(self, client):
        """Redis check value must be 'ok' when Redis is healthy."""
        response = client.get("/health")
        assert response.json()["checks"]["redis"] == "ok"


class TestHealthEndpointDegraded:
    def test_health_returns_503_when_postgresql_down(self, client, monkeypatch):
        """Health endpoint must return 503 when PostgreSQL is unreachable."""
        def bad_session():
            mock = MagicMock()
            mock.__enter__ = MagicMock(side_effect=OperationalError(
                "connection refused", None, None
            ))
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        monkeypatch.setattr("app.main.SessionLocal", bad_session)
        response = client.get("/health")
        assert response.status_code == 503

    def test_health_status_degraded_when_postgresql_down(self, client, monkeypatch):
        """Health response must have status='degraded' when PostgreSQL is down."""
        def bad_session():
            mock = MagicMock()
            mock.__enter__ = MagicMock(side_effect=OperationalError(
                "connection refused", None, None
            ))
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        monkeypatch.setattr("app.main.SessionLocal", bad_session)
        response = client.get("/health")
        assert response.json()["status"] == "degraded"

    def test_health_returns_503_when_redis_down(self, client, monkeypatch):
        """Health endpoint must return 503 when Redis is unreachable."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("Redis down"))
        monkeypatch.setattr("app.main.async_redis_client", mock_redis)

        response = client.get("/health")
        assert response.status_code == 503

    def test_health_postgresql_check_shows_error_message(self, client, monkeypatch):
        """When PostgreSQL is down, postgresql check must show error string."""
        def bad_session():
            mock = MagicMock()
            mock.__enter__ = MagicMock(side_effect=OperationalError(
                "connection refused", None, None
            ))
            mock.__exit__ = MagicMock(return_value=False)
            return mock

        monkeypatch.setattr("app.main.SessionLocal", bad_session)
        response = client.get("/health")
        checks = response.json()["checks"]
        assert "error" in checks["postgresql"].lower()

    def test_health_redis_check_shows_error_message(self, client, monkeypatch):
        """When Redis is down, redis check must show error string."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("Redis connection refused"))
        monkeypatch.setattr("app.main.async_redis_client", mock_redis)

        response = client.get("/health")
        checks = response.json()["checks"]
        assert "error" in checks["redis"].lower()

    def test_health_postgresql_ok_redis_down_returns_503(self, client, monkeypatch):
        """Even if only Redis is down, /health must return 503."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("down"))
        monkeypatch.setattr("app.main.async_redis_client", mock_redis)

        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["checks"]["postgresql"] == "ok"
        assert "error" in data["checks"]["redis"].lower()
