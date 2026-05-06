import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.bot_service import BotService, BotTurnDeliveryState
from app.services.engine_gateway.constants import Phase
from app.services.game_service import GameService


def test_sync_to_redis_skips_direct_broadcast_when_redis_publish_succeeds(monkeypatch):
    service = GameService(db=MagicMock())
    fake_redis = MagicMock()
    fake_loop = MagicMock()
    fake_loop.create_task.side_effect = lambda coro: coro.close()

    monkeypatch.setattr("app.services.game_service.redis_client", fake_redis)
    monkeypatch.setattr("app.services.game_service.manager", SimpleNamespace(broadcast_to_game=AsyncMock()))
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: fake_loop)

    service._sync_to_redis("game-1", {"meta": {"phase": "role_selection"}})

    fake_redis.publish.assert_called_once()
    fake_loop.create_task.assert_not_called()


def test_sync_to_redis_falls_back_to_direct_broadcast_when_redis_publish_fails(monkeypatch):
    service = GameService(db=MagicMock())
    fake_redis = MagicMock()
    fake_redis.set.side_effect = RuntimeError("redis down")
    fake_loop = MagicMock()
    fake_loop.create_task.side_effect = lambda coro: coro.close()

    monkeypatch.setattr("app.services.game_service.redis_client", fake_redis)
    monkeypatch.setattr("app.services.game_service.manager", SimpleNamespace(broadcast_to_game=AsyncMock()))
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: fake_loop)

    service._sync_to_redis("game-2", {"meta": {"phase": "role_selection"}})

    fake_loop.create_task.assert_called_once()


# ---------------------------------------------------------------------------
# Step 1·2: BotTurnDeliveryState + compensating publish on abnormal batch exits
# ---------------------------------------------------------------------------


class _FakeMayorEngine:
    """Minimal engine surrogate: tracks remaining colonists & a scripted action mask."""

    def __init__(
        self,
        *,
        remaining: int,
        legal_island_slots: list[int] | None = None,
        legal_city_slots: list[int] | None = None,
        on_apply=None,
    ):
        self._remaining = remaining
        self._legal_island = list(legal_island_slots or [120])
        self._legal_city = list(legal_city_slots or [])
        self._on_apply = on_apply
        self.applied_actions: list[int] = []
        self.last_obs = {"global_state": {"current_phase": int(Phase.MAYOR)}}
        self.last_info = {"current_phase_id": int(Phase.MAYOR)}
        self._step_count = 0
        self.env = SimpleNamespace(
            game=SimpleNamespace(
                current_player_idx=1,
                players=[
                    SimpleNamespace(unplaced_colonists=0),
                    SimpleNamespace(unplaced_colonists=remaining),
                    SimpleNamespace(unplaced_colonists=0),
                ],
                current_phase=Phase.MAYOR,
            ),
            agent_selection="player_1",
        )

    @property
    def remaining(self) -> int:
        return self._remaining

    def _build_mask(self) -> list[int]:
        mask = [0] * 160
        for slot in self._legal_island:
            mask[slot] = 1
        for slot in self._legal_city:
            mask[slot] = 1
        return mask

    def get_action_mask(self) -> list[int]:
        return self._build_mask()

    def apply(self, action: int) -> None:
        """Invoked by the test callback to advance state."""
        self.applied_actions.append(action)
        if self._on_apply is not None:
            self._on_apply(self, action)
            return

        # Default: consume one colonist, drop the slot from legality.
        if action in self._legal_island:
            self._legal_island.remove(action)
        elif action in self._legal_city:
            self._legal_city.remove(action)
        self._remaining = max(0, self._remaining - 1)
        self.env.game.players[1].unplaced_colonists = self._remaining
        if self._remaining <= 0:
            self.env.game.current_phase = Phase.CRAFTSMAN


def _first_legal_action_factory(engine: _FakeMayorEngine):
    def _select(_bot_type, game_context):
        mask = game_context["action_mask"]
        for idx in range(120, 132):
            if idx < len(mask) and mask[idx]:
                return idx
        for idx in range(140, 152):
            if idx < len(mask) and mask[idx]:
                return idx
        return 15

    return _select


