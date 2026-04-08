from app.services.engine_gateway.constants import BuildingType


CANONICAL_BUILDING_NAMES: dict[BuildingType, str] = {
    BuildingType.SMALL_INDIGO_PLANT: "small_indigo_plant",
    BuildingType.SMALL_SUGAR_MILL: "small_sugar_mill",
    BuildingType.INDIGO_PLANT: "indigo_plant",
    BuildingType.SUGAR_MILL: "sugar_mill",
    BuildingType.TOBACCO_STORAGE: "tobacco_storage",
    BuildingType.COFFEE_ROASTER: "coffee_roaster",
    BuildingType.SMALL_MARKET: "small_market",
    BuildingType.HACIENDA: "hacienda",
    BuildingType.CONSTRUCTION_HUT: "construction_hut",
    BuildingType.SMALL_WAREHOUSE: "small_warehouse",
    BuildingType.HOSPICE: "hospice",
    BuildingType.OFFICE: "office",
    BuildingType.LARGE_MARKET: "large_market",
    BuildingType.LARGE_WAREHOUSE: "large_warehouse",
    BuildingType.FACTORY: "factory",
    BuildingType.UNIVERSITY: "university",
    BuildingType.HARBOR: "harbor",
    BuildingType.WHARF: "wharf",
    BuildingType.GUILDHALL: "guild_hall",
    BuildingType.RESIDENCE: "residence",
    BuildingType.FORTRESS: "fortress",
    BuildingType.CUSTOMS_HOUSE: "customs_house",
    BuildingType.CITY_HALL: "city_hall",
}

LEGACY_BUILDING_NAME_ALIASES: dict[str, str] = {
    "guildhall": "guild_hall",
}

BUILDING_NAME_TO_TYPE: dict[str, BuildingType] = {
    name: building_type
    for building_type, name in CANONICAL_BUILDING_NAMES.items()
}


def canonical_building_name(building_type: BuildingType) -> str:
    if building_type in CANONICAL_BUILDING_NAMES:
        return CANONICAL_BUILDING_NAMES[building_type]
    return building_type.name.lower()


def normalize_building_name(name: str) -> str:
    lowered = name.strip().lower()
    return LEGACY_BUILDING_NAME_ALIASES.get(lowered, lowered)
