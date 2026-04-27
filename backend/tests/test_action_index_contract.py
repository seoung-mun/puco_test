"""Action index contract regression: face_up + mayor metas use semantic engine_action_index."""
from __future__ import annotations

import pytest
from app.engine_wrapper.wrapper import EngineWrapper
from app.services.engine_gateway.constants import BuildingType, Good, TileType
from app.services.state_serializer import serialize_game_state_from_engine
from app.services.state_serializer_support import serialize_common_board


class _StubGame:
    """Minimal stub mirroring PuertoRicoGame fields used by serialize_common_board."""

    def __init__(self, face_up_tiles):
        self.face_up_plantations = face_up_tiles
        self.available_roles = []
        self.roles_in_play = []
        self.role_doubloons = {}
        self.active_role = None
        self.trading_house = []
        self.plantation_stack = []
        self.cargo_ships = []
        self.building_supply = {}
        self.quarry_stack = 0
        self.goods_supply = {g: 0 for g in Good}
        self.colonists_ship = 0
        self.colonists_supply = 0


def _force_phase_mayor(engine: EngineWrapper, island_tiles, city_buildings):
    """Forcefully set engine state to MAYOR with given island/city slots.

    실제 forcing 로직은 GREEN 단계(Task 7/8) 진행 시점에 EngineWrapper API에
    맞춰 채운다. 현 시점에서는 RED 잠금이 목적이므로 NotImplementedError로 둔다.
    """
    raise NotImplementedError


@pytest.fixture
def make_session_in_mayor_phase():
    def _factory(*, island_layout=None, city_buildings=None):
        engine = EngineWrapper(num_players=3)
        engine.reset()
        _force_phase_mayor(engine, island_layout or [], city_buildings or [])
        return engine
    return _factory


def session_state_dict(engine):
    return serialize_game_state_from_engine(engine, ["A", "B", "C"], game_id="test")


def test_face_up_engine_action_index_uses_tile_type_value():
    # face_up 순서가 [CORN, COFFEE]일 때 corn entry는 8 + Good.CORN.value(=2) = 10이어야 한다.
    game = _StubGame(
        face_up_tiles=[TileType.CORN_PLANTATION, TileType.COFFEE_PLANTATION],
    )
    board = serialize_common_board(game)
    face_up = board["available_plantations"]["face_up"]

    by_type = {entry["type"]: entry for entry in face_up}
    assert by_type["corn"]["engine_action_index"] == 10
    assert by_type["coffee"]["engine_action_index"] == 8
    # backwards-compat: action_index도 같은 값(의미)이어야 한다.
    assert by_type["corn"]["action_index"] == 10
    assert by_type["coffee"]["action_index"] == 8
    # display_position은 face_up 순서를 그대로 유지한다.
    assert by_type["corn"]["display_position"] == 0
    assert by_type["coffee"]["display_position"] == 1
    # canonical_id는 settler:tile_type:{name}.
    assert by_type["corn"]["canonical_id"] == "settler:tile_type:corn"
    assert by_type["coffee"]["canonical_id"] == "settler:tile_type:coffee"


def test_mayor_island_actions_use_tile_type_value(make_session_in_mayor_phase):
    """mayor_island_actions의 engine_action_index는 120 + tile.value 이어야 한다."""
    session = make_session_in_mayor_phase(
        island_layout=["corn", "coffee", "indigo"],
    )
    state = session_state_dict(session)
    actions = state["meta"]["mayor_island_actions"]

    by_tile = {a["tile_name"]: a for a in actions}
    # Good enum: COFFEE=0, TOBACCO=1, CORN=2, SUGAR=3, INDIGO=4
    assert by_tile["corn"]["engine_action_index"] == 122
    assert by_tile["coffee"]["engine_action_index"] == 120
    assert by_tile["indigo"]["engine_action_index"] == 124
    assert by_tile["corn"]["canonical_id"] == "mayor:island:tile_type:corn"


def test_mayor_city_actions_use_building_type_value(make_session_in_mayor_phase):
    """mayor_city_actions의 engine_action_index는 140 + building_type.value 이어야 한다."""
    session = make_session_in_mayor_phase(
        city_buildings=["small_market", "indigo_plant"],
    )
    state = session_state_dict(session)
    actions = state["meta"]["mayor_city_actions"]

    by_name = {a["building_name"]: a for a in actions}
    for entry in actions:
        bt = BuildingType[entry["building_name"].upper()]
        assert entry["engine_action_index"] == 140 + bt.value
        assert entry["canonical_id"] == f"mayor:city:building_type:{bt.value}"
