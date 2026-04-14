"""
Tests for Mayor large building masking fix.

Root cause: OCCUPIED_SPACE filtering in serialize_player creates index
mismatch between mayor_legal_city_slots (raw engine indices) and
frontend buildings array (filtered indices).

Fix: add engine_slot_idx to each building, convert mayor_legal_city_slots
to filtered indices.
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_mayor_large_building.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.engine_wrapper.wrapper import create_game_engine
from app.services.state_serializer import serialize_game_state_from_engine
from configs.constants import BuildingType, Phase, TileType


def _prepare_large_building_engine():
    """Set up a mayor phase with two large buildings (Guildhall + City Hall)."""
    engine = create_game_engine(num_players=3)
    game = engine.env.game
    game.current_phase = Phase.MAYOR
    game.current_player_idx = 0
    game.active_role_player = 0
    game.players_taken_action = 0

    player = game.players[0]
    player.unplaced_colonists = 5
    player.island_board = []
    player.city_board = []

    # Build: SmallIndigo(slot0), Guildhall(slot1)+OCCUPIED(slot2), CityHall(slot3)+OCCUPIED(slot4)
    player.build_building(BuildingType.SMALL_INDIGO_PLANT)
    player.build_building(BuildingType.GUILDHALL)
    player.build_building(BuildingType.CITY_HALL)

    player.place_plantation(TileType.CORN_PLANTATION)

    engine.env.agent_selection = "player_0"
    engine._refresh_cached_view()
    return engine


def _serialize(engine):
    return serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bot1", "Bot2"],
        game_id="large-building-test",
    )


# ------------------------------------------------------------------ #
# Cycle 1: engine_slot_idx must be present in building data
# ------------------------------------------------------------------ #

def test_buildings_have_engine_slot_idx():
    """Each building in serialized data must expose its raw engine city_board index."""
    engine = _prepare_large_building_engine()
    state = _serialize(engine)
    buildings = state["players"]["player_0"]["city"]["buildings"]

    # 3 buildings visible (OCCUPIED_SPACE filtered out)
    assert len(buildings) == 3

    # engine_slot_idx must match raw city_board positions
    assert buildings[0]["engine_slot_idx"] == 0  # SmallIndigo at slot 0
    assert buildings[1]["engine_slot_idx"] == 1  # Guildhall at slot 1
    assert buildings[2]["engine_slot_idx"] == 3  # CityHall at slot 3 (slot 2 is OCCUPIED_SPACE)


# ------------------------------------------------------------------ #
# Cycle 2: mayor_legal_city_slots must use filtered indices
# ------------------------------------------------------------------ #

def test_mayor_legal_city_slots_use_filtered_indices():
    """mayor_legal_city_slots must match buildings array indices, not raw engine indices."""
    engine = _prepare_large_building_engine()
    state = _serialize(engine)

    legal_city = state["meta"]["mayor_legal_city_slots"]
    buildings = state["players"]["player_0"]["city"]["buildings"]

    # All 3 buildings have 0 colonists, all should be legal
    # Filtered indices: SmallIndigo=0, Guildhall=1, CityHall=2
    assert legal_city == [0, 1, 2]

    # Verify each legal index points to a real building
    for idx in legal_city:
        assert idx < len(buildings)
        assert buildings[idx]["current_colonists"] < buildings[idx]["max_colonists"]


def test_mayor_legal_city_slots_after_placing_on_guildhall():
    """After placing colonist on Guildhall, CityHall must still be legal (not masked)."""
    engine = _prepare_large_building_engine()
    game = engine.env.game
    player = game.players[0]

    # Directly simulate: Guildhall (city_board slot 1) gets 1 colonist
    player.city_board[1].colonists = 1
    player.unplaced_colonists = 4

    engine._refresh_cached_view()
    state = _serialize(engine)
    legal_city = state["meta"]["mayor_legal_city_slots"]
    buildings = state["players"]["player_0"]["city"]["buildings"]

    # Guildhall now full (capacity 1), SmallIndigo and CityHall still legal
    # Filtered: SmallIndigo=0, CityHall=2 (Guildhall=1 is full)
    assert 0 in legal_city   # SmallIndigo
    assert 1 not in legal_city  # Guildhall (full)
    assert 2 in legal_city   # CityHall — THIS IS THE BUG: currently returns 3 (raw index)

    # Verify CityHall is accessible at filtered index 2
    city_hall = buildings[2]
    assert city_hall["name"] == "city_hall"
    assert city_hall["current_colonists"] == 0
