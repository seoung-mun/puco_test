import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_priority2_snapshot.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.engine_wrapper.wrapper import create_game_engine
from app.services.bot_service import BotService
from app.services.state_serializer import PHASE_TO_STR, apply_backend_action_mask_guards, serialize_game_state_from_engine
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

    guarded_mask = apply_backend_action_mask_guards(engine.env.game, snapshot.action_mask)
    assert guarded_mask == state["action_mask"]
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
