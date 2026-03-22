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

if TYPE_CHECKING:
    from env.engine import PuertoRicoGame
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


def _building_name(bt: BuildingType) -> str:
    return bt.name.lower()


# ------------------------------------------------------------------ #
#  Sub-serializers                                                     #
# ------------------------------------------------------------------ #

def _serialize_cargo_ship(ship) -> Dict[str, Any]:
    return {
        "capacity": ship.capacity,
        "good": GOOD_TO_STR.get(ship.good_type) if ship.good_type is not None else None,
        "d_filled": ship.current_load,
        "d_remaining_space": ship.capacity - ship.current_load,
        "d_is_full": ship.is_full,
        "d_is_empty": ship.is_empty,
    }


def _serialize_common_board(game: "PuertoRicoGame") -> Dict[str, Any]:
    # Roles: which player holds each role this round
    role_data: Dict[str, Any] = {}
    for role in game.available_roles + list(game.roles_in_play if hasattr(game, "roles_in_play") else []):
        pass

    all_roles = list(Role)
    # Map role → player name (if taken this round)
    role_taken_by: Dict[Role, Optional[str]] = {r: None for r in all_roles}
    # roles_in_play are roles already picked; the player who picked them is not stored in game
    # directly, but we can infer from each player's active role selection is not stored per-player.
    # We'll leave taken_by as None and populate via session if needed.

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
        roles[ROLE_TO_STR[role]] = {
            "doubloons_on_role": doubloons,
            "taken_by": taken_by,
        }

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

    face_up = [TILE_TO_STR.get(t, "empty") for t in game.face_up_plantations]

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
        available_buildings[_building_name(bt)] = {
            "cost": data[0],
            "max_colonists": data[2],
            "vp": data[1],
            "copies_remaining": count,
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
    corn = sum(1 for t in player.island_board if t.tile_type == TileType.CORN_PLANTATION and t.is_occupied)
    raw_indigo = sum(1 for t in player.island_board if t.tile_type == TileType.INDIGO_PLANTATION and t.is_occupied)
    raw_sugar = sum(1 for t in player.island_board if t.tile_type == TileType.SUGAR_PLANTATION and t.is_occupied)
    raw_tobacco = sum(1 for t in player.island_board if t.tile_type == TileType.TOBACCO_PLANTATION and t.is_occupied)
    raw_coffee = sum(1 for t in player.island_board if t.tile_type == TileType.COFFEE_PLANTATION and t.is_occupied)

    cap_indigo = sum(b.colonists for b in player.city_board if b.building_type in (BuildingType.SMALL_INDIGO_PLANT, BuildingType.INDIGO_PLANT))
    cap_sugar = sum(b.colonists for b in player.city_board if b.building_type in (BuildingType.SMALL_SUGAR_MILL, BuildingType.SUGAR_MILL))
    cap_tobacco = sum(b.colonists for b in player.city_board if b.building_type == BuildingType.TOBACCO_STORAGE)
    cap_coffee = sum(b.colonists for b in player.city_board if b.building_type == BuildingType.COFFEE_ROASTER)

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
) -> Dict[str, Any]:
    # Island
    plantations = [
        {
            "type": TILE_TO_STR.get(t.tile_type, "empty"),
            "colonized": t.is_occupied,
        }
        for t in player.island_board
    ]
    island = {
        "total_spaces": 12,
        "d_used_spaces": len(player.island_board),
        "d_empty_spaces": player.empty_island_spaces,
        "d_active_quarries": sum(
            1 for t in player.island_board
            if t.tile_type == TileType.QUARRY and t.is_occupied
        ),
        "plantations": plantations,
    }

    # City
    buildings_data = []
    for b in player.city_board:
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
            "current_colonists": b.colonists,
            "empty_slots": max(0, max_col - b.colonists),
            "is_active": b.colonists > 0,
            "vp": bdata[1],
        })

    city = {
        "total_spaces": 12,
        "d_used_spaces": len(player.city_board),
        "d_empty_spaces": player.empty_city_spaces,
        "colonists_unplaced": player.unplaced_colonists,
        "d_quarry_discount": sum(
            1 for b in player.city_board
            if b.building_type == BuildingType.CONSTRUCTION_HUT and b.colonists > 0
        ),
        "d_total_empty_colonist_slots": sum(
            max(0, BUILDING_DATA.get(b.building_type, (0, 0, 0))[2] - b.colonists)
            for b in player.city_board
            if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
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
    for i, p in enumerate(game.players):
        name = player_names[i] if i < len(player_names) else f"player_{i}"
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
        scores[name] = {
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
    player_order = [player_names[i] if i < len(player_names) else f"player_{i}" for i in range(len(game.players))]
    winner = max(
        player_order,
        key=lambda n: (scores[n]["total"], game.players[player_order.index(n)].doubloons + sum(game.players[player_order.index(n)].goods.values()))
    )
    return {"scores": scores, "winner": winner, "player_order": player_order}


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
    players: Dict[str, Any] = {}
    for i, p in enumerate(game.players):
        name = session.player_names[i] if i < len(session.player_names) else f"Player {i}"
        players[f"player_{i}"] = _serialize_player(p, game, name, i)

    meta = {
        "round": session.round,
        "num_players": game.num_players,
        "player_order": player_order,
        "governor": governor_key,
        "phase": phase_str,
        "active_role": ROLE_TO_STR.get(game.active_role) if game.active_role is not None else None,
        "active_player": player_key,
        "players_acted_this_phase": [],
        "end_game_triggered": session.game_over,
        "end_game_reason": None,
        "vp_supply_remaining": game.vp_chips,
        "captain_consecutive_passes": len(game._captain_passed_players),
        "bot_thinking": session.bot_thinking,
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

    return {
        "meta": meta,
        "common_board": common_board,
        "players": players,
        "decision": decision,
        "history": session.history,
        "bot_players": bot_players,
    }
