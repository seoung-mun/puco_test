"""
CanonicalStateBuilder - engine state를 모델 서빙/adapter용 표준 상태로 변환.

이 모듈은 frontend rich JSON과 별개의 내부 계약이다.
같은 engine state에서 생성되지만, adapter decode 최적화를 위해 설계됨.
"""
from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from app.services.engine_gateway.constants import (
    BUILDING_DATA,
    BuildingType,
    Good,
    TileType,
)

if TYPE_CHECKING:
    from app.engine_wrapper.wrapper import EngineWrapper

CANONICAL_STATE_VERSION = "castone.canonical-state.v1"

GOOD_ENUM_TO_NAME: Dict[Good, str] = {
    Good.COFFEE: "coffee",
    Good.TOBACCO: "tobacco",
    Good.CORN: "corn",
    Good.SUGAR: "sugar",
    Good.INDIGO: "indigo",
}

# env constants for game_progress calculation (must match env.pr_env._compute_game_progress)
VP_CHIPS_SETUP = {2: 65, 3: 75, 4: 100, 5: 122}
COLONIST_SUPPLY_SETUP = {2: 40, 3: 55, 4: 75, 5: 95}


def _safe_phase_id(phase) -> int:
    """Phase enum -> int. None은 9로 매핑 (env의 one-hot index 9 = None/INIT)."""
    if phase is None:
        return 9
    try:
        return int(phase)
    except (TypeError, ValueError):
        return 9


def _compute_production_capacity(player) -> Dict[str, int]:
    """각 재화의 생산 가능 수량을 계산한다 (env의 _compute_production_capacity와 동일 의미)."""
    raw = {"corn": 0, "indigo": 0, "sugar": 0, "tobacco": 0, "coffee": 0}
    tile_to_good = {
        TileType.CORN_PLANTATION: "corn",
        TileType.INDIGO_PLANTATION: "indigo",
        TileType.SUGAR_PLANTATION: "sugar",
        TileType.TOBACCO_PLANTATION: "tobacco",
        TileType.COFFEE_PLANTATION: "coffee",
    }
    for t in player.island_board:
        good = tile_to_good.get(t.tile_type)
        if good and t.is_occupied:
            raw[good] += 1

    building_cap = {"indigo": 0, "sugar": 0, "tobacco": 0, "coffee": 0}
    indigo_buildings = {BuildingType.SMALL_INDIGO_PLANT, BuildingType.INDIGO_PLANT}
    sugar_buildings = {BuildingType.SMALL_SUGAR_MILL, BuildingType.SUGAR_MILL}
    for b in player.city_board:
        bt = b.building_type
        if bt in indigo_buildings:
            building_cap["indigo"] += b.colonists
        elif bt in sugar_buildings:
            building_cap["sugar"] += b.colonists
        elif bt == BuildingType.TOBACCO_STORAGE:
            building_cap["tobacco"] += b.colonists
        elif bt == BuildingType.COFFEE_ROASTER:
            building_cap["coffee"] += b.colonists

    return {
        "corn": raw["corn"],
        "indigo": min(raw["indigo"], building_cap["indigo"]),
        "sugar": min(raw["sugar"], building_cap["sugar"]),
        "tobacco": min(raw["tobacco"], building_cap["tobacco"]),
        "coffee": min(raw["coffee"], building_cap["coffee"]),
    }


