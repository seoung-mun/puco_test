"""
State Serializer — converts PuertoRicoGame (engine.env.game) into the
rich GameState JSON format expected by the frontend.
"""
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL")))

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from configs.constants import (
    Phase, Role, Good, TileType, BuildingType, BUILDING_DATA
)
import app.services.action_translator as _tr
from app.services.mayor_orchestrator import make_city_slot_id, make_island_slot_id, slot_tile_name

if TYPE_CHECKING:
    from env.engine import PuertoRicoGame
    from app.engine_wrapper.wrapper import EngineWrapper
    from app.services.session_manager import SessionManager

# ------------------------------------------------------------------ #
#  Name mappings                                                       #
# ------------------------------------------------------------------ #

PHASE_TO_STR: Dict[Optional[Phase], str] = {
    None: "role_selection",
    Phase.END_ROUND: "role_selection",
    Phase.SETTLER: "settler_action",
    Phase.MAYOR: "mayor_action",
    Phase.BUILDER: "builder_action",
    Phase.CRAFTSMAN: "craftsman_action",
    Phase.TRADER: "trader_action",
    Phase.CAPTAIN: "captain_action",
    Phase.CAPTAIN_STORE: "captain_discard",
    Phase.PROSPECTOR: "role_selection",
}

ROLE_TO_STR = {r: r.name.lower() for r in Role}
GOOD_TO_STR = {g: g.name.lower() for g in Good}
TILE_TO_STR = {
    TileType.COFFEE_PLANTATION: "coffee",
    TileType.TOBACCO_PLANTATION: "tobacco",
    TileType.CORN_PLANTATION: "corn",
    TileType.SUGAR_PLANTATION: "sugar",
    TileType.INDIGO_PLANTATION: "indigo",
    TileType.QUARRY: "quarry",
    TileType.EMPTY: "empty",
}


def compute_display_order(governor_idx: int, num_players: int) -> Dict[int, int]:
    """Return {internal_player_idx: display_number} where Governor=1."""
    return {
        (governor_idx + offset) % num_players: offset + 1
        for offset in range(num_players)
    }


def _building_name(bt: BuildingType) -> str:
    return bt.name.lower()


def _safe_get(obj: Any, *names: str, default: Any = None) -> Any:
    """Return the first existing attribute/key from a drift-prone engine object."""
    for name in names:
        if isinstance(obj, dict) and name in obj:
            value = obj[name]
            return default if value is None else value
        if hasattr(obj, name):
            value = getattr(obj, name)
            return default if value is None else value
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _settler_has_regular_pick(game: "PuertoRicoGame", player_idx: int) -> bool:
    """Backend-side guard for Settler pass handling without mutating engine code."""
    if game.current_phase != Phase.SETTLER:
        return False
    if player_idx < 0 or player_idx >= len(game.players):
        return False

    player = game.players[player_idx]
    if player.empty_island_spaces <= 0:
        return False
    if len(game.face_up_plantations) > 0:
        return True

    can_quarry = (
        player_idx == game.active_role_player_idx()
        or player.is_building_occupied(BuildingType.CONSTRUCTION_HUT)
    )
    return can_quarry and game.quarry_stack > 0


def apply_backend_action_mask_guards(
    game: "PuertoRicoGame",
    action_mask: List[int],
) -> List[int]:
    """
    Normalize engine masks at the backend boundary so API/WS consumers see the
    rules we enforce server-side, even if the engine itself is more permissive.
    """
    guarded_mask = list(action_mask)
    if len(guarded_mask) <= 15:
        return guarded_mask

    if _settler_has_regular_pick(game, game.current_player_idx):
        guarded_mask[15] = 0
    return guarded_mask


# ------------------------------------------------------------------ #
#  Sub-serializers                                                     #
# ------------------------------------------------------------------ #

def _serialize_cargo_ship(ship) -> Dict[str, Any]:
    capacity = _safe_int(_safe_get(ship, "capacity", default=0))
    current_load = _safe_int(_safe_get(ship, "current_load", "filled", default=0))
    is_full = bool(_safe_get(ship, "is_full", default=current_load >= capacity if capacity else False))
    is_empty = bool(_safe_get(ship, "is_empty", default=current_load == 0))
    return {
        "capacity": capacity,
        "good": GOOD_TO_STR.get(_safe_get(ship, "good_type", "good")) if _safe_get(ship, "good_type", "good") is not None else None,
        "d_filled": current_load,
        "d_remaining_space": max(0, capacity - current_load),
        "d_is_full": is_full,
        "d_is_empty": is_empty,
    }


