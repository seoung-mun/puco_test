import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_terminal_result_summary.db")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.engine_wrapper.wrapper import create_game_engine
from app.services.state_serializer import compute_score_breakdown, serialize_game_state_from_engine


def test_terminal_state_embeds_result_summary():
    engine = create_game_engine(num_players=3)
    player_names = ["Alice", "Bot 1", "Bot 2"]

    engine.env.terminations = {agent: True for agent in engine.env.terminations}
    engine.env.truncations = {agent: False for agent in engine.env.truncations}

    state = serialize_game_state_from_engine(
        engine=engine,
        player_names=player_names,
        game_id="terminal-game",
        bot_players={1: "random", 2: "random"},
    )

    assert state["meta"]["end_game_triggered"] is True
    assert state["meta"]["phase"] == "game_over"
    assert state["result_summary"] == compute_score_breakdown(engine.env.game, player_names)


def test_non_terminal_state_has_no_result_summary():
    engine = create_game_engine(num_players=3)

    state = serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot 1", "Bot 2"],
        game_id="in-progress-game",
        bot_players={1: "random", 2: "random"},
    )

    assert state["meta"]["end_game_triggered"] is False
    assert state["result_summary"] is None


def test_score_breakdown_uses_stable_player_refs_for_duplicate_display_names():
    engine = create_game_engine(num_players=3)

    result_summary = compute_score_breakdown(
        engine.env.game,
        ["Bot (ppo)", "Bot (ppo)", "Bot (ppo)"],
    )

    assert result_summary["player_order"] == ["player_0", "player_1", "player_2"]
    assert result_summary["winner"] in result_summary["player_order"]
    assert set(result_summary["scores"].keys()) == {"player_0", "player_1", "player_2"}
    assert result_summary["display_names"] == {
        "player_0": "Bot (ppo)",
        "player_1": "Bot (ppo)",
        "player_2": "Bot (ppo)",
    }