def _build_player_canonical(player, player_idx: int) -> Dict[str, Any]:
    """단일 플레이어의 canonical state를 생성한다."""
    goods = {GOOD_ENUM_TO_NAME[g]: int(v) for g, v in player.goods.items()}

    island_tiles = []
    island_tile_counts: Dict[int, int] = {}
    island_tile_occupied: Dict[int, int] = {}
    for slot_idx, t in enumerate(player.island_board):
        tt = t.tile_type
        island_tiles.append({
            "slot_idx": slot_idx,
            "tile_type": int(tt),
            "is_occupied": bool(t.is_occupied),
        })
        if tt != TileType.EMPTY:
            island_tile_counts[int(tt)] = island_tile_counts.get(int(tt), 0) + 1
            if t.is_occupied:
                island_tile_occupied[int(tt)] = island_tile_occupied.get(int(tt), 0) + 1

    city_buildings = []
    has_building: Dict[int, bool] = {}
    building_colonists: Dict[int, int] = {}
    for slot_idx, b in enumerate(player.city_board):
        bt = b.building_type
        if bt == BuildingType.OCCUPIED_SPACE:
            continue
        bdata = BUILDING_DATA.get(bt)
        if bdata is None:
            continue
        city_buildings.append({
            "slot_idx": slot_idx,
            "building_type": int(bt),
            "colonists": int(b.colonists),
            "max_colonists": int(bdata[2]),
        })
        if bt != BuildingType.EMPTY:
            has_building[int(bt)] = True
            building_colonists[int(bt)] = int(b.colonists)

    production_capacity = _compute_production_capacity(player)

    return {
        "idx": player_idx,
        "doubloons": int(player.doubloons),
        "vp_chips": int(player.vp_chips),
        "goods": goods,
        "unplaced_colonists": int(player.unplaced_colonists),
        "empty_island_spaces": int(player.empty_island_spaces),
        "empty_city_spaces": int(player.empty_city_spaces),
        "island_tiles": island_tiles,
        "city_buildings": city_buildings,
        "has_building": has_building,
        "building_colonists": building_colonists,
        "island_tile_counts": island_tile_counts,
        "island_tile_occupied": island_tile_occupied,
        "production_capacity": production_capacity,
    }


def build_canonical_state(engine: "EngineWrapper") -> Dict[str, Any]:
    """EngineWrapper에서 canonical serving state를 생성한다."""
    game = engine.env.game

    cargo_ships = []
    for ship in game.cargo_ships:
        good_type = getattr(ship, "good_type", None)
        cargo_ships.append({
            "capacity": int(ship.capacity),
            "good": GOOD_ENUM_TO_NAME.get(good_type) if good_type is not None else None,
            "load": int(ship.current_load),
            "space": int(max(0, ship.capacity - ship.current_load)),
        })

    available_roles = [int(r) for r in game.available_roles]
    role_doubloons = {int(r): int(v) for r, v in game.role_doubloons.items()}

    face_up = [int(t) for t in game.face_up_plantations]

    initial_vp = VP_CHIPS_SETUP.get(game.num_players, 75)
    vp_prog = max(0.0, (initial_vp - game.vp_chips)) / initial_vp
    max_city = 0
    for p in game.players:
        filled = sum(
            1 for b in p.city_board
            if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
        )
        max_city = max(max_city, filled)
    city_prog = max_city / 12.0
    initial_col = COLONIST_SUPPLY_SETUP.get(game.num_players, 55)
    col_prog = max(0.0, (initial_col - game.colonists_supply)) / initial_col
    game_progress = min(1.0, max(vp_prog, city_prog, col_prog))

    goods_supply = {GOOD_ENUM_TO_NAME[g]: int(v) for g, v in game.goods_supply.items()}

    trading_house = [GOOD_ENUM_TO_NAME[g] for g in game.trading_house]

    players = [
        _build_player_canonical(p, i)
        for i, p in enumerate(game.players)
    ]

    return {
        "schema_version": CANONICAL_STATE_VERSION,
        "meta": {
            "phase_id": _safe_phase_id(game.current_phase),
            "current_player_idx": int(game.current_player_idx),
            "governor_idx": int(game.governor_idx),
            "round": int(getattr(engine, "_round_count", 0)) + 1,
            "step_count": int(getattr(engine, "_step_count", 0)),
            "num_players": int(game.num_players),
        },
        "global": {
            "vp_supply": int(game.vp_chips),
            "colonist_supply": int(game.colonists_supply),
            "colonist_ship": int(game.colonists_ship),
            "goods_supply": goods_supply,
            "trading_house": trading_house,
            "trading_house_count": len(game.trading_house),
            "cargo_ships": cargo_ships,
            "available_roles": available_roles,
            "role_doubloons": role_doubloons,
            "face_up_plantations": face_up,
            "quarry_supply": int(game.quarry_stack),
            "game_progress": float(game_progress),
        },
        "players": players,
    }