def _serialize_common_board(game: "PuertoRicoGame") -> Dict[str, Any]:
    all_roles = list(game.available_roles) + list(game.roles_in_play)

    roles: Dict[str, Any] = {}
    for role in all_roles:
        doubloons = game.role_doubloons.get(role, 0)
        # Role is "available" (not taken) if it's in game.available_roles
        taken_by = None
        if role in game.roles_in_play:
            if role == game.active_role and hasattr(game, 'active_role_player'):
                taken_by = f"player_{game.active_role_player}"
            else:
                taken_by = "taken"
        role_entry: Dict[str, Any] = {
            "doubloons_on_role": doubloons,
            "taken_by": taken_by,
        }
        if taken_by is None:
            try:
                role_entry["action_index"] = _tr.select_role(ROLE_TO_STR[role])
            except (ValueError, KeyError):
                pass
        roles[ROLE_TO_STR[role]] = role_entry

    trading_house_goods = [GOOD_TO_STR[g] for g in game.trading_house]

    # Plantation draw pile counts (remaining in stack)
    from collections import Counter
    draw_counts = Counter(game.plantation_stack)
    draw_pile = {
        "corn": draw_counts.get(TileType.CORN_PLANTATION, 0),
        "indigo": draw_counts.get(TileType.INDIGO_PLANTATION, 0),
        "sugar": draw_counts.get(TileType.SUGAR_PLANTATION, 0),
        "tobacco": draw_counts.get(TileType.TOBACCO_PLANTATION, 0),
        "coffee": draw_counts.get(TileType.COFFEE_PLANTATION, 0),
    }

    face_up = [
        {
            "type": TILE_TO_STR.get(t, "empty"),
            "action_index": 14 if TILE_TO_STR.get(t, "empty") == "quarry" else (8 + i),
        }
        for i, t in enumerate(game.face_up_plantations)
    ]

    # Available buildings
    available_buildings: Dict[str, Any] = {}
    for bt, count in game.building_supply.items():
        if bt in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
            continue
        if count <= 0:
            continue
        data = BUILDING_DATA.get(bt)
        if data is None:
            continue
        bname = _building_name(bt)
        try:
            b_action_idx = _tr.build(bname)
        except (ValueError, KeyError):
            b_action_idx = None
        available_buildings[bname] = {
            "cost": data[0],
            "max_colonists": data[2],
            "vp": data[1],
            "copies_remaining": count,
            "action_index": b_action_idx,
        }

    goods_supply = {GOOD_TO_STR[g]: v for g, v in game.goods_supply.items()}

    return {
        "roles": roles,
        "colonists": {
            "ship": game.colonists_ship,
            "supply": game.colonists_supply,
        },
        "trading_house": {
            "goods": trading_house_goods,
            "d_spaces_used": len(game.trading_house),
            "d_spaces_remaining": 4 - len(game.trading_house),
            "d_is_full": len(game.trading_house) >= 4,
        },
        "cargo_ships": [_serialize_cargo_ship(s) for s in game.cargo_ships],
        "available_plantations": {
            "face_up": face_up,
            "draw_pile": draw_pile,
        },
        "available_buildings": available_buildings,
        "quarry_supply_remaining": game.quarry_stack,
        "goods_supply": goods_supply,
    }


