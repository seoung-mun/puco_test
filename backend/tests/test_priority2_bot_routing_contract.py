import asyncio
from unittest.mock import MagicMock

import pytest

from app.services.bot_service import BotService


class _WrapperStub:
    def __init__(self, action: int):
        self.action = action
        self.calls = []

    def act(self, obs, mask, phase_id=9, obs_dict=None, player_idx=None, env=None):
        self.calls.append(
            {
                "obs_shape": tuple(obs.shape),
                "mask_shape": tuple(mask.shape),
                "phase_id": phase_id,
                "obs_dict": obs_dict,
                "player_idx": player_idx,
                "env": env,
            }
        )
        return self.action


class TestBotRoutingContract:
    def test_get_action_uses_requested_random_bot_type(self, monkeypatch):
        wrapper = _WrapperStub(action=15)
        requested = {}

        def fake_get_agent_wrapper(cls, bot_type):
            requested["bot_type"] = bot_type
            return wrapper

        monkeypatch.setattr(BotService, "_obs_space", object())
        monkeypatch.setattr(BotService, "_obs_dim", 210)
        monkeypatch.setattr(
            BotService,
            "get_agent_wrapper",
            classmethod(fake_get_agent_wrapper),
        )
        monkeypatch.setattr(
            "app.services.bot_service.flatten_dict_observation",
            lambda raw_obs, obs_space: [0.0, 1.0, 2.0],
        )

        action = BotService.get_action(
            "random",
            {
                "vector_obs": {"global_state": {"current_phase": 8}},
                "action_mask": [0] * 15 + [1],
                "phase_id": 8,
                "current_player_idx": 2,
            },
        )

        assert action == 15
        assert requested["bot_type"] == "random"
        assert wrapper.calls[0]["phase_id"] == 8
        assert wrapper.calls[0]["obs_shape"] == (1, 3)
        assert wrapper.calls[0]["mask_shape"] == (1, 16)
        assert wrapper.calls[0]["player_idx"] == 2
        assert wrapper.calls[0]["obs_dict"] == {"global_state": {"current_phase": 8}}
        assert wrapper.calls[0]["env"] is None

    def test_get_action_uses_requested_ppo_bot_type(self, monkeypatch):
        wrapper = _WrapperStub(action=3)
        requested = {}

        def fake_get_agent_wrapper(cls, bot_type):
            requested["bot_type"] = bot_type
            return wrapper

        monkeypatch.setattr(BotService, "_obs_space", object())
        monkeypatch.setattr(BotService, "_obs_dim", 210)
        monkeypatch.setattr(
            BotService,
            "get_agent_wrapper",
            classmethod(fake_get_agent_wrapper),
        )
        monkeypatch.setattr(
            "app.services.bot_service.flatten_dict_observation",
            lambda raw_obs, obs_space: [5.0, 4.0, 3.0],
        )

        action = BotService.get_action(
            "ppo",
            {
                "vector_obs": {"global_state": {"current_phase": 2}},
                "action_mask": [1, 1, 1, 1],
                "phase_id": 2,
                "current_player_idx": 1,
            },
        )

        assert action == 3
        assert requested["bot_type"] == "ppo"
        assert wrapper.calls[0]["phase_id"] == 2
        assert wrapper.calls[0]["obs_shape"] == (1, 3)
        assert wrapper.calls[0]["mask_shape"] == (1, 4)
        assert wrapper.calls[0]["player_idx"] == 1

    @pytest.mark.asyncio
    async def test_run_bot_turn_resolves_bot_type_from_actor_id(self, monkeypatch):
        engine = MagicMock()
        mask = [0] * 16
        mask[15] = 1
        engine.get_action_mask.return_value = mask
        engine.last_obs = {"global_state": {"current_phase": 8}}

        captured = {}

        def fake_get_action(bot_type, game_context):
            captured["bot_type"] = bot_type
            captured["phase_id"] = game_context["phase_id"]
            return 15

        callback = MagicMock()
        async def fake_sleep(*_args, **_kwargs):
            return None

        monkeypatch.setattr(BotService, "get_action", staticmethod(fake_get_action))
        monkeypatch.setattr("asyncio.sleep", fake_sleep)

        await BotService.run_bot_turn(
            game_id="00000000-0000-0000-0000-000000000000",
            engine=engine,
            actor_id="BOT_ppo",
            process_action_callback=callback,
        )

        assert captured["bot_type"] == "ppo"
        assert captured["phase_id"] == 8
        callback.assert_called_once_with(
            "00000000-0000-0000-0000-000000000000",
            "BOT_ppo",
            15,
        )
