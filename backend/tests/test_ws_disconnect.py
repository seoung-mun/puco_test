"""
TDD tests for WebSocket disconnect and timeout logic in ws_manager.py:
- connect() updates Redis player status to 'connected'
- connect() cancels any existing disconnect timer
- disconnect() updates Redis player status to 'disconnected'
- disconnect() broadcasts PLAYER_DISCONNECTED event to remaining players
- END_GAME_REQUEST message ends the game immediately
- Disconnect timer is cancelled on reconnect
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ws_manager import ConnectionManager


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.fixture
def mock_websocket():
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.fixture
def mock_redis_for_ws():
    mock = AsyncMock()
    mock.hset = AsyncMock(return_value=1)
    mock.hgetall = AsyncMock(return_value={})
    mock.hget = AsyncMock(return_value=None)
    mock.expire = AsyncMock(return_value=True)
    mock.pubsub = MagicMock(return_value=AsyncMock())
    return mock


class TestConnectWithPlayerId:
    @pytest.mark.asyncio
    async def test_connect_sets_player_status_connected(self, manager, mock_websocket, mock_redis_for_ws):
        """connect() must set player status to 'connected' in Redis."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        await manager.connect(game_id, mock_websocket, player_id=player_id)

        mock_redis_for_ws.hset.assert_called_once_with(
            f"game:{game_id}:players", player_id, "connected"
        )

    @pytest.mark.asyncio
    async def test_connect_sets_ttl_on_players_key(self, manager, mock_websocket, mock_redis_for_ws):
        """connect() must call expire on game:{id}:players with 900s."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        await manager.connect(game_id, mock_websocket, player_id=player_id)

        mock_redis_for_ws.expire.assert_called_once_with(f"game:{game_id}:players", 900)

    @pytest.mark.asyncio
    async def test_connect_adds_websocket_to_active_connections(self, manager, mock_websocket, mock_redis_for_ws):
        """connect() must register the WebSocket in active_connections."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())

        await manager.connect(game_id, mock_websocket, player_id="player_1")

        assert game_id in manager.active_connections
        assert mock_websocket in manager.active_connections[game_id]

    @pytest.mark.asyncio
    async def test_connect_cancels_existing_disconnect_timer(self, manager, mock_websocket, mock_redis_for_ws):
        """Reconnecting player must cancel any pending disconnect timer."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        # Simulate an existing timer
        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        timer_key = f"{game_id}:{player_id}"
        manager._disconnect_timers[timer_key] = mock_task

        await manager.connect(game_id, mock_websocket, player_id=player_id)

        mock_task.cancel.assert_called_once()
        assert timer_key not in manager._disconnect_timers

    @pytest.mark.asyncio
    async def test_connect_without_player_id_does_not_touch_redis(self, manager, mock_websocket, mock_redis_for_ws):
        """connect() without player_id (bots, observers) must not update player status Redis."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())

        await manager.connect(game_id, mock_websocket, player_id=None)

        mock_redis_for_ws.hset.assert_not_called()