def _compute_production(player, game: "PuertoRicoGame") -> Dict[str, Any]:
    """Compute production potential for a player (same logic as engine craftsman phase)."""
    corn = sum(1 for t in player.island_board if _safe_get(t, "tile_type") == TileType.CORN_PLANTATION and _safe_get(t, "is_occupied", "occupied", default=False))
    raw_indigo = sum(1 for t in player.island_board if _safe_get(t, "tile_type") == TileType.INDIGO_PLANTATION and _safe_get(t, "is_occupied", "occupied", default=False))
    raw_sugar = sum(1 for t in player.island_board if _safe_get(t, "tile_type") == TileType.SUGAR_PLANTATION and _safe_get(t, "is_occupied", "occupied", default=False))
    raw_tobacco = sum(1 for t in player.island_board if _safe_get(t, "tile_type") == TileType.TOBACCO_PLANTATION and _safe_get(t, "is_occupied", "occupied", default=False))
    raw_coffee = sum(1 for t in player.island_board if _safe_get(t, "tile_type") == TileType.COFFEE_PLANTATION and _safe_get(t, "is_occupied", "occupied", default=False))

    cap_indigo = sum(_safe_int(_safe_get(b, "colonists", "worker_count", default=0)) for b in player.city_board if _safe_get(b, "building_type") in (BuildingType.SMALL_INDIGO_PLANT, BuildingType.INDIGO_PLANT))
    cap_sugar = sum(_safe_int(_safe_get(b, "colonists", "worker_count", default=0)) for b in player.city_board if _safe_get(b, "building_type") in (BuildingType.SMALL_SUGAR_MILL, BuildingType.SUGAR_MILL))
    cap_tobacco = sum(_safe_int(_safe_get(b, "colonists", "worker_count", default=0)) for b in player.city_board if _safe_get(b, "building_type") == BuildingType.TOBACCO_STORAGE)
    cap_coffee = sum(_safe_int(_safe_get(b, "colonists", "worker_count", default=0)) for b in player.city_board if _safe_get(b, "building_type") == BuildingType.COFFEE_ROASTER)

    amounts = {
        "corn": corn,
        "indigo": min(raw_indigo, cap_indigo),
        "sugar": min(raw_sugar, cap_sugar),
        "tobacco": min(raw_tobacco, cap_tobacco),
        "coffee": min(raw_coffee, cap_coffee),
    }
    total = sum(amounts.values())
    return {
        good: {"can_produce": amounts[good] > 0, "amount": amounts[good]}
        for good in ["corn", "indigo", "sugar", "tobacco", "coffee"]
    } | {"d_total": total}


def _serialize_player(
    player,
    game: "PuertoRicoGame",
    display_name: str,
    player_idx: int,
    display_number: int = 0,
) -> Dict[str, Any]:
    # Island
    plantations = [
        {
            "type": TILE_TO_STR.get(_safe_get(t, "tile_type"), "empty"),
            "colonized": bool(_safe_get(t, "is_occupied", "occupied", default=False)),
            "slot_id": make_island_slot_id(slot_tile_name(_safe_get(t, "tile_type")), idx),
            "capacity": 1,
        }
        for idx, t in enumerate(player.island_board)
    ]
    island = {
        "total_spaces": 12,
        "d_used_spaces": len(player.island_board),
        "d_empty_spaces": player.empty_island_spaces,
        "d_active_quarries": sum(
            1 for t in player.island_board
            if _safe_get(t, "tile_type") == TileType.QUARRY and _safe_get(t, "is_occupied", "occupied", default=False)
        ),
        "plantations": plantations,
    }

    # City
    buildings_data = []
    for idx, b in enumerate(player.city_board):
        bt = b.building_type
        if bt in (BuildingType.OCCUPIED_SPACE,):
            continue
        bdata = BUILDING_DATA.get(bt)
        if bdata is None:
            continue
        max_col = bdata[2]
        buildings_data.append({
            "name": _building_name(bt),
            "max_colonists": max_col,
            "current_colonists": _safe_int(_safe_get(b, "colonists", "worker_count", default=0)),
            "empty_slots": max(0, max_col - _safe_int(_safe_get(b, "colonists", "worker_count", default=0))),
            "is_active": _safe_int(_safe_get(b, "colonists", "worker_count", default=0)) > 0,
            "vp": bdata[1],
            "slot_id": make_city_slot_id(_building_name(bt), idx),
            "capacity": max_col,
        })

    city = {
        "total_spaces": 12,
        "d_used_spaces": len(player.city_board),
        "d_empty_spaces": player.empty_city_spaces,
        "colonists_unplaced": _safe_int(_safe_get(player, "unplaced_colonists", "colonists", default=0)),
        "d_quarry_discount": sum(
            1 for b in player.city_board
            if _safe_get(b, "building_type") == BuildingType.CONSTRUCTION_HUT and _safe_int(_safe_get(b, "colonists", "worker_count", default=0)) > 0
        ),
        "d_total_empty_colonist_slots": sum(
            max(0, BUILDING_DATA.get(_safe_get(b, "building_type"), (0, 0, 0))[2] - _safe_int(_safe_get(b, "colonists", "worker_count", default=0)))
            for b in player.city_board
            if _safe_get(b, "building_type") not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
        ),
        "buildings": buildings_data,
    }

    # Goods
    goods = {GOOD_TO_STR[g]: v for g, v in player.goods.items()}
    goods["d_total"] = sum(player.goods.values())

    # Production
    production = _compute_production(player, game)

    # Warehouse
    has_small = player.has_building(BuildingType.SMALL_WAREHOUSE) and player.is_building_occupied(BuildingType.SMALL_WAREHOUSE)
    has_large = player.has_building(BuildingType.LARGE_WAREHOUSE) and player.is_building_occupied(BuildingType.LARGE_WAREHOUSE)
    storable = 1 + (1 if has_small else 0) + (2 if has_large else 0)
    # Protected goods during captain store phase
    storage = game._storage_assignments.get(player_idx, {})
    protected: List[str] = []
    if storage.get("windrose"):
        protected.append(GOOD_TO_STR[storage["windrose"]])
    for g in storage.get("warehouses", []):
        protected.append(GOOD_TO_STR[g])

    warehouse = {
        "has_small_warehouse": has_small,
        "has_large_warehouse": has_large,
        "d_goods_storable": storable,
        "protected_goods": protected,
    }

    return {
        "display_name": display_name,
        "display_number": display_number,
        "is_governor": player_idx == game.governor_idx,
        "doubloons": player.doubloons,
        "vp_chips": player.vp_chips,
        "goods": goods,
        "island": island,
        "city": city,
        "production": production,
        "warehouse": warehouse,
        "captain_first_load_done": False,
        "wharf_used_this_phase": game._wharf_used.get(player_idx, False),
        "hacienda_used_this_phase": game._hacienda_used,
    }


