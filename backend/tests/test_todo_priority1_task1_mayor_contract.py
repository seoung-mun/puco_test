import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_priority1_task1.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.engine_wrapper.wrapper import create_game_engine
from app.services.mayor_orchestrator import MayorPlacement, translate_plan_to_actions
from app.services.state_serializer import serialize_game_state_from_engine
from configs.constants import BuildingType, Phase, TileType


def _prepare_mayor_cursor_engine():
    engine = create_game_engine(num_players=3, governor_idx=0)
    game = engine.env.game

    game.current_phase = Phase.MAYOR
    game.current_player_idx = 0
    game.active_role_player = 0
    game.players_taken_action = 0

    player = game.players[0]
    player.unplaced_colonists = 3
    player.island_board = []
    player.city_board = []
    player.place_plantation(TileType.CORN_PLANTATION)  # slot 0
    player.place_plantation(TileType.INDIGO_PLANTATION)  # slot 1
    player.build_building(BuildingType.SMALL_INDIGO_PLANT)  # slot 12
    player.build_building(BuildingType.SMALL_MARKET)  # slot 13

    game._init_mayor_placement(0)
    engine.env.agent_selection = f"player_{game.current_player_idx}"
    engine._refresh_cached_view()
    return engine


def test_mayor_slot_progression_is_island_then_city_current_behavior():
    engine = _prepare_mayor_cursor_engine()
    game = engine.env.game

    assert game.mayor_placement_idx == 0

    game.action_mayor_place(0, 0)
    assert game.mayor_placement_idx == 1

    game.action_mayor_place(0, 1)
    assert game.mayor_placement_idx == 12

    game.action_mayor_place(0, 1)
    assert game.mayor_placement_idx == 13


def test_mayor_serializer_slot_idx_matches_engine_cursor():
    engine = _prepare_mayor_cursor_engine()
    game = engine.env.game

    initial_state = serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot1", "Bot2"],
        game_id="priority1-task1",
    )
    assert initial_state["meta"]["mayor_slot_idx"] == 0
    assert initial_state["meta"]["mayor_can_skip"] is True
    assert initial_state["players"]["player_0"]["island"]["plantations"][0]["slot_id"] == "island:corn:0"

    game.action_mayor_place(0, 0)
    engine._refresh_cached_view()
    state_after_skip = serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot1", "Bot2"],
        game_id="priority1-task1",
    )
    assert state_after_skip["meta"]["mayor_slot_idx"] == 1
    assert state_after_skip["meta"]["mayor_can_skip"] is False


def test_mayor_serializer_slot_ids_follow_engine_cursor_model():
    engine = _prepare_mayor_cursor_engine()
    game = engine.env.game

    game.action_mayor_place(0, 0)
    game.action_mayor_place(0, 1)
    assert game.mayor_placement_idx == 12
    state = serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot1", "Bot2"],
        game_id="priority1-task1",
    )
    assert state["players"]["player_0"]["city"]["buildings"][0]["slot_id"] == "city:small_indigo_plant:0"


def test_mayor_serializer_island_slot_ids_are_accepted_by_orchestrator():
    engine = _prepare_mayor_cursor_engine()
    state = serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot1", "Bot2"],
        game_id="priority1-task1",
    )

    slot_id = state["players"]["player_0"]["island"]["plantations"][0]["slot_id"]
    actions = translate_plan_to_actions(
        engine.env.game,
        0,
        [MayorPlacement(slot_id=slot_id, count=1)],
    )

    assert actions[0] == 70
