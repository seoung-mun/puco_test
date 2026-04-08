from app.services.engine_gateway.constants import TileType

from app.services.building_names import normalize_building_name


def make_island_slot_id(tile_type_name: str, index: int) -> str:
    return f"island:{tile_type_name}:{index}"


def make_city_slot_id(building_name: str, index: int) -> str:
    return f"city:{building_name}:{index}"


def normalize_city_slot_id(slot_id: str) -> str:
    parts = slot_id.split(":")
    if len(parts) != 3 or parts[0] != "city":
        return slot_id
    return make_city_slot_id(normalize_building_name(parts[1]), parts[2])


_TILE_SLOT_NAME = {
    TileType.COFFEE_PLANTATION: "coffee",
    TileType.TOBACCO_PLANTATION: "tobacco",
    TileType.CORN_PLANTATION: "corn",
    TileType.SUGAR_PLANTATION: "sugar",
    TileType.INDIGO_PLANTATION: "indigo",
    TileType.QUARRY: "quarry",
}


def slot_tile_name(tile_type: TileType) -> str:
    return _TILE_SLOT_NAME.get(tile_type, tile_type.name.lower())
