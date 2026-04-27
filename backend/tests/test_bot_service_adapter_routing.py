"""Tests for BotService.get_action adapter vs legacy routing."""
from unittest.mock import MagicMock

import pytest

from app.engine_wrapper.wrapper import EngineWrapper
from app.services import bot_service as bot_service_module
from app.services.adapter_runtime import InferenceResult
from app.services.bot_service import BotService


@pytest.fixture
def three_player_engine():
    return EngineWrapper(num_players=3)


def _legacy_game_context(engine: EngineWrapper) -> dict:
    return {
        "vector_obs": engine.last_obs,
        "action_mask": engine.get_action_mask(),
        "phase_id": 8,
        "current_player_idx": 0,
        "env": engine.env,
        "engine_instance": engine,
    }


def test_get_action_uses_adapter_when_runtime_available(three_player_engine, monkeypatch):
    fake_runtime = MagicMock()
    fake_runtime.infer.return_value = InferenceResult(
        engine_action=3,
        canonical_id="role:settler",
        bundle_id="b1",
        adapter_id="a1",
        phase_id=8,
    )
    monkeypatch.setattr(
        bot_service_module, "get_adapter_runtime", lambda bt: fake_runtime
    )

    ctx = _legacy_game_context(three_player_engine)
    action = BotService.get_action("ppo", ctx)
    assert action == 3
    fake_runtime.infer.assert_called_once_with(three_player_engine)
    assert ctx["adapter_info"]["bundle_id"] == "b1"
    assert ctx["adapter_info"]["fallback_used"] is False


def test_get_action_falls_back_to_wrapper_when_no_runtime(three_player_engine, monkeypatch):
    monkeypatch.setattr(bot_service_module, "get_adapter_runtime", lambda bt: None)

    ctx = _legacy_game_context(three_player_engine)
    action = BotService.get_action("random", ctx)
    assert isinstance(action, int)
    assert 0 <= action < 200
    assert "adapter_info" not in ctx


def test_get_action_falls_back_to_wrapper_when_engine_missing(three_player_engine, monkeypatch):
    fake_runtime = MagicMock()
    monkeypatch.setattr(
        bot_service_module, "get_adapter_runtime", lambda bt: fake_runtime
    )

    ctx = _legacy_game_context(three_player_engine)
    ctx.pop("engine_instance")
    action = BotService.get_action("random", ctx)
    assert isinstance(action, int)
    fake_runtime.infer.assert_not_called()
