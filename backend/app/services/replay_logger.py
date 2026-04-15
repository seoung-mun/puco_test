from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.services.model_registry import build_replay_parity_snapshot, enrich_actor_snapshot
from app.services.state_serializer import compute_score_breakdown
from app.services.engine_gateway.constants import (
    BUILDING_DATA,
    GOOD_PRICES,
    BuildingType,
    Good,
    Phase,
    Role,
    TileType,
)


LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/logs"))
REPLAY_LOG_DIR = os.path.join(LOG_DIR, "replay")
os.makedirs(REPLAY_LOG_DIR, exist_ok=True)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _phase_name(phase_id: int | None) -> str:
    if phase_id is None:
        return "UNKNOWN"
    try:
        return Phase(int(phase_id)).name
    except (ValueError, TypeError):
        return f"PHASE_{phase_id}"


def _role_name(role_id: int) -> str:
    try:
        role = Role(int(role_id))
    except ValueError:
        return f"Role {role_id}"
    return role.name.replace("_", " ").title()


def _good_name(good_id: int) -> str:
    try:
        return Good(int(good_id)).name.title()
    except ValueError:
        return f"Good {good_id}"


def _tile_name(tile_id: int) -> str:
    try:
        tile = TileType(int(tile_id))
    except ValueError:
        return f"Tile {tile_id}"
    return tile.name.replace("_PLANTATION", "").replace("_", " ").title()


def _building_name(building_id: int) -> str:
    try:
        building = BuildingType(int(building_id))
    except ValueError:
        return f"Building {building_id}"
    return building.name.replace("_", " ").title()


def get_replay_file_path(game_id: UUID | str) -> str:
    return os.path.join(REPLAY_LOG_DIR, f"{game_id}.json")


def summarize_transition_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}

    global_state = state.get("global_state") or {}
    players = state.get("players") or {}
    summary_players: dict[str, Any] = {}
    for player_key, player_state in players.items():
        if not isinstance(player_state, dict):
            continue

        plantations_counter = Counter()
        for tile_id in player_state.get("island_tiles", []):
            if tile_id == TileType.EMPTY:
                continue
            plantations_counter[_tile_name(int(tile_id)).lower().replace(" ", "_")] += 1

        buildings = [
            _building_name(int(building_id)).lower().replace(" ", "_")
            for building_id in player_state.get("city_buildings", [])
            if int(building_id) not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
        ]

        goods_values = list(player_state.get("goods", []))
        goods = {
            _good_name(idx).lower(): count
            for idx, count in enumerate(goods_values)
            if count
        }

        summary_players[player_key] = {
            "doubloons": player_state.get("doubloons", 0),
            "vp": player_state.get("vp_chips", 0),
            "goods": goods,
            "plantations": dict(plantations_counter),
            "buildings": buildings,
            "unplaced_colonists": player_state.get("unplaced_colonists", 0),
        }

    return {
        "phase": _phase_name(global_state.get("current_phase")),
        "phase_id": global_state.get("current_phase"),
        "current_player": global_state.get("current_player"),
        "governor": global_state.get("governor_idx"),
        "vp_supply": global_state.get("vp_chips"),
        "colonist_supply": global_state.get("colonists_supply"),
        "colonist_ship": global_state.get("colonists_ship"),
        "players": summary_players,
    }


def _describe_delta(before_value: int | float, after_value: int | float, label: str) -> str | None:
    delta = after_value - before_value
    if delta == 0:
        return None
    sign = "+" if delta > 0 else ""
    return f"{label} {sign}{delta}"


