import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_hacienda_turn_flow.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.engine_wrapper.wrapper import create_game_engine
from app.services.state_serializer import serialize_game_state_from_engine
from env.components import CityBuilding
from configs.constants import BuildingType


def test_hacienda_draw_keeps_same_player_turn_and_regular_settler_choice():
    engine = create_game_engine(num_players=3)
    game = engine.env.game
    active_idx = game.current_player_idx
    active_player = game.players[active_idx]

    active_player.city_board.append(
        CityBuilding(building_type=BuildingType.HACIENDA, colonists=1)
    )

    starting_island_tiles = len(game.players[active_idx].island_board)
    engine.step(0)  # Select Settler; upstream env auto-resolves Hacienda draw
    state = serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bob", "Carol"],
    )

    assert state["meta"]["phase"] == "settler_action"
    assert state["meta"]["active_player"] == f"player_{active_idx}"
    assert state["players"][f"player_{active_idx}"]["hacienda_used_this_phase"] is True
    assert len(game.players[active_idx].island_board) == starting_island_tiles + 1
    assert state["action_mask"][105] == 0
    assert state["action_mask"][15] == 0
    assert any(state["action_mask"][8:15])