# ------------------------------------------------------------------ #
#  Final score breakdown                                               #
# ------------------------------------------------------------------ #

def compute_score_breakdown(game: "PuertoRicoGame", player_names: List[str]) -> Dict[str, Any]:
    scores = {}
    display_names = {}
    player_order = []
    for i, p in enumerate(game.players):
        player_ref = f"player_{i}"
        display_names[player_ref] = player_names[i] if i < len(player_names) else player_ref
        player_order.append(player_ref)
        vp_chips = p.vp_chips

        building_vp = sum(BUILDING_DATA[b.building_type][1] for b in p.city_board if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE))

        guildhall_bonus = 0
        residence_bonus = 0
        fortress_bonus = 0
        customs_house_bonus = 0
        city_hall_bonus = 0

        for b in p.city_board:
            bdata = BUILDING_DATA.get(b.building_type)
            if bdata and bdata[4] and b.colonists > 0:  # large + occupied
                bt = b.building_type
                if bt == BuildingType.GUILDHALL:
                    for ob in p.city_board:
                        if BUILDING_DATA.get(ob.building_type, (0,)*6)[5] is not None:
                            guildhall_bonus += 1 if ob.building_type in (BuildingType.SMALL_INDIGO_PLANT, BuildingType.SMALL_SUGAR_MILL) else 2
                elif bt == BuildingType.RESIDENCE:
                    fi = len(p.island_board)
                    residence_bonus = 4 if fi <= 9 else (5 if fi == 10 else (6 if fi == 11 else 7))
                elif bt == BuildingType.FORTRESS:
                    fortress_bonus = p.total_colonists_owned // 3
                elif bt == BuildingType.CUSTOMS_HOUSE:
                    customs_house_bonus = p.vp_chips // 4
                elif bt == BuildingType.CITY_HALL:
                    city_hall_bonus = sum(
                        1 for v in p.city_board
                        if v.building_type != BuildingType.OCCUPIED_SPACE
                        and BUILDING_DATA.get(v.building_type, (0,)*6)[5] is None
                    )

        total = vp_chips + building_vp + guildhall_bonus + residence_bonus + fortress_bonus + customs_house_bonus + city_hall_bonus
        scores[player_ref] = {
            "vp_chips": vp_chips,
            "building_vp": building_vp,
            "guild_hall_bonus": guildhall_bonus,
            "residence_bonus": residence_bonus,
            "fortress_bonus": fortress_bonus,
            "customs_house_bonus": customs_house_bonus,
            "city_hall_bonus": city_hall_bonus,
            "total": total,
        }

    # Determine winner (highest total, tie-break by doubloons + goods)
    winner_idx = max(
        range(len(game.players)),
        key=lambda idx: (
            scores[f"player_{idx}"]["total"],
            game.players[idx].doubloons + sum(game.players[idx].goods.values()),
        ),
    )
    winner = f"player_{winner_idx}"
    return {
        "scores": scores,
        "winner": winner,
        "player_order": player_order,
        "display_names": display_names,
    }


