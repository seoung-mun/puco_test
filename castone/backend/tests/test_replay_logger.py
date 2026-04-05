import json
import uuid

from app.engine_wrapper.wrapper import create_game_engine
from app.services.replay_logger import (
    ReplayLogger,
    build_final_scores_payload,
    build_replay_entry,
    describe_action,
    summarize_transition_state,
)


def _sample_state() -> dict:
    return {
        "global_state": {
            "vp_chips": 75,
            "colonists_supply": 55,
            "colonists_ship": 3,
            "face_up_plantations": [2, 1, 0, 3],
            "governor_idx": 1,
            "current_player": 0,
            "current_phase": 8,
            "mayor_slot_idx": 4,
        },
        "players": {
            "player_0": {
                "doubloons": 2,
                "vp_chips": 0,
                "goods": [0, 0, 1, 0, 0],
                "island_tiles": [2, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
                "city_buildings": [24] * 12,
                "unplaced_colonists": 0,
            },
            "player_1": {
                "doubloons": 2,
                "vp_chips": 0,
                "goods": [0, 0, 0, 0, 0],
                "island_tiles": [4, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
                "city_buildings": [24] * 12,
                "unplaced_colonists": 0,
            },
            "player_2": {
                "doubloons": 2,
                "vp_chips": 0,
                "goods": [0, 0, 0, 0, 0],
                "island_tiles": [4, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6],
                "city_buildings": [24] * 12,
                "unplaced_colonists": 0,
            },
        },
    }


def test_describe_action_matches_human_readable_replay_strings():
    state = _sample_state()

    assert describe_action(2, state_before=state) == "Select Role: Builder"
    assert describe_action(8, state_before=state) == "Settler: Take Corn Plantation"
    assert describe_action(16, state_before=state) == "Builder: Build Small Indigo Plant (cost 1, VP 1)"
    assert describe_action(39, state_before=state) == "Trader: Sell Coffee (base price 4)"


def test_replay_logger_writes_human_readable_json(tmp_path, monkeypatch):
    replay_dir = tmp_path / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.services.replay_logger.REPLAY_LOG_DIR", str(replay_dir))

    game_id = uuid.uuid4()
    players = [
        {"player": 0, "actor_id": "human-1", "display_name": "Alice", "actor_type": "human", "bot_type": None},
        {"player": 1, "actor_id": "BOT_random", "display_name": "Bot (random)", "actor_type": "bot", "bot_type": "random"},
        {"player": 2, "actor_id": "BOT_ppo", "display_name": "Bot (ppo)", "actor_type": "bot", "bot_type": "ppo"},
    ]
    state_before = _sample_state()
    state_after = _sample_state()
    state_after["global_state"]["current_player"] = 1
    state_after["global_state"]["current_phase"] = 2

    ReplayLogger.initialize_game(
        game_id=game_id,
        title="Replay Room",
        status="PROGRESS",
        host_id="human-1",
        players=players,
        model_versions={"player_2": {"bot_type": "ppo", "artifact_name": "ppo-test"}},
        initial_state_summary=summarize_transition_state(state_before),
    )
    ReplayLogger.append_entry(
        game_id=game_id,
        title="Replay Room",
        status="FINISHED",
        host_id="human-1",
        players=players,
        model_versions={"player_2": {"bot_type": "ppo", "artifact_name": "ppo-test"}},
        entry=build_replay_entry(
            actor_id="human-1",
            actor_name="Alice",
            player_index=0,
            action=2,
            reward=0.0,
            done=True,
            info={"round": 0, "step": 1},
            state_before=state_before,
            state_after=state_after,
            action_mask_before=[1, 1, 1, 0],
            model_info={"actor_type": "human"},
        ),
        final_scores=[
            {"player": 0, "actor_id": "human-1", "display_name": "Alice", "vp": 32, "tiebreaker": 4, "winner": True}
        ],
        result_summary={"winner": "Alice"},
    )

    replay_path = replay_dir / f"{game_id}.json"
    data = json.loads(replay_path.read_text(encoding="utf-8"))

    assert data["format"] == "backend-replay.v1"
    assert data["title"] == "Replay Room"
    assert data["status"] == "FINISHED"
    assert data["players"][0]["display_name"] == "Alice"
    assert data["entries"][0]["action"] == "Select Role: Builder"
    assert data["entries"][0]["phase"] == "END_ROUND"
    assert data["entries"][0]["value_estimate"] is None
    assert data["entries"][0]["top_actions"] == []
    assert "Phase END_ROUND -> BUILDER" in data["entries"][0]["commentary"]
    assert data["entries"][0]["valid_action_count"] == 3
    assert data["entries"][0]["state_summary_before"]["players"]["player_0"]["plantations"]["corn"] == 1
    assert data["final_scores"][0]["winner"] is True


def test_build_final_scores_payload_matches_terminal_breakdown():
    engine = create_game_engine(num_players=3)
    player_names = ["Alice", "Bot 1", "Bot 2"]
    actor_ids = ["human-1", "BOT_random", "BOT_ppo"]

    final_scores, result_summary = build_final_scores_payload(
        game=engine.env.game,
        player_names=player_names,
        actor_ids=actor_ids,
    )

    assert len(final_scores) == 3
    assert result_summary["winner"] in player_names
    assert all("breakdown" in row for row in final_scores)
