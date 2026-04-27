"""Action index contract regression: face_up + mayor metas use semantic engine_action_index."""
from __future__ import annotations

from app.services.engine_gateway.constants import Good, TileType
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
