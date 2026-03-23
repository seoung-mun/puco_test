import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.dependencies import get_db
from app.db.models import Base

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://puco_user:puco_password@localhost:5432/puco_rl")

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session")
def db_engine():
    Base.metadata.create_all(bind=engine)
    yield engine


@pytest.fixture(scope="function")
def db(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def mock_sync_redis():
    """Sync Redis mock for game_service."""
    mock = MagicMock()
    mock.set.return_value = True
    mock.get.return_value = None
    mock.publish.return_value = 1
    mock.hset.return_value = 1
    mock.hgetall.return_value = {}
    mock.hget.return_value = None
    mock.expire.return_value = True
    mock.ping.return_value = True
    return mock


@pytest.fixture(scope="function")
def mock_async_redis():
    """Async Redis mock for ws_manager and main.py health check."""
    mock = AsyncMock()
    mock.ping.return_value = True
    mock.hset.return_value = 1
    mock.hgetall.return_value = {}
    mock.hget.return_value = None
    mock.expire.return_value = True
    mock.pubsub.return_value = AsyncMock()
    return mock


@pytest.fixture(scope="function")
def client(db, monkeypatch, mock_sync_redis, mock_async_redis):
    # Patch sync Redis client used by game_service
    monkeypatch.setattr("app.services.game_service.redis_client", mock_sync_redis)
    # Patch async Redis client used by ws_manager and main.py
    monkeypatch.setattr("app.core.redis.async_redis_client", mock_async_redis)
    monkeypatch.setattr("app.services.ws_manager.manager.redis", mock_async_redis)
    # Patch sync Redis client used by main.py health check (via app.core.redis)
    monkeypatch.setattr("app.core.redis.sync_redis_client", mock_sync_redis)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