def _build_commentary(
    *,
    player_key: str | None,
    state_before: dict[str, Any] | None,
    state_after: dict[str, Any] | None,
    reward: float,
    done: bool,
) -> str:
    before_summary = summarize_transition_state(state_before)
    after_summary = summarize_transition_state(state_after)
    notes: list[str] = []

    if player_key:
        before_player = (before_summary.get("players") or {}).get(player_key) or {}
        after_player = (after_summary.get("players") or {}).get(player_key) or {}

        for field, label in (
            ("doubloons", "Doubloons"),
            ("vp", "VP"),
            ("unplaced_colonists", "Unplaced colonists"),
        ):
            before_value = before_player.get(field, 0)
            after_value = after_player.get(field, 0)
            delta_note = _describe_delta(before_value, after_value, label)
            if delta_note:
                notes.append(delta_note)

        before_goods = before_player.get("goods") or {}
        after_goods = after_player.get("goods") or {}
        for good_name in sorted(set(before_goods) | set(after_goods)):
            before_count = before_goods.get(good_name, 0)
            after_count = after_goods.get(good_name, 0)
            delta_note = _describe_delta(before_count, after_count, good_name.title())
            if delta_note:
                notes.append(delta_note)

        before_buildings = len(before_player.get("buildings") or [])
        after_buildings = len(after_player.get("buildings") or [])
        delta_note = _describe_delta(before_buildings, after_buildings, "Buildings")
        if delta_note:
            notes.append(delta_note)

    before_phase = before_summary.get("phase")
    after_phase = after_summary.get("phase")
    if before_phase and after_phase and before_phase != after_phase:
        notes.append(f"Phase {before_phase} -> {after_phase}")

    before_player_idx = before_summary.get("current_player")
    after_player_idx = after_summary.get("current_player")
    if (
        before_player_idx is not None
        and after_player_idx is not None
        and before_player_idx != after_player_idx
    ):
        notes.append(f"Next player P{after_player_idx}")

    if reward:
        notes.append(f"Reward {reward:+.2f}")
    if done:
        notes.append("Game finished")

    return " | ".join(notes)


def describe_action(action_id: int, *, state_before: dict[str, Any] | None = None) -> str:
    if 0 <= action_id <= 7:
        return f"Select Role: {_role_name(action_id)}"

    if 8 <= action_id <= 13:
        face_up = ((state_before or {}).get("global_state") or {}).get("face_up_plantations") or []
        index = action_id - 8
        if index < len(face_up):
            return f"Settler: Take {_tile_name(int(face_up[index]))} Plantation"
        return f"Settler: Take Face-up Plantation #{index}"

    if action_id == 14:
        return "Settler: Take Quarry"
    if action_id == 15:
        return "Pass"

    if 16 <= action_id <= 38:
        building = BuildingType(action_id - 16)
        cost, vp, *_rest = BUILDING_DATA[building]
        return f"Builder: Build {_building_name(building.value)} (cost {cost}, VP {vp})"

    if 39 <= action_id <= 43:
        good = Good(action_id - 39)
        return f"Trader: Sell {good.name.title()} (base price {GOOD_PRICES[good]})"

    if 44 <= action_id <= 58:
        index = action_id - 44
        ship_index = index // 5
        good = Good(index % 5)
        return f"Captain: Load {good.name.title()} onto Ship {ship_index + 1}"

    if 59 <= action_id <= 63:
        return f"Captain: Load {_good_name(action_id - 59)} via Wharf"

    if 64 <= action_id <= 68:
        return f"Captain Store: Keep {_good_name(action_id - 64)} via Windrose"

    if 69 <= action_id <= 71:
        strategy_name = {
            69: "Captain Focus",
            70: "Trade / Factory Focus",
            71: "Building Focus",
        }[action_id]
        return f"Mayor: (legacy) Strategy {strategy_name}"

    if 120 <= action_id <= 131:
        return f"Mayor: Place colonist on Island slot {action_id - 120}"

    if 140 <= action_id <= 151:
        return f"Mayor: Place colonist on City slot {action_id - 140}"

    if 93 <= action_id <= 97:
        return f"Craftsman: Choose Privilege {_good_name(action_id - 93)}"

    if action_id == 105:
        return "Settler: Use Hacienda"

    if 106 <= action_id <= 110:
        return f"Captain Store: Keep {_good_name(action_id - 106)} via Warehouse"

    return f"Action {action_id}"


