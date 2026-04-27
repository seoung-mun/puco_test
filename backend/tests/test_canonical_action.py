"""Tests for app.services.canonical_action.build_canonical_action_catalog."""
import pytest

from app.engine_wrapper.wrapper import EngineWrapper
from app.services.canonical_action import (
    CANONICAL_ACTION_VERSION,
    build_canonical_action_catalog,
)
from app.services.canonical_state import build_canonical_state
from app.services.engine_gateway.constants import BuildingType, Phase, TileType


@pytest.fixture
def three_player_engine():
    return EngineWrapper(num_players=3)


@pytest.fixture
def three_player_engine_at_mayor():
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


def test_catalog_schema_version(three_player_engine):
    state = build_canonical_state(three_player_engine)
    mask = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    assert catalog["schema_version"] == CANONICAL_ACTION_VERSION


def test_catalog_only_contains_legal_actions(three_player_engine):
    state = build_canonical_state(three_player_engine)
    mask = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    expected_count = sum(1 for v in mask if v > 0.5)
    assert catalog["total_legal"] == expected_count
    assert len(catalog["legal_actions"]) == expected_count


def test_catalog_entries_have_required_fields(three_player_engine):
    state = build_canonical_state(three_player_engine)
    mask = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    for entry in catalog["legal_actions"]:
        assert "canonical_id" in entry
        assert "engine_action" in entry
        assert "category" in entry
        assert "detail" in entry


def test_role_selection_catalog_entries(three_player_engine):
    state = build_canonical_state(three_player_engine)
    mask = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    role_entries = [e for e in catalog["legal_actions"] if e["category"] == "role"]
    assert len(role_entries) > 0
    for entry in role_entries:
        assert entry["canonical_id"].startswith("role:")
        assert 0 <= entry["engine_action"] <= 7


def test_mayor_catalog_has_tile_type_detail(three_player_engine_at_mayor):
    state = build_canonical_state(three_player_engine_at_mayor)
    mask = three_player_engine_at_mayor.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    island_entries = [
        e for e in catalog["legal_actions"]
        if e["category"] == "mayor" and e["detail"].get("target") == "island"
    ]
    assert len(island_entries) >= 1
    for entry in island_entries:
        assert "tile_type" in entry["detail"]
        assert "tile_name" in entry["detail"]


def test_mayor_catalog_has_city_entries_with_building_type(three_player_engine_at_mayor):
    state = build_canonical_state(three_player_engine_at_mayor)
    mask = three_player_engine_at_mayor.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    city_entries = [
        e for e in catalog["legal_actions"]
        if e["category"] == "mayor" and e["detail"].get("target") == "city"
    ]
    assert len(city_entries) >= 1
    for entry in city_entries:
        assert "building_type" in entry["detail"]
