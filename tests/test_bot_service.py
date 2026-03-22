import pytest
import asyncio
from app.services.bot_service import BotService
from uuid import uuid4
import numpy as np

@pytest.mark.asyncio
async def test_bot_inference_output_format():
    # Verify the PPO agent loads and returns an int action for valid context.
    game_context = {
        "vector_obs": {
            "global_state": {
                "vp_chips": 12,
                "colonists_supply": 55,
                "colonists_ship": 3,
                "goods_supply": [10, 11, 11, 9, 9],
                "cargo_ships_good": [0, 0, 0],
                "cargo_ships_load": [0, 0, 0],
                "trading_house": [0, 0, 0, 0],
                "role_doubloons": [0] * 8,
                "roles_available": [1] * 8,
                "face_up_plantations": [1, 2, 3, 4],
                "quarry_stack": 8,
                "governor_idx": 0,
                "current_player": 1,
                "current_phase": 0
            },
            "players": {
                "player_0": {
                    "doubloons": 2,
                    "vp_chips": 0,
                    "goods": [0, 0, 0, 0, 0],
                    "island_tiles": [1] + [0]*11,
                    "island_occupied": [1] + [0]*11,
                    "city_buildings": [0]*12,
                    "city_colonists": [0]*12,
                    "unplaced_colonists": 0
                },
                "player_1": {"doubloons": 2, "vp_chips": 0, "goods": [0]*5, "island_tiles": [2]+[0]*11, "island_occupied": [1]+[0]*11, "city_buildings": [0]*12, "city_colonists": [0]*12, "unplaced_colonists": 0},
                "player_2": {"doubloons": 2, "vp_chips": 0, "goods": [0]*5, "island_tiles": [3]+[0]*11, "island_occupied": [1]+[0]*11, "city_buildings": [0]*12, "city_colonists": [0]*12, "unplaced_colonists": 0}
            }
        },
        "action_mask": [1.0] * 200,
        "phase_id": 0
    }
    
    # Run the get_action code directly. Expect int.
    action = BotService.get_action(game_context)
    assert isinstance(action, int)
    assert 0 <= action < 200
