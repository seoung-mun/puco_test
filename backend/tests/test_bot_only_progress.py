"""Task 2A regression tests — bot-only games must keep advancing.

Covers §1.2.1 of docs/superpowers/plans/2026-05-05-error-log-stabilization.md:

The single-event-loop deadlock pattern is:
  T1 (run_bot_turn) → process_action → _schedule_next_bot_turn_if_needed
    → finds _bot_tasks[game_id] == T1 (not done) → silent skip ("in_flight_self")
    → T1 finishes → done callback empties slot → BUT no one re-triggers next bot.
Result: bot-only game freezes forever.

These tests use unit-level mocking (mock task + direct callback invocation) per
the plan's allowance. They do NOT spin up a full game (which would be slow and
require a fully loaded engine), but they DO verify the actual code paths in
`_make_bot_task_done_callback`, `_schedule_next_bot_turn_if_needed`, and
`_start_bot_stall_watchdog`.
"""

import asyncio
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.game_service import GameService


def _reset_class_state(game_id):
    """Drain all per-game class state between tests."""
    GameService._bot_tasks.pop(game_id, None)
    GameService._bot_task_started_at.pop(game_id, None)
    GameService._last_skip_reason.pop(game_id, None)
    GameService._engine_revision.pop(game_id, None)
    GameService.active_engines.pop(game_id, None)
    GameService._game_paused.pop(game_id, None)
    # Clear watchdog tasks tagged with this game_id
    keys_to_drop = [k for k in GameService._bot_stall_watchdogs if k.startswith(f"{game_id}:")]
    for k in keys_to_drop:
        watchdog = GameService._bot_stall_watchdogs.pop(k, None)
        if watchdog is not None:
            watchdog.cancel()


def _make_engine(idx: int) -> MagicMock:
    engine = MagicMock()
    engine.env.game.current_player_idx = idx
    engine.env.game.governor_idx = 0
    engine.env.agent_selection = f"player_{idx}"
    return engine


class TestSchedulerSkipReasonRecorded:
    """Step 2 — schedule_skip_existing_task must record a structured reason."""

    @pytest.mark.asyncio
    async def test_in_flight_self_records_skip_reason(self):
        game_id = uuid4()
        _reset_class_state(game_id)

        room = MagicMock()
        room.players = ["BOT_a", "BOT_b", "BOT_c"]
        engine = _make_engine(idx=1)

        # Pre-populate _bot_tasks with an in-flight task to force the skip path.
        async def _slow():
            await asyncio.sleep(0.5)

        in_flight = asyncio.create_task(_slow())
        GameService._bot_tasks[game_id] = in_flight
        GameService._bot_task_started_at[game_id] = time.time() - 1.0
        GameService._engine_revision[game_id] = 42

        try:
            with patch("app.services.bot_service.BotService.run_bot_turn"):
                service = GameService(MagicMock())
                service._schedule_next_bot_turn_if_needed(game_id, room, engine)

            recorded = GameService._last_skip_reason.get(game_id)
            assert recorded is not None, "skip reason must be recorded"
            assert recorded["reason"] == "in_flight_self"
            assert recorded["actor"] == "BOT_b"
            assert recorded["current_idx"] == 1
            assert recorded["engine_revision"] == 42
            assert recorded["seconds_since_existing_task_started"] is not None
            assert recorded["seconds_since_existing_task_started"] >= 0.5
        finally:
            in_flight.cancel()
            await asyncio.gather(in_flight, return_exceptions=True)
            _reset_class_state(game_id)

    @pytest.mark.asyncio
    async def test_paused_records_skip_reason(self):
        game_id = uuid4()
        _reset_class_state(game_id)

        room = MagicMock()
        room.players = ["BOT_a", "BOT_b", "BOT_c"]
        engine = _make_engine(idx=0)
        GameService.set_game_paused(game_id, True)

        try:
            service = GameService(MagicMock())
            service._schedule_next_bot_turn_if_needed(game_id, room, engine)
            recorded = GameService._last_skip_reason.get(game_id)
            assert recorded is not None
            assert recorded["reason"] == "paused"
        finally:
            GameService.set_game_paused(game_id, False)
            _reset_class_state(game_id)

    @pytest.mark.asyncio
    async def test_idx_out_of_range_records_skip_reason(self):
        game_id = uuid4()
        _reset_class_state(game_id)

        room = MagicMock()
        room.players = ["BOT_a"]
        engine = _make_engine(idx=5)

        try:
            service = GameService(MagicMock())
            service._schedule_next_bot_turn_if_needed(game_id, room, engine)
            recorded = GameService._last_skip_reason.get(game_id)
            assert recorded is not None
            assert recorded["reason"] == "idx_out_of_range"
            assert recorded["current_idx"] == 5
            assert recorded["players_len"] == 1
        finally:
            _reset_class_state(game_id)


