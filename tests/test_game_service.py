import pytest
import uuid
import asyncio

from app.services.game_service import GameService
from app.db.models import GameSession
from app.schemas.game import GameRoomCreate

class MockQuery:
    def __init__(self, saved):
        self.saved = saved
    def filter(self, *args, **kwargs):
        return self
    def first(self):
        return self.saved[0] if self.saved else None

@pytest.fixture
def mock_db():
    class MockDB:
        def __init__(self):
            self.saved = []
        def add(self, entity):
            self.saved.append(entity)
        def commit(self):
            pass
        def refresh(self, entity):
            pass
        def query(self, model):
            return MockQuery(self.saved)
    return MockDB()

@pytest.fixture
def mock_redis():
    class MockRedis:
        def __init__(self):
            self.published = []
        def publish(self, channel, message):
            self.published.append((channel, message))
    return MockRedis()

@pytest.mark.asyncio
async def test_create_and_start_room(mock_db):
    # RED -> GREEN: Can we create a room and initialize early engine states?
    service = GameService(mock_db)
    
    room_id = service.create_room(GameRoomCreate(title="Test", max_players=3)).id
    assert isinstance(room_id, uuid.UUID), "Should return a valid UUID"
    
    # We need to manually call start_game to trigger Active Engines mapping
    service.start_game(room_id)
    
    # Check Active Engines map
    engine = GameService.active_engines.get(room_id)
    assert engine is not None, "Engine should be immediately instantiated upon room creation"
    
    # Assert DB object creation
    assert len(mock_db.saved) == 1

@pytest.mark.asyncio
async def test_process_action_validation(mock_db):
    # RED -> GREEN: Turn Spoofing defense
    service = GameService(mock_db)
    # We must properly format the room creation structure
    room = GameRoomCreate(title="Defense Test", max_players=3)
    room_id = service.create_room(room).id
    service.start_game(room_id)
    
    # In a fresh game before start_game, no actions are masked initially until initialization triggers wait states
    # Or in our engine wrapper, phase 9 (INIT) requires start_game to move to Phase 0
    engine = GameService.active_engines[room_id]
    
    # Test valid action vs invalid action bounds
    current_mask = engine.get_action_mask()
    valid_actions = [i for i, v in enumerate(current_mask) if v]
    invalid_actions = [i for i, v in enumerate(current_mask) if not v]
    
    if invalid_actions:
        invalid_action = invalid_actions[0]
        with pytest.raises(ValueError, match="is invalid for the current state"):
            service.process_action(room_id, actor_id="user123", action=invalid_action)
