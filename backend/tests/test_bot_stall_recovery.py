"""Delivery contract regression tests for Task 2 §1.2 Step 5.

Plan: ``docs/superpowers/plans/2026-05-05-error-log-stabilization.md``.

Three asserts here, one per documented failure mode:

1. A Mayor batch with a suppressed mid-action **must** emit exactly one final
   visible STATE_UPDATE when it exits via ``mayor_batch_no_legal_slot``.
2. When ``redis_client.publish`` raises, ``_sync_to_redis`` must fall back to
   the direct WS broadcast path (and not let the exception escape).
3. ``ConnectionManager._broadcast`` must keep delivering to the healthy
   sockets even when one in the middle dies, and harvest the dead socket from
   ``active_connections`` and ``_conn_ids``.

These tests are isolated stress checks against the contract — they do not
exercise the real engine or the real Redis/WS stack. We reuse helpers from
``test_priority2_ws_delivery_contract`` for the Mayor batch fixture so the two
suites stay in lock-step.
"""

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bot_service import BotService
from app.services.game_service import GameService
from app.services.ws_manager import ConnectionManager

# Reuse the existing fakes so we don't drift from the §1.2 Step 1·2 fixtures.
from tests.test_priority2_ws_delivery_contract import _FakeMayorEngine


# ---------------------------------------------------------------------------
# 1) Mayor batch with suppressed mid-action emits exactly one final visible
#    STATE_UPDATE (compensating publish via broadcast_current_state).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mayor_batch_with_suppressed_mid_action_emits_exactly_one_visible_state_update():
    """One placement is suppressed, then the batch exits via
    ``mayor_batch_no_legal_slot``. The compensating flush must run exactly
    once via ``GameService.broadcast_current_state``.
    """

    def _on_apply(eng: _FakeMayorEngine, action: int) -> None:
        # Apply the placement, but leave phase=MAYOR with remaining>0 so the
        # loop re-enters and finds an empty mask → no_legal_slot break path.
        if action in eng._legal_island:
            eng._legal_island.remove(action)
        eng._remaining = max(0, eng._remaining - 1)
        eng.env.game.players[1].unplaced_colonists = eng._remaining

    engine = _FakeMayorEngine(
        remaining=2,
        legal_island_slots=[120],  # only one slot — second iter has no legal
        on_apply=_on_apply,
    )

    captured: list[tuple[int, bool]] = []

    async def _callback(_game_id, _actor_id, action, suppress_broadcast=False):
        captured.append((action, suppress_broadcast))
        engine.apply(action)

    game_id = uuid.uuid4()

    def _select(*, game_id, engine, actor_id, action_mask=None):
        mask = action_mask if action_mask is not None else engine.get_action_mask()
        for idx in range(120, 132):
            if idx < len(mask) and mask[idx]:
                return idx, None
        return 15, None

    # Patch the staticmethod added in commit 3accdae. AsyncMock isn't right
    # here because broadcast_current_state is sync; use MagicMock and assert
    # via call_count.
    fake_publish = MagicMock(return_value=True)

    with patch.object(GameService, "broadcast_current_state", staticmethod(fake_publish)):
        with patch.object(
            BotService, "_select_action_for_current_state", side_effect=_select
        ):
            await BotService._run_mayor_batch_turn(
                game_id=game_id,
                engine=engine,
                actor_id="BOT_ppo",
                process_action_callback=_callback,
                initial_mask=engine.get_action_mask(),
                supports_suppress_broadcast=True,
            )

    # Exactly one suppressed apply happened (the only legal slot was taken).
    assert len(captured) == 1, f"expected one suppressed apply, got {captured!r}"
    assert captured[0][1] is True
    # The compensating flush must have fired exactly once.
    assert fake_publish.call_count == 1
    fake_publish.assert_called_with(game_id)


# ---------------------------------------------------------------------------
# 2) Redis publish failure → direct WS fallback.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_to_redis_falls_back_to_direct_broadcast_when_publish_raises():
    """``redis_client.publish`` raising ConnectionError must trigger the
    direct manager.broadcast_to_game fallback. The exception must not escape.
    """

    fake_redis = MagicMock()
    fake_redis.set.return_value = True
    # Production code's except block catches *any* Exception coming from the
    # publish call; ConnectionError is a real-world failure mode for a
    # cluster-replaced Redis instance.
    fake_redis.publish.side_effect = ConnectionError("redis publish unavailable")

    fake_manager = SimpleNamespace(broadcast_to_game=AsyncMock())

    game_id = uuid.uuid4()

    with patch("app.services.game_service.redis_client", fake_redis), patch(
        "app.services.game_service.manager", fake_manager
    ):
        # _sync_to_redis is sync — it schedules the fallback via
        # loop.create_task. We're inside an asyncio test so the loop exists.
        # No exception should escape.
        GameService._sync_to_redis(game_id, {"foo": "bar"}, finished=False)

        # Yield once so the scheduled coroutine runs.
        await asyncio.sleep(0)

    fake_redis.publish.assert_called_once()
    assert fake_manager.broadcast_to_game.await_count == 1
    # Sanity: the payload that went out was the STATE_UPDATE wrapper.
    args, _kwargs = fake_manager.broadcast_to_game.call_args
    assert args[0] == str(game_id)
    assert args[1]["type"] == "STATE_UPDATE"
    assert args[1]["data"] == {"foo": "bar"}


# ---------------------------------------------------------------------------
# 3) Dead WS does not block other receivers.
# ---------------------------------------------------------------------------


def _make_socket() -> AsyncMock:
    sock = AsyncMock()
    sock.send_text = AsyncMock()
    return sock


@pytest.mark.asyncio
async def test_dead_websocket_does_not_block_other_receivers():
    """Three sockets in a room; the middle one's send_text raises
    ConnectionError. The two healthy sockets must each be awaited exactly
    once with the payload, and the dead socket must be removed from
    ``active_connections[game_id]`` and ``_conn_ids``.
    """
    mgr = ConnectionManager()
    game_id = "g-stall-recovery"

    s_first = _make_socket()
    s_dead = _make_socket()
    s_dead.send_text.side_effect = ConnectionError("client gone")
    s_last = _make_socket()

    mgr.active_connections[game_id] = {s_first, s_dead, s_last}
    for s in (s_first, s_dead, s_last):
        mgr._get_connection_id(s)

    payload = json.dumps({"type": "X"})
    await mgr._broadcast(game_id, payload)

    # Both healthy sockets received the payload exactly once.
    s_first.send_text.assert_awaited_once_with(payload)
    s_last.send_text.assert_awaited_once_with(payload)
    # Dead socket was attempted (gather doesn't short-circuit) and harvested.
    s_dead.send_text.assert_awaited_once_with(payload)

    # Dead socket removed from active_connections and _conn_ids.
    assert s_dead not in mgr.active_connections[game_id]
    assert mgr.active_connections[game_id] == {s_first, s_last}
    assert id(s_dead) not in mgr._conn_ids
    # Healthy ones still tracked.
    assert id(s_first) in mgr._conn_ids
    assert id(s_last) in mgr._conn_ids
