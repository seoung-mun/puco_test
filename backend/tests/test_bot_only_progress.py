"""Task 2A regressions for bot-only scheduler self-recovery and watchdogs."""

import asyncio
import logging
import time
import uuid
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.db.models import GameSession, User
from app.services.game_service import GameService


class _SessionContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, exc_type, exc, tb):
        return False


def _session_local_factory(db):
    def _factory():
        return _SessionContext(db)

    return _factory


def _reset_class_state(game_id):
    GameService._bot_tasks.pop(game_id, None)
    GameService._bot_task_started_at.pop(game_id, None)
    GameService._last_skip_reason.pop(game_id, None)
    GameService._engine_revision.pop(game_id, None)
    GameService.active_engines.pop(game_id, None)
    GameService._game_paused.pop(game_id, None)
    GameService._game_speed.pop(game_id, None)
    GameService._bot_stall_watchdog_meta.pop(game_id, None)

    watchdog_key = GameService._bot_stall_watchdog_key(game_id)
    watchdog = GameService._bot_stall_watchdogs.pop(watchdog_key, None)
    if watchdog is not None:
        watchdog.cancel()


def _make_engine(idx: int) -> MagicMock:
    engine = MagicMock()
    engine.env.game.current_player_idx = idx
    engine.env.game.governor_idx = 0
    engine.env.agent_selection = f"player_{idx}"
    return engine


def _make_bot_room(db) -> uuid.UUID:
    host = User(
        id=uuid.uuid4(),
        google_id=f"bot_progress_host_{uuid.uuid4().hex}",
        nickname="BotProgressHost",
    )
    db.add(host)
    db.flush()

    room = GameSession(
        id=uuid.uuid4(),
        title="Bot Progress Room",
        status="WAITING",
        num_players=3,
        players=["BOT_random", "BOT_random", "BOT_random"],
        host_id=str(host.id),
    )
    db.add(room)
    db.commit()
    return room.id


def _patch_test_runtime(monkeypatch, db):
    mock_redis = MagicMock()
    mock_redis.set.return_value = True
    mock_redis.get.return_value = None
    mock_redis.publish.return_value = 1
    mock_redis.hset.return_value = 1
    mock_redis.hgetall.return_value = {}
    mock_redis.hget.return_value = None
    mock_redis.expire.return_value = True
    monkeypatch.setattr("app.services.game_service.redis_client", mock_redis)
    monkeypatch.setattr("app.core.redis.sync_redis_client", mock_redis)
    monkeypatch.setattr("app.dependencies.SessionLocal", _session_local_factory(db))
    monkeypatch.setattr("app.services.game_service.SessionLocal", _session_local_factory(db))


class _DeterministicBotChain:
    def __init__(self):
        self.action_count = 0
        self.first_action_applied = asyncio.Event()
        self.ten_actions_applied = asyncio.Event()
        self.seen_task_ids = []

    async def run(self, game_id, engine, actor_id, process_action_callback):
        current_task = asyncio.current_task()
        assert current_task is not None
        self.seen_task_ids.append(id(current_task))

        action_number = self.action_count + 1
        if action_number == 10:
            GameService.set_game_paused(game_id, True)

        mask = engine.get_action_mask()
        action = next(idx for idx, valid in enumerate(mask) if valid)
        process_action_callback(game_id, actor_id, action)

        self.action_count = action_number
        if action_number == 1:
            self.first_action_applied.set()
        if action_number == 10:
            self.ten_actions_applied.set()


