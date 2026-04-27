"""Tests for app.services.canonical_state.build_canonical_state."""
import pytest

from app.engine_wrapper.wrapper import EngineWrapper
from app.services.canonical_state import (
    CANONICAL_STATE_VERSION,
    build_canonical_state,
)
from app.services.engine_gateway.constants import BuildingType, Phase, TileType


@pytest.fixture
def three_player_engine():
    """3인 게임의 초기 상태 EngineWrapper를 반환한다."""
    engine = EngineWrapper(num_players=3)
    return engine


@pytest.fixture
def three_player_engine_at_mayor():
    """Mayor phase 상태로 강제 전환된 3인 EngineWrapper."""
    engine = EngineWrapper(num_players=3, governor_idx=0)
    game = engine.env.game
    game.current_phase = Phase.MAYOR
    game.current_player_idx = 0
    game.active_role_player = 0
    game.players_taken_action = 0
    for p in game.players:
        p.unplaced_colonists = 3
        p.island_board = []
        p.city_board = []
        p.place_plantation(TileType.CORN_PLANTATION)
        p.place_plantation(TileType.INDIGO_PLANTATION)
        p.build_building(BuildingType.SMALL_INDIGO_PLANT)
        p.build_building(BuildingType.SMALL_MARKET)
    engine.env.agent_selection = "player_0"
    engine._refresh_cached_view()
    return engine


def test_canonical_state_has_required_schema_version(three_player_engine):
    state = build_canonical_state(three_player_engine)
    assert state["schema_version"] == CANONICAL_STATE_VERSION


def test_canonical_state_meta_fields(three_player_engine):
    state = build_canonical_state(three_player_engine)
    meta = state["meta"]
    assert set(meta.keys()) >= {
        "phase_id", "current_player_idx", "governor_idx",
        "round", "step_count", "num_players",
    }
    assert isinstance(meta["phase_id"], int)
    assert 0 <= meta["current_player_idx"] < 3
    assert meta["num_players"] == 3


def test_canonical_state_player_count_matches(three_player_engine):
    state = build_canonical_state(three_player_engine)
    assert len(state["players"]) == state["meta"]["num_players"]


def test_canonical_state_goods_supply_has_five_goods(three_player_engine):
    state = build_canonical_state(three_player_engine)
    goods = state["global"]["goods_supply"]
    assert set(goods.keys()) == {"corn", "indigo", "sugar", "tobacco", "coffee"}
    for v in goods.values():
        assert isinstance(v, int)
        assert v >= 0


def test_canonical_state_player_has_derived_fields(three_player_engine):
    state = build_canonical_state(three_player_engine)
    player = state["players"][0]
    assert "has_building" in player
    assert "production_capacity" in player
    assert set(player["production_capacity"].keys()) == {
        "corn", "indigo", "sugar", "tobacco", "coffee"
    }


def test_canonical_state_cargo_ships(three_player_engine):
    state = build_canonical_state(three_player_engine)
    ships = state["global"]["cargo_ships"]
    assert len(ships) >= 1
    for ship in ships:
        assert set(ship.keys()) >= {"capacity", "good", "load", "space"}
        assert ship["load"] + ship["space"] == ship["capacity"]


def test_canonical_state_trading_house_is_list_of_names(three_player_engine):
    state = build_canonical_state(three_player_engine)
    th = state["global"]["trading_house"]
    assert isinstance(th, list)
    for good in th:
        assert good in {"corn", "indigo", "sugar", "tobacco", "coffee"}


def test_canonical_state_player_island_tiles_have_slot_metadata(three_player_engine_at_mayor):
    state = build_canonical_state(three_player_engine_at_mayor)
    player = state["players"][0]
    assert len(player["island_tiles"]) == 2
    for tile in player["island_tiles"]:
        assert {"slot_idx", "tile_type", "is_occupied"} <= set(tile.keys())


def test_canonical_state_player_city_buildings_exclude_occupied_marker(three_player_engine_at_mayor):
    state = build_canonical_state(three_player_engine_at_mayor)
    player = state["players"][0]
    for b in player["city_buildings"]:
        assert b["building_type"] != int(BuildingType.OCCUPIED_SPACE)
        assert b["max_colonists"] >= 0


def test_canonical_state_phase_id_at_mayor(three_player_engine_at_mayor):
    state = build_canonical_state(three_player_engine_at_mayor)
    assert state["meta"]["phase_id"] == int(Phase.MAYOR)