def build_replay_entry(
    *,
    actor_id: str,
    actor_name: str,
    player_index: int | None,
    action: int,
    reward: float,
    done: bool,
    info: dict[str, Any],
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    action_mask_before: list[int] | None = None,
    model_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    phase_id = ((state_before or {}).get("global_state") or {}).get("current_phase")
    player_key = f"player_{player_index}" if player_index is not None else None
    entry = {
        "step": info.get("step"),
        "round": info.get("round"),
        "player": player_index,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "phase": _phase_name(phase_id),
        "phase_id": phase_id,
        "action_id": action,
        "action": describe_action(action, state_before=state_before),
        "value_estimate": None,
        "top_actions": [],
        "reward": reward,
        "done": done,
        "valid_action_count": sum(1 for flag in (action_mask_before or []) if flag),
        "commentary": _build_commentary(
            player_key=player_key,
            state_before=state_before,
            state_after=state_after,
            reward=reward,
            done=done,
        ),
        "state_summary_before": summarize_transition_state(state_before),
        "state_summary_after": summarize_transition_state(state_after),
    }
    if model_info is not None:
        entry["model_info"] = enrich_actor_snapshot(model_info)
    if 0 <= action <= 7:
        entry["role_selected"] = _role_name(action)
    return entry


def build_final_scores_payload(
    *,
    game,
    player_names: list[str],
    actor_ids: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    breakdown = compute_score_breakdown(game, player_names)
    final_scores: list[dict[str, Any]] = []
    for idx, player_ref in enumerate(breakdown["player_order"]):
        player = game.players[idx]
        tiebreaker = int(player.doubloons + sum(player.goods.values()))
        final_scores.append(
            {
                "player": idx,
                "actor_id": actor_ids[idx] if idx < len(actor_ids) else f"player_{idx}",
                "display_name": breakdown["display_names"].get(player_ref, player_ref),
                "vp": breakdown["scores"][player_ref]["total"],
                "tiebreaker": tiebreaker,
                "winner": breakdown["winner"] == player_ref,
                "breakdown": breakdown["scores"][player_ref],
            }
        )
    return final_scores, breakdown


def _base_payload(
    *,
    game_id: UUID | str,
    title: str | None,
    status: str | None,
    host_id: str | None,
    players: list[dict[str, Any]],
    model_versions: dict[str, Any] | None,
    initial_state_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    now = _iso_now()
    return {
        "format": "backend-replay.v2",
        "game_id": str(game_id),
        "title": title,
        "status": status,
        "host_id": host_id,
        "num_players": len(players),
        "players": players,
        "model_versions": model_versions or {},
        "parity": build_replay_parity_snapshot(model_versions),
        "created_at": now,
        "updated_at": now,
        "initial_state_summary": initial_state_summary or {},
        "total_steps": 0,
        "final_scores": [],
        "result_summary": None,
        "entries": [],
    }


def _load_payload(path: str) -> dict[str, Any] | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_payload(path: str, payload: dict[str, Any]) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp_path, path)


class ReplayLogger:
    @staticmethod
    def initialize_game(
        *,
        game_id: UUID | str,
        title: str | None,
        status: str | None,
        host_id: str | None,
        players: list[dict[str, Any]],
        model_versions: dict[str, Any] | None,
        initial_state_summary: dict[str, Any] | None,
    ) -> str:
        path = get_replay_file_path(game_id)
        payload = _load_payload(path) or _base_payload(
            game_id=game_id,
            title=title,
            status=status,
            host_id=host_id,
            players=players,
            model_versions=model_versions,
            initial_state_summary=initial_state_summary,
        )
        payload["title"] = title
        payload["status"] = status
        payload["host_id"] = host_id
        payload["players"] = players
        payload["num_players"] = len(players)
        payload["model_versions"] = model_versions or {}
        payload["parity"] = build_replay_parity_snapshot(model_versions)
        payload["initial_state_summary"] = initial_state_summary or payload.get("initial_state_summary") or {}
        payload["updated_at"] = _iso_now()
        _write_payload(path, payload)
        return path

    @staticmethod
    def append_entry(
        *,
        game_id: UUID | str,
        title: str | None,
        status: str | None,
        host_id: str | None,
        players: list[dict[str, Any]],
        model_versions: dict[str, Any] | None,
        entry: dict[str, Any],
        rich_state: dict[str, Any] | None = None,
        final_scores: list[dict[str, Any]] | None = None,
        result_summary: dict[str, Any] | None = None,
    ) -> str:
        path = get_replay_file_path(game_id)
        payload = _load_payload(path) or _base_payload(
            game_id=game_id,
            title=title,
            status=status,
            host_id=host_id,
            players=players,
            model_versions=model_versions,
            initial_state_summary=None,
        )
        payload["title"] = title
        payload["status"] = status
        payload["host_id"] = host_id
        payload["players"] = players
        payload["num_players"] = len(players)
        payload["model_versions"] = model_versions or {}
        payload["parity"] = build_replay_parity_snapshot(model_versions)
        entry_to_append = dict(entry)
        entry_to_append["rich_state"] = rich_state if rich_state is not None else None
        payload.setdefault("entries", []).append(entry_to_append)
        payload["total_steps"] = len(payload["entries"])
        payload["updated_at"] = _iso_now()
        if final_scores is not None:
            payload["final_scores"] = final_scores
        if result_summary is not None:
            payload["result_summary"] = result_summary
        _write_payload(path, payload)
        return path