class TestSchedulerSkipMetadata:
    @pytest.mark.asyncio
    async def test_in_flight_self_records_extended_skip_fields(self):
        game_id = uuid4()
        _reset_class_state(game_id)

        room = MagicMock()
        room.players = ["BOT_a", "BOT_b", "BOT_c"]
        engine = _make_engine(idx=1)

        gate = asyncio.Event()

        async def _slow():
            await gate.wait()

        in_flight = asyncio.create_task(_slow())
        setattr(in_flight, "_bot_actor_id", "BOT_a")
        GameService._bot_tasks[game_id] = in_flight
        GameService._bot_task_started_at[game_id] = time.time() - 1.0
        GameService._engine_revision[game_id] = 42

        try:
            with patch("app.services.bot_service.BotService.run_bot_turn"):
                service = GameService(MagicMock())
                service._schedule_next_bot_turn_if_needed(game_id, room, engine)

            recorded = GameService._last_skip_reason.get(game_id)
            assert recorded is not None
            assert recorded["reason"] == "in_flight_self"
            assert recorded["actor"] == "BOT_b"
            assert recorded["existing_task_actor"] == "BOT_a"
            assert recorded["engine_revision"] == 42
            assert recorded["current_idx"] == 1
            assert recorded["seconds_since_existing_task_started"] is not None
            assert recorded["seconds_since_existing_task_started"] >= 0.5
        finally:
            gate.set()
            await asyncio.gather(in_flight, return_exceptions=True)
            _reset_class_state(game_id)


class TestTaskDoneGuardrails:
    @pytest.mark.asyncio
    async def test_cancelled_task_does_not_reschedule(self):
        game_id = uuid4()
        _reset_class_state(game_id)

        engine = _make_engine(idx=1)
        GameService.active_engines[game_id] = engine

        async def _slow():
            await asyncio.sleep(10)

        task = asyncio.create_task(_slow())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        GameService._bot_tasks[game_id] = task
        service = GameService(MagicMock())
        callback = service._make_bot_task_done_callback(game_id, "BOT_a")

        try:
            with patch.object(asyncio.get_running_loop(), "call_soon") as mock_call_soon:
                callback(task)
                assert mock_call_soon.call_count == 0
        finally:
            _reset_class_state(game_id)

    @pytest.mark.asyncio
    async def test_failed_task_does_not_reschedule(self):
        game_id = uuid4()
        _reset_class_state(game_id)

        engine = _make_engine(idx=1)
        GameService.active_engines[game_id] = engine

        async def _boom():
            raise RuntimeError("simulated bot turn failure")

        task = asyncio.create_task(_boom())
        try:
            await task
        except RuntimeError:
            pass

        GameService._bot_tasks[game_id] = task
        service = GameService(MagicMock())
        callback = service._make_bot_task_done_callback(game_id, "BOT_a")

        try:
            with patch.object(asyncio.get_running_loop(), "call_soon") as mock_call_soon:
                callback(task)
                assert mock_call_soon.call_count == 0
        finally:
            _reset_class_state(game_id)


class TestWatchdogRecovery:
    @pytest.mark.asyncio
    async def test_skip_watchdog_survives_task_done(self):
        game_id = uuid4()
        _reset_class_state(game_id)

        room = MagicMock()
        room.players = ["BOT_a", "BOT_b", "BOT_c"]
        engine = _make_engine(idx=0)
        GameService.active_engines[game_id] = engine

        in_flight = MagicMock(spec=asyncio.Task)
        in_flight.done.return_value = False
        in_flight.cancelled.return_value = False
        in_flight.exception.return_value = None
        setattr(in_flight, "_bot_actor_id", "BOT_a")
        GameService._bot_tasks[game_id] = in_flight
        GameService._bot_task_started_at[game_id] = time.time()

        service = GameService(MagicMock())

        try:
            service._schedule_next_bot_turn_if_needed(game_id, room, engine)
            assert GameService._last_skip_reason[game_id]["reason"] == "in_flight_self"
            in_flight.done.return_value = True

            callback = service._make_bot_task_done_callback(game_id, "BOT_a")

            with patch.object(asyncio.get_running_loop(), "call_soon") as mock_call_soon:
                callback(in_flight)
                assert mock_call_soon.call_count == 1

            watchdog_key = GameService._bot_stall_watchdog_key(game_id)
            watchdog = GameService._bot_stall_watchdogs.get(watchdog_key)
            assert watchdog is not None
            assert not watchdog.done()
            assert GameService._bot_stall_watchdog_meta[game_id]["source"] == "schedule_skip"
        finally:
            watchdog_key = GameService._bot_stall_watchdog_key(game_id)
            watchdog = GameService._bot_stall_watchdogs.get(watchdog_key)
            if watchdog is not None:
                watchdog.cancel()
                await asyncio.gather(watchdog, return_exceptions=True)
            _reset_class_state(game_id)

    @pytest.mark.asyncio
    async def test_watchdog_logs_last_skip_reason(self, caplog):
        game_id = uuid4()
        _reset_class_state(game_id)
        GameService._last_skip_reason[game_id] = {
            "reason": "in_flight_self",
            "actor": "BOT_x",
            "at": time.time(),
            "current_idx": 1,
        }
        service = GameService(MagicMock())
        original_sleep = asyncio.sleep

        async def fast_sleep(delay):
            await original_sleep(0.01)

        try:
            with patch("app.services.game_service.asyncio.sleep", side_effect=fast_sleep):
                with caplog.at_level(logging.WARNING, logger="app.services.game_service"):
                    service._start_bot_stall_watchdog(
                        game_id,
                        "BOT_x",
                        source="schedule_skip",
                    )
                    watchdog_key = GameService._bot_stall_watchdog_key(game_id)
                    watchdog = GameService._bot_stall_watchdogs[watchdog_key]
                    await watchdog

            messages = [rec.getMessage() for rec in caplog.records]
            assert any("watchdog_timeout" in message for message in messages)
            assert any("last_skip_reason" in message and "in_flight_self" in message for message in messages)
        finally:
            _reset_class_state(game_id)


