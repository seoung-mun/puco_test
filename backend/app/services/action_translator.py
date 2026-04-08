"""
Action Translator — maps frontend semantic action payloads to
PuCo_RL integer action indices (0–199).

Action space summary:
  0-7:    select_role       (Role enum value)
  8-13:   settle_plantation (face-up index 0-5)
  14:     settle_quarry
  15:     pass              (all phases)
  16-38:  build             (BuildingType value, 0-22)
  39-43:  sell              (Good value, 0-4)
  44-58:  load_ship         (ship_idx*5 + good_value)
  59-63:  load_wharf        (good_value, ship_idx=-1)
  64-68:  store_windrose    (good_value)
  69-71:  mayor_strategy    (Human/Bot 공통: CAPTAIN_FOCUS=0, TRADE_FACTORY=1, BUILDING=2)
  93-97:  craftsman_priv    (good_value)
  105:    hacienda_draw
  106-110: store_warehouse  (good_value)
"""
import os
import sys

from typing import List, Optional, TYPE_CHECKING
from app.services.engine_gateway.constants import Role, Good, BuildingType, TileType
from app.services.building_names import BUILDING_NAME_TO_TYPE, normalize_building_name

if TYPE_CHECKING:
    pass

# ------------------------------------------------------------------ #
#  Name → enum mappings                                                #
# ------------------------------------------------------------------ #

ROLE_MAP = {
    "settler": Role.SETTLER,
    "mayor": Role.MAYOR,
    "builder": Role.BUILDER,
    "craftsman": Role.CRAFTSMAN,
    "trader": Role.TRADER,
    "captain": Role.CAPTAIN,
    "prospector": Role.PROSPECTOR_1,
    "prospector_1": Role.PROSPECTOR_1,
    "prospector_2": Role.PROSPECTOR_2,
}

GOOD_MAP = {
    "coffee": Good.COFFEE,
    "tobacco": Good.TOBACCO,
    "corn": Good.CORN,
    "sugar": Good.SUGAR,
    "indigo": Good.INDIGO,
}

BUILDING_MAP = dict(BUILDING_NAME_TO_TYPE)

TILE_MAP = {
    # long names (legacy)
    "coffee_plantation": TileType.COFFEE_PLANTATION,
    "tobacco_plantation": TileType.TOBACCO_PLANTATION,
    "corn_plantation": TileType.CORN_PLANTATION,
    "sugar_plantation": TileType.SUGAR_PLANTATION,
    "indigo_plantation": TileType.INDIGO_PLANTATION,
    # short names (sent by frontend)
    "coffee": TileType.COFFEE_PLANTATION,
    "tobacco": TileType.TOBACCO_PLANTATION,
    "corn": TileType.CORN_PLANTATION,
    "sugar": TileType.SUGAR_PLANTATION,
    "indigo": TileType.INDIGO_PLANTATION,
    "quarry": TileType.QUARRY,
}


# ------------------------------------------------------------------ #
#  Translators                                                         #
# ------------------------------------------------------------------ #

def select_role(role: str) -> int:
    r = ROLE_MAP.get(role.lower())
    if r is None:
        raise ValueError(f"Unknown role: {role!r}")
    return r.value   # 0-7


def settle_plantation(plantation: str, face_up: List) -> int:
    """
    plantation: tile type name (e.g. "corn_plantation") or "quarry"
    face_up: game.face_up_plantations (list of TileType values)
    """
    if plantation == "quarry":
        return 14
    tile_type = TILE_MAP.get(plantation.lower())
    if tile_type is None:
        raise ValueError(f"Unknown plantation type: {plantation!r}")
    for i, t in enumerate(face_up):
        if t == tile_type:
            return 8 + i
    raise ValueError(f"Plantation {plantation!r} not in face-up: {face_up}")


def use_hacienda() -> int:
    return 105


def pass_action() -> int:
    return 15


def build(building: str) -> int:
    bt = BUILDING_MAP.get(normalize_building_name(building))
    if bt is None:
        raise ValueError(f"Unknown building: {building!r}")
    return 16 + bt.value   # 16-38


def sell(good: str) -> int:
    g = GOOD_MAP.get(good.lower())
    if g is None:
        raise ValueError(f"Unknown good: {good!r}")
    return 39 + g.value   # 39-43


def load_ship(good: str, ship_index: int, use_wharf: bool) -> int:
    g = GOOD_MAP.get(good.lower())
    if g is None:
        raise ValueError(f"Unknown good: {good!r}")
    if use_wharf:
        return 59 + g.value   # 59-63
    return 44 + (ship_index * 5) + g.value   # 44-58


def craftsman_privilege(good: str) -> int:
    g = GOOD_MAP.get(good.lower())
    if g is None:
        raise ValueError(f"Unknown good: {good!r}")
    return 93 + g.value   # 93-97


def mayor_strategy(strategy_index: int) -> int:
    if not (0 <= strategy_index <= 2):
        raise ValueError(f"Mayor strategy_index {strategy_index} out of range (0-2)")
    return 69 + strategy_index


def store_windrose(good: str) -> int:
    g = GOOD_MAP.get(good.lower())
    if g is None:
        raise ValueError(f"Unknown good: {good!r}")
    return 64 + g.value   # 64-68


def store_warehouse(good: str) -> int:
    g = GOOD_MAP.get(good.lower())
    if g is None:
        raise ValueError(f"Unknown good: {good!r}")
    return 106 + g.value   # 106-110


def discard_sequence(
    protected: List[str],
    single_extra: Optional[str],
    action_mask: List[int],
) -> List[int]:
    """
    Build the sequence of engine steps needed to protect goods before
    the captain store phase ends.

    protected: goods protected by warehouse (up to 2 for large warehouse,
               1 for small warehouse)
    single_extra: one extra good always kept (windrose / free keep)
    action_mask: current valid action mask from the engine

    Returns a list of integer actions to call in order, ending with pass (15).
    """
    actions: List[int] = []

    # Warehouse protection (actions 106-110) — only if valid in mask
    for good in protected:
        action = store_warehouse(good)
        if action < len(action_mask) and action_mask[action]:
            actions.append(action)

    # Windrose / single-extra protection (actions 64-68)
    if single_extra:
        action = store_windrose(single_extra)
        if action < len(action_mask) and action_mask[action]:
            actions.append(action)

    # Finish with pass
    actions.append(15)
    return actions