# ------------------------------------------------------------------ #
#  Main entry point                                                    #
# ------------------------------------------------------------------ #

def serialize_game_state(session: "SessionManager") -> Dict[str, Any]:
    """Convert session + engine state into the full GameState dict."""
    game = session.game.env.game

    phase_str = "game_over" if session.game_over else PHASE_TO_STR.get(game.current_phase, "role_selection")

    player_key = f"player_{game.current_player_idx}"
    governor_key = f"player_{game.governor_idx}"
    player_order = [f"player_{i}" for i in range(game.num_players)]

    # Players dict
    display_order = compute_display_order(game.governor_idx, game.num_players)
    players: Dict[str, Any] = {}
    for i, p in enumerate(game.players):
        name = session.player_names[i] if i < len(session.player_names) else f"Player {i}"
        players[f"player_{i}"] = _serialize_player(p, game, name, i, display_order[i])

    from configs.constants import Phase as _Phase
    _in_mayor = game.current_phase == _Phase.MAYOR
    mayor_slot_idx = game.mayor_placement_idx if _in_mayor else None
    # True when action 69 (place 0 / skip) is currently valid
    if _in_mayor and not session.game_over:
        _mask = session.game.get_action_mask()
        mayor_can_skip = bool(_mask[69]) if len(_mask) > 69 else False
    else:
        mayor_can_skip = False

    meta = {
        "game_id": session.session_id,
        "round": session.game._round_count + 1,
        "step_count": getattr(session.game, "_step_count", 0),
        "num_players": game.num_players,
        "player_order": player_order,
        "governor": governor_key,
        "phase": phase_str,
        "phase_id": _safe_int(game.current_phase, default=8),
        "active_role": ROLE_TO_STR.get(game.active_role) if game.active_role is not None else None,
        "active_player": player_key,
        "players_acted_this_phase": [],
        "end_game_triggered": session.game_over,
        "end_game_reason": None,
        "vp_supply_remaining": game.vp_chips,
        "captain_consecutive_passes": len(game._captain_passed_players),
        "bot_thinking": session.bot_thinking,
        "mayor_slot_idx": mayor_slot_idx,  # 0-11=island slot, 12-23=city slot(idx-12), null if not mayor phase
        "mayor_can_skip": mayor_can_skip,  # True if skip (action 69) is currently valid
        "pass_action_index": 15,
        "hacienda_action_index": 105,
    }

    decision = {
        "type": phase_str,
        "player": player_key,
        "note": "",
    }

    common_board = _serialize_common_board(game)

    bot_players = {
        f"player_{idx}": bot_type
        for idx, bot_type in session.bot_players.items()
    }
    result_summary = compute_score_breakdown(game, session.player_names) if session.game_over else None

    return {
        "meta": meta,
        "common_board": common_board,
        "players": players,
        "decision": decision,
        "history": session.history,
        "bot_players": bot_players,
        "result_summary": result_summary,
    }


