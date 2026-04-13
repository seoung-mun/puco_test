import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_priority2_snapshot.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.engine_wrapper.wrapper import create_game_engine
from app.services.agent_registry import valid_bot_types
from app.services.bot_service import BotService
from app.services.state_serializer import PHASE_TO_STR, serialize_game_state_from_engine
from configs.constants import Phase


def _advance_one_valid_action(engine):
    action_mask = engine.get_action_mask()
    valid_actions = [idx for idx, allowed in enumerate(action_mask) if allowed]
    assert valid_actions, "유효 액션이 하나 이상 있어야 합니다"
    engine.step(valid_actions[0])


def test_bot_input_snapshot_matches_serializer_after_engine_step():
    engine = create_game_engine(num_players=3)
    _advance_one_valid_action(engine)

    snapshot = BotService.build_input_snapshot(engine, "BOT_random")
    state = serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot1", "Bot2"],
        game_id="snapshot-test",
        bot_players={1: "random", 2: "ppo"},
    )

    assert list(snapshot.action_mask) == state["action_mask"]
    assert snapshot.current_player_idx == int(state["meta"]["active_player"].split("_")[1])
    assert snapshot.step_count == engine._step_count
    assert state["meta"]["step_count"] == snapshot.step_count


def test_bot_input_snapshot_phase_matches_engine_info_and_serializer():
    engine = create_game_engine(num_players=3)

    snapshot = BotService.build_input_snapshot(engine, "BOT_ppo")
    state = serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot1", "Bot2"],
        game_id="snapshot-phase-test",
        bot_players={1: "ppo", 2: "random"},
    )

    assert snapshot.phase_id == engine.last_info["current_phase_id"]
    assert state["meta"]["phase"] == PHASE_TO_STR[Phase(snapshot.phase_id)]
    assert state["meta"]["phase_id"] == snapshot.phase_id
    assert snapshot.bot_type == "ppo"


def test_factory_rule_bot_returns_valid_settler_choice():
    engine = create_game_engine(num_players=3)

    initial_mask = engine.get_action_mask()
    assert initial_mask[0] == 1, "게임 시작 직후 Settler 역할 선택이 가능해야 합니다"
    engine.step(0)

    snapshot = BotService.build_input_snapshot(engine, "BOT_factory_rule")
    assert snapshot.phase_id == Phase.SETTLER

    action = BotService.get_action(
        "factory_rule",
        {
            "vector_obs": snapshot.obs,
            "action_mask": snapshot.action_mask,
            "phase_id": snapshot.phase_id,
            "current_player_idx": snapshot.current_player_idx,
        },
    )

    valid_actions = [idx for idx, allowed in enumerate(snapshot.action_mask) if allowed]
    assert action in valid_actions
    assert 8 <= action <= 14
    assert action != 15


def test_latest_agent_types_are_registered():
    types = valid_bot_types()
    assert "shipping_rush" in types
    assert "action_value" in types


def test_shipping_rush_bot_returns_valid_role_choice():
    engine = create_game_engine(num_players=3)
    snapshot = BotService.build_input_snapshot(engine, "BOT_shipping_rush")

    action = BotService.get_action(
        "shipping_rush",
        {
            "vector_obs": snapshot.obs,
            "action_mask": snapshot.action_mask,
            "phase_id": snapshot.phase_id,
            "current_player_idx": snapshot.current_player_idx,
            "env": engine.env,
        },
    )

    valid_actions = [idx for idx, allowed in enumerate(snapshot.action_mask) if allowed]
    assert action in valid_actions
    assert 0 <= action <= 7


def test_action_value_bot_returns_valid_role_choice_with_env_context():
    engine = create_game_engine(num_players=3)
    snapshot = BotService.build_input_snapshot(engine, "BOT_action_value")

    action = BotService.get_action(
        "action_value",
        {
            "vector_obs": snapshot.obs,
            "action_mask": snapshot.action_mask,
            "phase_id": snapshot.phase_id,
            "current_player_idx": snapshot.current_player_idx,
            "env": engine.env,
        },
    )

    valid_actions = [idx for idx, allowed in enumerate(snapshot.action_mask) if allowed]
    assert action in valid_actions
    assert 0 <= action <= 7
