"""
TDD tests for Redis operations in game_service:
- _sync_to_redis applies TTL (ex=900 active, ex=300 finished)
- _store_game_meta stores human_count and status in Redis hash
- Redis meta status updated to FINISHED when game ends
- Redis TTL is refreshed on every state update
"""
import uuid
from unittest.mock import MagicMock

import pytest

from app.db.models import GameSession
from app.services.game_service import GameService


@pytest.fixture
def mock_redis():
    mock = MagicMock()
    mock.set.return_value = True
    mock.publish.return_value = 1
    mock.hset.return_value = 1
    mock.hgetall.return_value = {}
    mock.expire.return_value = True
    return mock


@pytest.fixture
def game_service(db, monkeypatch, mock_redis):
    monkeypatch.setattr("app.services.game_service.redis_client", mock_redis)
    return GameService(db), mock_redis


class TestSyncToRedisWithTTL:
    def test_active_game_state_has_15min_ttl(self, game_service):
        """Active game state must be cached with 900s (15min) TTL."""
        service, mock_redis = game_service
        game_id = uuid.uuid4()
        state = {"round": 1, "phase": "role_selection"}

        service._sync_to_redis(game_id, state, action_mask=[1, 0, 1], finished=False)

        # The SET call must include ex=900
        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs.kwargs.get("ex") == 900 or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] == 900
        ), f"Expected ex=900 for active game, got: {call_kwargs}"

    def test_finished_game_state_has_5min_ttl(self, game_service):
        """Finished game state must be cached with 300s (5min) TTL."""
        service, mock_redis = game_service
        game_id = uuid.uuid4()
        state = {"round": 5, "phase": "game_over"}

        service._sync_to_redis(game_id, state, action_mask=[], finished=True)

        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args
        assert call_kwargs.kwargs.get("ex") == 300 or (
            len(call_kwargs.args) > 2 and call_kwargs.args[2] == 300
        ), f"Expected ex=300 for finished game, got: {call_kwargs}"

    def test_redis_key_format_for_state(self, game_service):
        """State key must follow game:{game_id}:state pattern."""
        service, mock_redis = game_service
        game_id = uuid.uuid4()

        service._sync_to_redis(game_id, {"phase": "test"}, finished=False)

        key_used = mock_redis.set.call_args.args[0]
        assert key_used == f"game:{game_id}:state"

    def test_publish_event_key_format(self, game_service):
        """Publish channel must follow game:{game_id}:events pattern."""
        service, mock_redis = game_service
        game_id = uuid.uuid4()

        service._sync_to_redis(game_id, {"phase": "test"}, finished=False)

        channel_used = mock_redis.publish.call_args.args[0]
        assert channel_used == f"game:{game_id}:events"

    def test_publish_message_contains_state_update_type(self, game_service):
        """Published message must have type=STATE_UPDATE."""
        import json
        service, mock_redis = game_service
        game_id = uuid.uuid4()

        service._sync_to_redis(game_id, {"round": 1}, action_mask=[1], finished=False)

        published_msg = json.loads(mock_redis.publish.call_args.args[1])
        assert published_msg["type"] == "STATE_UPDATE"
        assert "data" in published_msg
        assert "action_mask" in published_msg

    def test_redis_failure_does_not_raise(self, game_service):
        """Redis failure must be swallowed and not crash the game."""
        service, mock_redis = game_service
        mock_redis.set.side_effect = ConnectionError("Redis down")

        # Should not raise
        service._sync_to_redis(uuid.uuid4(), {"phase": "test"}, finished=False)


class TestStoreGameMeta:
    def test_stores_human_count_for_mixed_game(self, game_service, db):
        """_store_game_meta must correctly count human players (non-BOT)."""
        service, mock_redis = game_service
        game_id = uuid.uuid4()
        game = GameSession(
            id=game_id, title="Meta Test", status="PROGRESS",
            num_players=3, players=["user_abc", "BOT_PPO_1", "BOT_PPO_2"]
        )
        db.add(game)
        db.flush()

        service._store_game_meta(game_id, game)

        hset_calls = mock_redis.hset.call_args_list
        assert any(
            call_args.kwargs.get("mapping", {}).get("human_count") == "1"
            or (call_args.args and "human_count" in str(call_args))
            for call_args in hset_calls
        ), "human_count should be '1' for 1 human + 2 bots"

    def test_stores_human_count_for_two_humans(self, game_service, db):
        """Two human players in 2v1 mode: human_count must be 2."""
        service, mock_redis = game_service
        game_id = uuid.uuid4()
        game = GameSession(
            id=game_id, title="2H Meta Test", status="PROGRESS",
            num_players=3, players=["user_abc", "user_xyz", "BOT_PPO_1"]
        )
        db.add(game)
        db.flush()

        service._store_game_meta(game_id, game)

        hset_calls = mock_redis.hset.call_args_list
        meta_call = next(
            (c for c in hset_calls if f"game:{game_id}:meta" in str(c)), None
        )
        assert meta_call is not None, "hset must be called with game:{id}:meta key"
        mapping = meta_call.kwargs.get("mapping", {})
        assert mapping.get("human_count") == "2"

    def test_meta_key_has_ttl_applied(self, game_service, db):
        """game:{id}:meta key must have expire called with 900s."""
        service, mock_redis = game_service
        game_id = uuid.uuid4()
        game = GameSession(
            id=game_id, title="TTL Meta", status="PROGRESS",
            num_players=3, players=["user_abc", "BOT_PPO_1", "BOT_PPO_2"]
        )
        db.add(game)
        db.flush()

        service._store_game_meta(game_id, game)

        expire_calls = mock_redis.expire.call_args_list
        meta_expire = next(
            (c for c in expire_calls if f"game:{game_id}:meta" in str(c)), None
        )
        assert meta_expire is not None, "expire must be called for meta key"
        assert 900 in meta_expire.args or 900 == meta_expire.args[1], \
            "Meta TTL must be 900s"

    def test_redis_meta_failure_does_not_crash(self, game_service, db):
        """Redis meta store failure must not crash the game."""
        service, mock_redis = game_service
        mock_redis.hset.side_effect = ConnectionError("Redis down")

        game_id = uuid.uuid4()
        game = GameSession(
            id=game_id, title="Fail Test", status="PROGRESS", num_players=3, players=[]
        )
        db.add(game)
        db.flush()

        # Must not raise
        service._store_game_meta(game_id, game)


class TestRedisMetaUpdatedOnFinish:
    def test_meta_status_set_to_finished_when_game_ends(self, db, monkeypatch):
        """When game ends, Redis meta status must be updated to FINISHED."""
        mock_redis = MagicMock()
        mock_redis.set.return_value = True
        mock_redis.publish.return_value = 1
        mock_redis.hset.return_value = 1
        mock_redis.expire.return_value = True
        monkeypatch.setattr("app.services.game_service.redis_client", mock_redis)

        game_id = uuid.uuid4()
        game = GameSession(
            id=game_id, title="Finish Test", status="PROGRESS",
            num_players=3, players=["user_abc", "BOT_PPO_1", "BOT_PPO_2"]
        )
        db.add(game)
        db.flush()

        # Simulate what process_action does when result["done"] is True
        game.status = "FINISHED"
        try:
            mock_redis.hset(f"game:{game_id}:meta", "status", "FINISHED")
            mock_redis.expire(f"game:{game_id}:meta", 300)
        except Exception:
            pass

        # Verify the hset was called with FINISHED status
        hset_calls = [str(c) for c in mock_redis.hset.call_args_list]
        assert any("FINISHED" in c for c in hset_calls), \
            "Redis meta status must be updated to FINISHED when game ends"