@pytest.mark.asyncio
async def test_mayor_batch_no_legal_slot_emits_one_compensating_publish():
    """After 1 suppressed placement, abnormal exit must trigger exactly one compensating flush."""

    def _on_apply(eng, action):
        eng.applied_actions  # noqa: B018 — ensure called
        # Apply the placement, but the SECOND iteration will have *no* legal slots.
        if action in eng._legal_island:
            eng._legal_island.remove(action)
        eng._remaining = max(0, eng._remaining - 1)
        eng.env.game.players[1].unplaced_colonists = eng._remaining
        # Crucially: leave phase=MAYOR and remaining>0 so the loop re-enters,
        # but with no legal slots → mayor_batch_no_legal_slot break path.

    engine = _FakeMayorEngine(
        remaining=2,
        legal_island_slots=[120],  # only one slot — second iteration will find none
        on_apply=_on_apply,
    )

    captured = []

    async def _callback(_game_id, _actor_id, action, suppress_broadcast=False):
        captured.append((action, suppress_broadcast))
        engine.apply(action)

    publish_calls: list[uuid.UUID] = []

    def _fake_publish(game_id):
        publish_calls.append(game_id)
        return True

    game_id = uuid.uuid4()

    def _select(*, game_id, engine, actor_id, action_mask=None):
        mask = action_mask if action_mask is not None else engine.get_action_mask()
        for idx in range(120, 132):
            if idx < len(mask) and mask[idx]:
                return idx, None
        for idx in range(140, 152):
            if idx < len(mask) and mask[idx]:
                return idx, None
        return 15, None

    with patch.object(GameService, "broadcast_current_state", staticmethod(_fake_publish)):
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

    # One placement was applied (suppressed because remaining started at 2).
    assert len(captured) == 1
    assert captured[0][1] is True  # suppress_broadcast=True
    # Exactly one compensating publish for the applied-but-never-broadcast placement.
    assert publish_calls == [game_id]


@pytest.mark.asyncio
async def test_mayor_batch_natural_completion_does_not_double_publish():
    """When the final placement runs with suppress=False, no compensating flush is needed."""
    engine = _FakeMayorEngine(
        remaining=2,
        legal_island_slots=[120, 121],
    )

    captured = []

    async def _callback(_game_id, _actor_id, action, suppress_broadcast=False):
        captured.append((action, suppress_broadcast))
        engine.apply(action)

    publish_calls: list[uuid.UUID] = []

    def _fake_publish(game_id):
        publish_calls.append(game_id)
        return True

    game_id = uuid.uuid4()

    def _select(*, game_id, engine, actor_id, action_mask=None):
        mask = action_mask if action_mask is not None else engine.get_action_mask()
        for idx in range(120, 132):
            if idx < len(mask) and mask[idx]:
                return idx, None
        for idx in range(140, 152):
            if idx < len(mask) and mask[idx]:
                return idx, None
        return 15, None

    with patch.object(GameService, "broadcast_current_state", staticmethod(_fake_publish)):
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

    assert [s for _a, s in captured] == [True, False]
    # No compensating publish — the final non-suppressed apply already broadcast.
    assert publish_calls == []


@pytest.mark.asyncio
async def test_mayor_batch_zero_applied_actions_does_not_publish():
    """If the loop exits before applying any action, there is nothing to compensate for."""
    engine = _FakeMayorEngine(
        remaining=1,
        legal_island_slots=[120],
    )
    # Force phase to non-MAYOR so the very first iteration hits `mayor_batch_stop`.
    engine.env.game.current_phase = Phase.CRAFTSMAN

    async def _callback(_game_id, _actor_id, action, suppress_broadcast=False):
        engine.apply(action)

    publish_calls: list[uuid.UUID] = []

    def _fake_publish(game_id):
        publish_calls.append(game_id)
        return True

    game_id = uuid.uuid4()

    def _select(*, game_id, engine, actor_id, action_mask=None):
        mask = action_mask if action_mask is not None else engine.get_action_mask()
        for idx in range(120, 132):
            if idx < len(mask) and mask[idx]:
                return idx, None
        for idx in range(140, 152):
            if idx < len(mask) and mask[idx]:
                return idx, None
        return 15, None

    with patch.object(GameService, "broadcast_current_state", staticmethod(_fake_publish)):
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

    assert engine.applied_actions == []
    assert publish_calls == []


def test_bot_turn_delivery_state_defaults():
    """Sanity: dataclass starts with the invariant cleared."""
    state = BotTurnDeliveryState()
    assert state.actions_applied == 0
    assert state.visible_publish_emitted is False
