import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_priority1_task1.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.engine_wrapper.wrapper import create_game_engine
from app.services.state_serializer import serialize_game_state_from_engine
from app.services.action_translator import mayor_toggle
from configs.constants import BuildingType, Phase, TileType


def _prepare_mayor_cursor_engine():
    engine = create_game_engine(num_players=3)
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

    game.action_mayor_place(0, 0)
    engine._refresh_cached_view()
    state_after_skip = serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot1", "Bot2"],
        game_id="priority1-task1",
    )
    assert state_after_skip["meta"]["mayor_slot_idx"] == 1
    assert state_after_skip["meta"]["mayor_can_skip"] is False


def test_mayor_frontend_slot_mapping_is_out_of_sync_with_engine_cursor_model():
    engine = _prepare_mayor_cursor_engine()
    game = engine.env.game

    game.action_mayor_place(0, 0)
    game.action_mayor_place(0, 1)
    engine._refresh_cached_view()

    mask = engine.get_action_mask()
    assert game.mayor_placement_idx == 12

    current_cursor_action = 70  # place 1 on current slot
    frontend_city_slot_action = mayor_toggle("city", 0)  # 81

    assert mask[current_cursor_action] == 1
    assert frontend_city_slot_action == 81
    assert mask[frontend_city_slot_action] == 0
