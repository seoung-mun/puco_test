"""
TDD tests for LobbyConnectionManager and handle_leave logic.
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services.lobby_manager import LobbyConnectionManager, handle_leave


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def manager():
    return LobbyConnectionManager()


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.fixture
def mock_db():
    return MagicMock()


# ── LobbyConnectionManager ────────────────────────────────────────────

class TestLobbyConnectionManager:

    @pytest.mark.asyncio
    async def test_connect_registers_websocket(self, manager, mock_ws):
        room_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        await manager.connect(room_id, player_id, mock_ws)
        assert player_id in manager.connections.get(room_id, {})

    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket(self, manager, mock_ws):
        room_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        await manager.connect(room_id, player_id, mock_ws)
        manager.disconnect(room_id, player_id)
        assert player_id not in manager.connections.get(room_id, {})

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_in_room(self, manager):
        room_id = str(uuid.uuid4())
        ws1, ws2 = AsyncMock(), AsyncMock()
        p1, p2 = str(uuid.uuid4()), str(uuid.uuid4())
        await manager.connect(room_id, p1, ws1)
        await manager.connect(room_id, p2, ws2)
        await manager.broadcast(room_id, {"type": "LOBBY_UPDATE"})
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_skips_room_with_no_connections(self, manager):
        await manager.broadcast("nonexistent-room", {"type": "LOBBY_UPDATE"})

    @pytest.mark.asyncio
    async def test_close_all_sends_room_deleted_and_cleans_up(self, manager):
        room_id = str(uuid.uuid4())
        ws = AsyncMock()
        await manager.connect(room_id, str(uuid.uuid4()), ws)
        await manager.close_all(room_id)
        ws.send_text.assert_called_once()
        payload = json.loads(ws.send_text.call_args[0][0])
        assert payload["type"] == "ROOM_DELETED"
        assert room_id not in manager.connections

    @pytest.mark.asyncio
    async def test_broadcast_game_started_sends_to_all_in_room(self, manager):
        room_id = str(uuid.uuid4())
        ws1, ws2 = AsyncMock(), AsyncMock()
        p1, p2 = str(uuid.uuid4()), str(uuid.uuid4())
        await manager.connect(room_id, p1, ws1)
        await manager.connect(room_id, p2, ws2)
        game_state = {"board": [], "current_player": 0}
        await manager.broadcast_game_started(room_id, game_state)
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
        payload = json.loads(ws1.send_text.call_args[0][0])
        assert payload["type"] == "GAME_STARTED"
        assert payload["state"] == game_state

    @pytest.mark.asyncio
    async def test_broadcast_game_started_noop_when_no_connections(self, manager):
        # Should not raise even when no clients connected
        await manager.broadcast_game_started("nonexistent-room", {})


# ── handle_leave ──────────────────────────────────────────────────────

class TestHandleLeave:

    def _make_room(self, players, host_id=None):
        from app.db.models import GameSession
        room = MagicMock(spec=GameSession)
        room.players = list(players)
        room.host_id = host_id or players[0]
        room.id = uuid.uuid4()
        room.status = "WAITING"
        return room

    def _mock_db_with_room(self, mock_db, room):
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = room

    @pytest.mark.asyncio
    async def test_last_human_leaves_deletes_room(self, mock_db):
        player_id = str(uuid.uuid4())
        room = self._make_room([player_id, "BOT_random"])
        self._mock_db_with_room(mock_db, room)
        mgr = LobbyConnectionManager()
        await handle_leave(str(room.id), player_id, mock_db, mgr)
        mock_db.delete.assert_called_once_with(room)
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_host_leaves_waiting_room_deletes_room(self, mock_db):
        host_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        room = self._make_room([host_id, other_id], host_id=host_id)
        room.status = "WAITING"
        self._mock_db_with_room(mock_db, room)
        mgr = LobbyConnectionManager()
        
        # In this scenario, the room should be deleted because host left a WAITING room
        await handle_leave(str(room.id), host_id, mock_db, mgr)
        
        mock_db.delete.assert_called_once_with(room)
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_host_leaves_progress_room_transfers_host(self, mock_db):
        host_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        room = self._make_room([host_id, other_id], host_id=host_id)
        room.status = "PROGRESS"
        self._mock_db_with_room(mock_db, room)
        mgr = LobbyConnectionManager()
        
        await handle_leave(str(room.id), host_id, mock_db, mgr)
        
        assert room.host_id == other_id
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_non_host_leaves_room_updated(self, mock_db):
        host_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        room = self._make_room([host_id, other_id], host_id=host_id)
        self._mock_db_with_room(mock_db, room)
        mgr = LobbyConnectionManager()
        await handle_leave(str(room.id), other_id, mock_db, mgr)
        assert other_id not in room.players
        assert room.host_id == host_id
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_leave_nonexistent_room_is_noop(self, mock_db):
        mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None
        mgr = LobbyConnectionManager()
        await handle_leave(str(uuid.uuid4()), str(uuid.uuid4()), mock_db, mgr)

    @pytest.mark.asyncio
    async def test_player_not_in_room_is_noop(self, mock_db):
        host_id = str(uuid.uuid4())
        room = self._make_room([host_id])
        self._mock_db_with_room(mock_db, room)
        mgr = LobbyConnectionManager()
        await handle_leave(str(room.id), str(uuid.uuid4()), mock_db, mgr)
        assert room.players == [host_id]
