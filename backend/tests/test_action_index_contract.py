"""Action index contract regression: face_up + mayor metas use semantic engine_action_index."""
from __future__ import annotations

from app.services.engine_gateway.constants import BUILDING_DATA, BuildingType, Good, Phase, TileType
from app.services.state_serializer import _build_mayor_meta
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


class _StubTile:
    def __init__(self, tile_type: TileType, is_occupied: bool = False):
        self.tile_type = tile_type
        self.is_occupied = is_occupied


class _StubBuilding:
    def __init__(self, building_type: BuildingType, colonists: int = 0):
        self.building_type = building_type
        self.colonists = colonists


class _StubPlayer:
    def __init__(self, island_board, city_board, unplaced_colonists: int = 1):
        self.island_board = island_board
        self.city_board = city_board
        self.unplaced_colonists = unplaced_colonists


class _StubMayorGame:
    """game stub for _build_mayor_meta (Phase.MAYOR)."""

    def __init__(self, *, island_tiles, city_buildings):
        island_board = [_StubTile(t) for t in island_tiles]
        # 12-slot island: pad with EMPTY for realism (not strictly required by helper)
        city_board = [_StubBuilding(b) for b in city_buildings]

        self.current_phase = Phase.MAYOR
        self.current_player_idx = 0
        self.players = [_StubPlayer(island_board, city_board)]


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


def test_face_up_quarry_uses_engine_index_13():
    """Quarry는 13 (의미 인덱스), canonical_id는 settler:quarry."""
    game = _StubGame(face_up_tiles=[TileType.QUARRY])
    board = serialize_common_board(game)
    face_up = board["available_plantations"]["face_up"]

    quarry = next(e for e in face_up if e["type"] == "quarry")
    assert quarry["engine_action_index"] == 13
    assert quarry["action_index"] == 13
    assert quarry["canonical_id"] == "settler:quarry"


def test_mayor_island_actions_use_tile_type_value():
    """mayor_island_actions의 engine_action_index는 120 + tile.value 이어야 한다."""
    game = _StubMayorGame(
        island_tiles=[TileType.CORN_PLANTATION, TileType.COFFEE_PLANTATION, TileType.INDIGO_PLANTATION],
        city_buildings=[],
    )
    meta = _build_mayor_meta(game)
    actions = meta["mayor_island_actions"]

    by_tile = {a["tile_name"]: a for a in actions}
    # Good enum: COFFEE=0, TOBACCO=1, CORN=2, SUGAR=3, INDIGO=4
    assert by_tile["corn"]["engine_action_index"] == 122
    assert by_tile["coffee"]["engine_action_index"] == 120
    assert by_tile["indigo"]["engine_action_index"] == 124
    assert by_tile["corn"]["canonical_id"] == "mayor:island:tile_type:corn"


def test_mayor_city_actions_use_building_type_value():
    """mayor_city_actions의 engine_action_index는 140 + building_type.value 이어야 한다."""
    game = _StubMayorGame(
        island_tiles=[],
        city_buildings=[BuildingType.SMALL_MARKET, BuildingType.SMALL_INDIGO_PLANT],
    )
    meta = _build_mayor_meta(game)
    actions = meta["mayor_city_actions"]

    by_name = {a["building_name"]: a for a in actions}
    assert "small_market" in by_name
    assert "small_indigo_plant" in by_name
    assert by_name["small_market"]["engine_action_index"] == 140 + int(BuildingType.SMALL_MARKET.value)
    assert by_name["small_indigo_plant"]["engine_action_index"] == 140 + int(BuildingType.SMALL_INDIGO_PLANT.value)
    assert by_name["small_market"]["canonical_id"] == f"mayor:city:building_type:{int(BuildingType.SMALL_MARKET.value)}"
