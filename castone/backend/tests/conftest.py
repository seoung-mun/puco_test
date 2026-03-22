import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from unittest.mock import MagicMock

from app.main import app
from app.dependencies import get_db
from app.db.models import Base

# Use a test database or a different schema
# For this example, we'll use the same DB but could be configured via env
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://puco_user:puco_password@localhost:5432/puco_rl")

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session")
def db_engine():
    Base.metadata.create_all(bind=engine)
    yield engine
    # Base.metadata.drop_all(bind=engine) # Optional: clean up after all tests

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
def client(db, monkeypatch):
    # Mock Redis
    mock_redis = MagicMock()
    # Patch the global redis_client in game_service
    # It's already initialized, so we MUST patch the instance or the reference in the module
    monkeypatch.setattr("app.services.game_service.redis_client", mock_redis)
    # Also patch the class/method just in case of other uses
    monkeypatch.setattr("redis.from_url", lambda *args, **kwargs: mock_redis)

    def override_get_db():
        try:
            yield db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