class TestBotOnlyProgression:
    @pytest.mark.asyncio
    async def test_three_bot_game_replaces_task_next_tick_and_runs_ten_actions(self, db, monkeypatch, caplog):
        game_id = _make_bot_room(db)
        _reset_class_state(game_id)
        _patch_test_runtime(monkeypatch, db)

        chain = _DeterministicBotChain()
        service = GameService(db)

        try:
            from app.services.bot_service import BotService

            with patch.object(BotService, "run_bot_turn", side_effect=chain.run):
                with caplog.at_level(logging.WARNING, logger="app.services.game_service"):
                    service.start_game(game_id)
                    first_task = GameService._bot_tasks.get(game_id)
                    assert first_task is not None

                    await asyncio.wait_for(chain.first_action_applied.wait(), timeout=2)
                    await first_task
                    await asyncio.sleep(0)
                    await asyncio.sleep(0)

                    replacement_task = GameService._bot_tasks.get(game_id)
                    assert replacement_task is not None
                    assert replacement_task is not first_task

                    await asyncio.wait_for(chain.ten_actions_applied.wait(), timeout=5)
                    await asyncio.sleep(0)
                    await asyncio.sleep(0)

            assert chain.action_count == 10
            assert len(set(chain.seen_task_ids)) >= 10
            assert GameService._bot_tasks.get(game_id) is None

            messages = [rec.getMessage() for rec in caplog.records]
            skip_indexes = [
                idx for idx, message in enumerate(messages)
                if "schedule_skip_existing_task" in message
            ]
            task_done_indexes = [
                idx for idx, message in enumerate(messages)
                if "task_done" in message
            ]
            task_created_indexes = [
                idx for idx, message in enumerate(messages)
                if "task_created" in message
            ]

            assert skip_indexes, "expected at least one real in-flight skip during bot chaining"
            assert len(task_created_indexes) >= 2, "expected initial and replacement bot tasks"
            assert len(task_done_indexes) >= 1, "expected completed bot tasks in the chain"

            first_skip = skip_indexes[0]
            next_done = next(idx for idx in task_done_indexes if idx > first_skip)
            next_created = next(idx for idx in task_created_indexes if idx > next_done)
            assert first_skip < next_done < next_created
        finally:
            GameService.set_game_paused(game_id, False)
            current_task = GameService._bot_tasks.get(game_id)
            if current_task is not None:
                current_task.cancel()
                await asyncio.gather(current_task, return_exceptions=True)
            _reset_class_state(game_id)