class TestTaskDoneRescheduling:
    """Step 1 — task_done callback must re-trigger the next bot turn."""

    @pytest.mark.asyncio
    async def test_clean_finish_triggers_call_soon_for_next_bot(self):
        """A cleanly-completed bot task must enqueue a follow-up reschedule."""
        game_id = uuid4()
        _reset_class_state(game_id)

        engine = _make_engine(idx=2)  # next actor is players[2] which is BOT_c
        GameService.active_engines[game_id] = engine

        # Build a real, *completed* task we can pass to the callback.
        async def _no_op():
            return None

        task = asyncio.create_task(_no_op())
        await task  # ensure task.done()
        GameService._bot_tasks[game_id] = task
        GameService._bot_task_started_at[game_id] = time.time()

        service = GameService(MagicMock())
        callback = service._make_bot_task_done_callback(game_id, "BOT_b")

        try:
            with patch.object(asyncio.get_running_loop(), "call_soon") as mock_call_soon:
                callback(task)

                # Slot was cleared first, then call_soon scheduled the follow-up.
                assert game_id not in GameService._bot_tasks
                assert mock_call_soon.call_count == 1, (
                    f"expected exactly one call_soon, got {mock_call_soon.call_count}"
                )
        finally:
            _reset_class_state(game_id)

    @pytest.mark.asyncio
    async def test_cancelled_task_does_not_reschedule(self):
        """Guard against infinite-loop: cancelled tasks must NOT reschedule."""
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
                assert mock_call_soon.call_count == 0, (
                    "cancelled tasks must not enqueue follow-up reschedule"
                )
        finally:
            _reset_class_state(game_id)

    @pytest.mark.asyncio
    async def test_failed_task_does_not_reschedule(self):
        """Guard against infinite-loop: tasks raising exceptions must NOT reschedule."""
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
                assert mock_call_soon.call_count == 0, (
                    "failed tasks must not enqueue follow-up reschedule"
                )
        finally:
            _reset_class_state(game_id)

    @pytest.mark.asyncio
    async def test_no_active_engine_skips_reschedule(self):
        """If the game's engine is gone (recovery/crash), don't reschedule."""
        game_id = uuid4()
        _reset_class_state(game_id)
        # Note: do NOT register an engine.

        async def _no_op():
            return None

        task = asyncio.create_task(_no_op())
        await task
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
    async def test_paused_game_skips_reschedule(self):
        """Paused games must not auto-resume via the task_done reschedule."""
        game_id = uuid4()
        _reset_class_state(game_id)

        engine = _make_engine(idx=1)
        GameService.active_engines[game_id] = engine
        GameService.set_game_paused(game_id, True)

        async def _no_op():
            return None

        task = asyncio.create_task(_no_op())
        await task
        GameService._bot_tasks[game_id] = task
        service = GameService(MagicMock())
        callback = service._make_bot_task_done_callback(game_id, "BOT_a")

        try:
            with patch.object(asyncio.get_running_loop(), "call_soon") as mock_call_soon:
                callback(task)
                assert mock_call_soon.call_count == 0
        finally:
            GameService.set_game_paused(game_id, False)
            _reset_class_state(game_id)


class TestWatchdogIncludesSkipReason:
    """Step 4 — bot-stall watchdog log must include last_skip_reason."""

    @pytest.mark.asyncio
    async def test_watchdog_logs_last_skip_reason(self, caplog):
        import logging as _logging

        game_id = uuid4()
        _reset_class_state(game_id)
        GameService._last_skip_reason[game_id] = {
            "reason": "in_flight_self",
            "actor": "BOT_x",
            "at": time.time(),
            "current_idx": 1,
        }
        service = GameService(MagicMock())

        # Patch sleep to short for test speed.
        original_sleep = asyncio.sleep

        async def fast_sleep(delay):
            await original_sleep(0.01)

        try:
            with patch("app.services.game_service.asyncio.sleep", side_effect=fast_sleep):
                with caplog.at_level(_logging.WARNING, logger="app.services.game_service"):
                    service._start_bot_stall_watchdog(game_id, "BOT_x")
                    watchdog = GameService._bot_stall_watchdogs[f"{game_id}:BOT_x"]
                    await watchdog
            messages = [rec.getMessage() for rec in caplog.records]
            assert any("watchdog_timeout" in m for m in messages), (
                f"watchdog should have fired, messages={messages}"
            )
            assert any("last_skip_reason" in m and "in_flight_self" in m for m in messages), (
                f"watchdog log must include last_skip_reason details, messages={messages}"
            )
        finally:
            _reset_class_state(game_id)


class TestPairedSkipAndRecreate:
    """Regression guard — when a skip happens, a follow-up task_created must follow."""

    @pytest.mark.asyncio
    async def test_skip_then_done_then_new_task_pair(self):
        """If scheduler fires schedule_skip_existing_task once, the very next
        task_done callback must enqueue a follow-up reschedule. Without Step 1
        that pairing breaks and the bot-only game freezes."""
        game_id = uuid4()
        _reset_class_state(game_id)

        engine = _make_engine(idx=2)
        GameService.active_engines[game_id] = engine
        room = MagicMock()
        room.players = ["BOT_a", "BOT_b", "BOT_c"]

        # Stage 1: simulate the in-flight skip.
        async def _slow():
            await asyncio.sleep(0.05)

        in_flight = asyncio.create_task(_slow())
        GameService._bot_tasks[game_id] = in_flight
        GameService._bot_task_started_at[game_id] = time.time()

        service = GameService(MagicMock())
        try:
            service._schedule_next_bot_turn_if_needed(game_id, room, engine)
            assert GameService._last_skip_reason[game_id]["reason"] == "in_flight_self"

            # Stage 2: T1 finishes cleanly, callback runs.
            await in_flight
            callback = service._make_bot_task_done_callback(game_id, "BOT_a")

            with patch.object(asyncio.get_running_loop(), "call_soon") as mock_call_soon:
                callback(in_flight)
                assert mock_call_soon.call_count == 1, (
                    "after a skip, the very next task_done MUST schedule a follow-up "
                    "reschedule on the event loop. Otherwise bot-only games freeze."
                )
        finally:
            if not in_flight.done():
                in_flight.cancel()
                await asyncio.gather(in_flight, return_exceptions=True)
            _reset_class_state(game_id)