class TestDisconnectWithPlayerId:
    @pytest.mark.asyncio
    async def test_disconnect_sets_player_status_disconnected(self, manager, mock_websocket, mock_redis_for_ws):
        """disconnect() must set player status to 'disconnected' in Redis."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        # First connect
        await manager.connect(game_id, mock_websocket, player_id=player_id)
        mock_redis_for_ws.hset.reset_mock()

        # Then disconnect
        await manager.disconnect(game_id, mock_websocket, player_id=player_id)

        mock_redis_for_ws.hset.assert_called_with(
            f"game:{game_id}:players", player_id, "disconnected"
        )

    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket_from_active_connections(self, manager, mock_websocket, mock_redis_for_ws):
        """disconnect() must remove the WebSocket from active_connections."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        await manager.connect(game_id, mock_websocket, player_id=player_id)
        await manager.disconnect(game_id, mock_websocket, player_id=player_id)

        assert game_id not in manager.active_connections or \
               mock_websocket not in manager.active_connections.get(game_id, set())

    @pytest.mark.asyncio
    async def test_disconnect_broadcasts_player_disconnected_event(self, manager, mock_redis_for_ws):
        """When a player disconnects from an in-progress game, PLAYER_DISCONNECTED must be broadcast."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        remaining_ws = AsyncMock()
        remaining_ws.send_text = AsyncMock()

        # Simulate two players connected
        ws1 = AsyncMock()
        ws1.accept = AsyncMock()
        manager.redis = mock_redis_for_ws
        # Setup: PROGRESS game with 1 human player
        mock_redis_for_ws.hgetall = AsyncMock(return_value={
            b"status": b"PROGRESS",
            b"human_count": b"2",
            b"num_players": b"3",
        })

        # Add remaining connection manually
        manager.active_connections[game_id] = {remaining_ws}

        # Trigger the disconnect handler directly
        await manager._handle_player_disconnect(game_id, player_id)

        remaining_ws.send_text.assert_called_once()
        sent_msg = json.loads(remaining_ws.send_text.call_args.args[0])
        assert sent_msg["type"] == "PLAYER_DISCONNECTED"
        assert sent_msg["player_id"] == player_id
        assert "options" in sent_msg  # 2 humans → show end/wait options

    @pytest.mark.asyncio
    async def test_disconnect_no_broadcast_for_finished_game(self, manager, mock_redis_for_ws):
        """No PLAYER_DISCONNECTED broadcast for finished games."""
        manager.redis = mock_redis_for_ws
        mock_redis_for_ws.hgetall = AsyncMock(return_value={
            b"status": b"FINISHED",
            b"human_count": b"1",
        })

        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        remaining_ws = AsyncMock()
        manager.active_connections[game_id] = {remaining_ws}

        await manager._handle_player_disconnect(game_id, player_id)

        remaining_ws.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_starts_timeout_timer(self, manager, mock_redis_for_ws):
        """disconnect() from an in-progress game must start a disconnect timer."""
        manager.redis = mock_redis_for_ws
        mock_redis_for_ws.hgetall = AsyncMock(return_value={
            b"status": b"PROGRESS",
            b"human_count": b"1",
        })

        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        manager.active_connections[game_id] = set()

        await manager._handle_player_disconnect(game_id, player_id)

        timer_key = f"{game_id}:{player_id}"
        assert timer_key in manager._disconnect_timers


class TestHandleClientMessage:
    @pytest.mark.asyncio
    async def test_end_game_request_cancels_timers(self, manager, mock_redis_for_ws):
        """END_GAME_REQUEST must cancel all disconnect timers for the game."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        other_player_id = str(uuid.uuid4())

        # Simulate two timers
        mock_task1 = MagicMock()
        mock_task2 = MagicMock()
        manager._disconnect_timers[f"{game_id}:{player_id}"] = mock_task1
        manager._disconnect_timers[f"{game_id}:{other_player_id}"] = mock_task2

        with patch("app.services.ws_manager.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_game = MagicMock()
            mock_game.status = "PROGRESS"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_game

            await manager.handle_client_message(
                game_id, player_id, {"type": "END_GAME_REQUEST"}
            )

        mock_task1.cancel.assert_called_once()
        mock_task2.cancel.assert_called_once()
        assert f"{game_id}:{player_id}" not in manager._disconnect_timers
        assert f"{game_id}:{other_player_id}" not in manager._disconnect_timers

    @pytest.mark.asyncio
    async def test_end_game_request_broadcasts_game_ended(self, manager, mock_redis_for_ws):
        """END_GAME_REQUEST must broadcast GAME_ENDED to all clients."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        remaining_ws = AsyncMock()
        remaining_ws.send_text = AsyncMock()
        manager.active_connections[game_id] = {remaining_ws}

        with patch("app.services.ws_manager.SessionLocal") as mock_session:
            mock_db = MagicMock()
            mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_session.return_value.__exit__ = MagicMock(return_value=False)
            mock_game = MagicMock()
            mock_game.status = "PROGRESS"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_game

            await manager.handle_client_message(
                game_id, player_id, {"type": "END_GAME_REQUEST"}
            )

        remaining_ws.send_text.assert_called_once()
        sent = json.loads(remaining_ws.send_text.call_args.args[0])
        assert sent["type"] == "GAME_ENDED"
        assert sent["reason"] == "player_request"

    @pytest.mark.asyncio
    async def test_unknown_message_type_does_not_raise(self, manager, mock_redis_for_ws):
        """Unknown WebSocket message types must be silently ignored."""
        manager.redis = mock_redis_for_ws
        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        # Should not raise
        await manager.handle_client_message(
            game_id, player_id, {"type": "SOME_UNKNOWN_TYPE", "data": "irrelevant"}
        )


class TestDisconnectTimeoutAutoEnd:
    @pytest.mark.asyncio
    async def test_timeout_ends_game_after_wait(self, manager, mock_redis_for_ws):
        """After DISCONNECT_TIMEOUT_SECONDS, game must be automatically ended."""

        manager.redis = mock_redis_for_ws
        mock_redis_for_ws.hget = AsyncMock(return_value=b"disconnected")

        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())
        manager.active_connections[game_id] = set()

        with patch("app.services.ws_manager.DISCONNECT_TIMEOUT_SECONDS", 0):
            with patch("app.services.ws_manager.SessionLocal") as mock_session:
                mock_db = MagicMock()
                mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
                mock_session.return_value.__exit__ = MagicMock(return_value=False)
                mock_game = MagicMock()
                mock_game.status = "PROGRESS"
                mock_db.query.return_value.filter.return_value.first.return_value = mock_game

                # Run the timeout coroutine directly with 0 second wait
                await manager._disconnect_timeout(game_id, player_id)

                # Verify game was ended
                assert mock_game.status == "FINISHED"
                mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_does_not_end_game_if_player_reconnected(self, manager, mock_redis_for_ws):
        """If player reconnects before timeout, game must NOT be ended."""
        manager.redis = mock_redis_for_ws
        # Simulate player reconnected: status is 'connected'
        mock_redis_for_ws.hget = AsyncMock(return_value=b"connected")

        game_id = str(uuid.uuid4())
        player_id = str(uuid.uuid4())

        with patch("app.services.ws_manager.DISCONNECT_TIMEOUT_SECONDS", 0):
            with patch("app.services.ws_manager.SessionLocal") as mock_session:
                mock_db = MagicMock()
                mock_session.return_value.__enter__ = MagicMock(return_value=mock_db)
                mock_session.return_value.__exit__ = MagicMock(return_value=False)

                await manager._disconnect_timeout(game_id, player_id)

                # DB should not be touched since player reconnected
                mock_db.query.assert_not_called()
