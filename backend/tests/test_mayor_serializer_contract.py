import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_mayor_serializer_contract.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.engine_wrapper.wrapper import create_game_engine
from app.services.state_serializer import serialize_game_state_from_engine
from configs.constants import BuildingType, Phase, TileType


def _prepare_engine():
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
    player.place_plantation(TileType.CORN_PLANTATION)
    player.place_plantation(TileType.INDIGO_PLANTATION)
    player.build_building(BuildingType.SMALL_INDIGO_PLANT)
    player.build_building(BuildingType.SMALL_MARKET)

    game._init_mayor_placement(0)
    engine._refresh_cached_view()
    return engine


def test_mayor_serializer_exposes_slot_ids_for_island_and_city():
    engine = _prepare_engine()
    state = serialize_game_state_from_engine(engine, ["Alice", "Bot1", "Bot2"], game_id="g")
    player = state["players"]["player_0"]

    assert player["island"]["plantations"][0]["slot_id"] == "island:corn:0"
    assert player["island"]["plantations"][1]["slot_id"] == "island:indigo:1"
    assert player["city"]["buildings"][0]["slot_id"] == "city:small_indigo_plant:0"
    assert player["city"]["buildings"][1]["slot_id"] == "city:small_market:1"


def test_mayor_serializer_exposes_capacity_metadata():
    engine = _prepare_engine()
    state = serialize_game_state_from_engine(engine, ["Alice", "Bot1", "Bot2"], game_id="g")
    player = state["players"]["player_0"]

    assert player["island"]["plantations"][0]["capacity"] == 1
    assert player["city"]["buildings"][0]["capacity"] == 1
    assert player["city"]["buildings"][1]["capacity"] == 1