def serialize_game_state_from_engine(
    engine: "EngineWrapper",
    player_names: List[str],
    game_id: str = "",
    bot_players: Optional[Dict[int, str]] = None,
    history: Optional[List] = None,
) -> Dict[str, Any]:
    """
    EngineWrapper에서 직접 rich GameState JSON을 생성한다.
    SessionManager 없이 channel WebSocket / 테스트에서 사용한다.
    """
    game = engine.env.game
    if bot_players is None:
        bot_players = {}
    if history is None:
        history = []

    # game_over: any agent terminated or truncated
    game_over = any(engine.env.terminations.values()) or any(engine.env.truncations.values())

    phase_str = "game_over" if game_over else PHASE_TO_STR.get(game.current_phase, "role_selection")

    player_key = f"player_{game.current_player_idx}"
    governor_key = f"player_{game.governor_idx}"
    player_order = [f"player_{i}" for i in range(game.num_players)]

    display_order = compute_display_order(game.governor_idx, game.num_players)
    players: Dict[str, Any] = {}
    for i, p in enumerate(game.players):
        name = player_names[i] if i < len(player_names) else f"Player {i}"
        players[f"player_{i}"] = _serialize_player(p, game, name, i, display_order[i])

    from configs.constants import Phase as _Phase
    _in_mayor = game.current_phase == _Phase.MAYOR
    mayor_slot_idx = game.mayor_placement_idx if _in_mayor else None
    action_mask = apply_backend_action_mask_guards(game, engine.get_action_mask())
    if _in_mayor and not game_over:
        mayor_can_skip = bool(action_mask[69]) if len(action_mask) > 69 else False
    else:
        mayor_can_skip = False

    meta = {
        "game_id": game_id,
        "round": engine._round_count + 1,
        "step_count": engine._step_count,
        "num_players": game.num_players,
        "player_order": player_order,
        "governor": governor_key,
        "phase": phase_str,
        "phase_id": _safe_int(game.current_phase, default=8),
        "active_role": ROLE_TO_STR.get(game.active_role) if game.active_role is not None else None,
        "active_player": player_key,
        "players_acted_this_phase": [],
        "end_game_triggered": game_over,
        "end_game_reason": None,
        "vp_supply_remaining": game.vp_chips,
        "captain_consecutive_passes": len(game._captain_passed_players),
        "bot_thinking": False,
        "mayor_slot_idx": mayor_slot_idx,
        "mayor_can_skip": mayor_can_skip,
        "pass_action_index": 15,
        "hacienda_action_index": 105,
    }

    decision = {
        "type": phase_str,
        "player": player_key,
        "note": "",
    }

    common_board = _serialize_common_board(game)

    bot_players_out = {
        f"player_{idx}": bot_type
        for idx, bot_type in bot_players.items()
    }
    result_summary = compute_score_breakdown(game, player_names) if game_over else None

    return {
        "meta": meta,
        "common_board": common_board,
        "players": players,
        "decision": decision,
        "history": history,
        "bot_players": bot_players_out,
        "result_summary": result_summary,
        "action_mask": action_mask,
    }


# ------------------------------------------------------------------ #
#  Compact summary for DB logging (Adminer-friendly)                  #
# ------------------------------------------------------------------ #

def serialize_compact_summary(engine: "EngineWrapper") -> Dict[str, Any]:
    """
    EngineWrapper에서 핵심 게임 지표만 추출하여 Adminer에서 읽기 쉬운
    compact JSON을 반환한다. GameLog.state_summary 컬럼에 저장된다.
    """
    game = engine.env.game

    phase_name = PHASE_TO_STR.get(game.current_phase, "unknown")
    active_role_name = ROLE_TO_STR.get(game.active_role) if game.active_role else None

    players_summary = {}
    for i, p in enumerate(game.players):
        goods = {GOOD_TO_STR[g]: v for g, v in p.goods.items() if v > 0}
        buildings = [
            _building_name(b.building_type)
            for b in p.city_board
            if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
        ]
        plantations: dict[str, int] = {}
        for t in p.island_board:
            tname = TILE_TO_STR.get(t.tile_type, "empty")
            if tname == "empty":
                continue
            plantations[tname] = plantations.get(tname, 0) + 1

        players_summary[f"p{i}"] = {
            "doubloons": p.doubloons,
            "vp": p.vp_chips,
            "goods": goods,
            "buildings": buildings,
            "plantations": plantations,
            "colonists": p.total_colonists_owned,
            "empty_city": p.empty_city_spaces,
        }

    return {
        "phase": phase_name,
        "role": active_role_name,
        "current_player": game.current_player_idx,
        "governor": game.governor_idx,
        "vp_supply": game.vp_chips,
        "colonist_supply": game.colonists_supply,
        "colonist_ship": game.colonists_ship,
        "players": players_summary,
    }
