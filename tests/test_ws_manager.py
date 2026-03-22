import pytest
from app.services.ws_manager import ConnectionManager
from fastapi import WebSocket

class MockWebSocket:
    def __init__(self):
        self.accepted = False
        self.closed = False
        self.close_code = None
        self.sent_messages = []

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000):
        self.closed = True
        self.close_code = code

    async def send_json(self, data):
        self.sent_messages.append(data)

    async def send_text(self, data):
        self.sent_messages.append(data)

@pytest.mark.asyncio
async def test_connection_manager_connect():
    # Verify ConnectionManager accepts and adds connections
    manager = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    
    room_id = "test-room"
    
    await manager.connect(room_id, ws1)
    assert ws1.accepted
    assert ws1 in manager.active_connections[room_id]
    
    await manager.connect(room_id, ws2)
    assert len(manager.active_connections[room_id]) == 2
    
    # Broadcast isolation check
    await manager.broadcast_to_game(room_id, {"type": "TEST"})
    assert len(ws1.sent_messages) == 1
    assert len(ws2.sent_messages) == 1
    assert "TEST" in ws1.sent_messages[0]

@pytest.mark.asyncio
async def test_connection_manager_disconnect():
    manager = ConnectionManager()
    ws1 = MockWebSocket()
    room_id = "test-room"
    
    await manager.connect(room_id, ws1)
    manager.disconnect(room_id, ws1)
    
    assert not manager.active_connections.get(room_id)
