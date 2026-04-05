import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL")))

from configs.constants import BUILDING_DATA, BuildingType, Phase, TileType


def make_island_slot_id(tile_type_name: str, index: int) -> str:
    return f"island:{tile_type_name}:{index}"


def make_city_slot_id(building_name: str, index: int) -> str:
    return f"city:{building_name}:{index}"


@dataclass
class MayorPlacement:
    slot_id: str
    count: int


def build_slot_catalog(game, player_idx: int) -> List[Dict[str, object]]:
    if game.current_phase != Phase.MAYOR:
        raise ValueError("Mayor phase is not active.")

    player = game.players[player_idx]
    slots: List[Dict[str, object]] = []

    for idx in range(len(player.island_board)):
        tile = player.island_board[idx]
        if tile.tile_type == TileType.EMPTY:
            continue
        slots.append(
            {
                "slot_id": make_island_slot_id(tile.tile_type.name.lower(), idx),
                "engine_slot_idx": idx,
                "capacity": 1,
                "kind": "island",
            }
        )

    for idx in range(len(player.city_board)):
        building = player.city_board[idx]
        if building.building_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
            continue
        slots.append(
            {
                "slot_id": make_city_slot_id(building.building_type.name.lower(), idx),
                "engine_slot_idx": 12 + idx,
                "capacity": BUILDING_DATA[building.building_type][2],
                "kind": "city",
            }
        )

    slots.sort(key=lambda slot: int(slot["engine_slot_idx"]))
    return slots


def validate_distribution_plan(game, player_idx: int, placements: List[MayorPlacement]) -> None:
    if game.current_phase != Phase.MAYOR:
        raise ValueError("Mayor phase is not active.")
    if game.current_player_idx != player_idx:
        raise ValueError("It is not this player's Mayor turn.")

    catalog = build_slot_catalog(game, player_idx)
    catalog_by_id = {str(slot["slot_id"]): slot for slot in catalog}
    seen: set[str] = set()
    total_assigned = 0

    for placement in placements:
        if placement.slot_id not in catalog_by_id:
            raise ValueError(f"Unknown Mayor slot_id: {placement.slot_id}")
        if placement.slot_id in seen:
            raise ValueError(f"Duplicate Mayor slot_id: {placement.slot_id}")
        seen.add(placement.slot_id)

        if placement.count < 0 or placement.count > 3:
            raise ValueError(f"Invalid Mayor count for {placement.slot_id}: {placement.count}")

        capacity = int(catalog_by_id[placement.slot_id]["capacity"])
        if placement.count > capacity:
            raise ValueError(
                f"Mayor count exceeds slot capacity for {placement.slot_id}: "
                f"{placement.count} > {capacity}"
            )

        total_assigned += placement.count

    available = int(getattr(game.players[player_idx], "unplaced_colonists", 0))
    if total_assigned > available:
        raise ValueError(
            f"Mayor distribution exceeds available colonists: {total_assigned} > {available}"
        )


def translate_plan_to_actions(game, player_idx: int, placements: List[MayorPlacement]) -> List[int]:
    validate_distribution_plan(game, player_idx, placements)

    plan_map: Dict[str, int] = {placement.slot_id: placement.count for placement in placements}
    actions: List[int] = []

    for slot in build_slot_catalog(game, player_idx):
        amount = plan_map.get(str(slot["slot_id"]), 0)
        actions.append(69 + amount)

    return actions


def apply_distribution_plan(service, game_id, actor_id: str, placements: List[MayorPlacement]):
    engine = service.active_engines.get(game_id)
    if engine is None:
        raise ValueError(f"Active game engine not found for game {game_id}")

    room = service.db.query(service.game_session_model).filter(service.game_session_model.id == game_id).first()
    if room is None or not room.players:
        raise ValueError("Game room not found")

    current_idx = engine.env.game.current_player_idx
    expected_actor = str(room.players[current_idx])
    if expected_actor != actor_id:
        raise ValueError("Not your turn.")

    actions = translate_plan_to_actions(engine.env.game, current_idx, placements)
    last_result: Optional[Dict[str, object]] = None

    for action in actions:
        game = engine.env.game
        if game.current_phase != Phase.MAYOR or game.current_player_idx != current_idx:
            break
        last_result = service.process_action(game_id, actor_id, action)

    if last_result is None:
        raise ValueError("Mayor distribution produced no actions.")

    return last_result
