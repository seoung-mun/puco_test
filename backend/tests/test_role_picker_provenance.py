from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_role_picker_provenance.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.services.state_serializer_support import serialize_common_board
from configs.constants import Role
from env.engine import PuertoRicoGame


def test_serialize_common_board_uses_actual_picker_for_active_and_prior_roles():
    game = PuertoRicoGame(num_players=4, seed=7)
    game.start_game()

    first_picker = game.current_player_idx
    game.select_role(first_picker, Role.PROSPECTOR_1)

    second_picker = game.current_player_idx
    game.select_role(second_picker, Role.SETTLER)

    board = serialize_common_board(game)

    assert board["roles"]["prospector_1"]["taken_by"] == f"player_{first_picker}"
    assert board["roles"]["settler"]["taken_by"] == f"player_{second_picker}"
    assert board["roles"]["settler"].get("action_index") is None
    assert board["roles"]["mayor"]["action_index"] == Role.MAYOR.value


def test_role_picker_map_clears_when_round_ends():
    game = PuertoRicoGame(num_players=4, seed=7)
    game.start_game()

    picker = game.current_player_idx
    game.select_role(picker, Role.PROSPECTOR_1)

    assert game.role_pickers_by_role == {Role.PROSPECTOR_1: picker}

    game._end_round()

    assert game.role_pickers_by_role == {}


def test_role_picker_map_starts_clean_on_game_init():
    game = PuertoRicoGame(num_players=4, seed=7)
    game.role_pickers_by_role = {Role.SETTLER: 2}

    game.start_game()

    assert game.role_pickers_by_role == {}


def test_serialize_common_board_recovers_picker_from_round_order_when_map_is_missing():
    game = PuertoRicoGame(num_players=4, seed=7)
    game.start_game()

    first_picker = game.current_player_idx
    game.select_role(first_picker, Role.PROSPECTOR_1)
    second_picker = game.current_player_idx
    game.select_role(second_picker, Role.SETTLER)

    game.role_pickers_by_role = {}

    board = serialize_common_board(game)

    assert board["roles"]["prospector_1"]["taken_by"] == f"player_{first_picker}"
    assert board["roles"]["settler"]["taken_by"] == f"player_{second_picker}"
