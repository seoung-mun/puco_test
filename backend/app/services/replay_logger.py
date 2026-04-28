from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Replay
from app.services.contracts import (
    MODEL_OBSERVATION_STATE_KIND,
    REPLAY_SUMMARY_SCHEMA_VERSION,
    REPLAY_SUMMARY_STATE_KIND,
    extract_state_kind,
    with_state_contract,
)
from app.services.model_registry import build_replay_parity_snapshot, enrich_actor_snapshot
from app.services.log_paths import ensure_log_dir, resolve_log_dir
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

LOG_DIR = resolve_log_dir()
REPLAY_LOG_DIR = os.path.join(LOG_DIR, "replay")


def _replay_log_dir() -> str:
    if replay_storage_backend() == "file":
        os.makedirs(REPLAY_LOG_DIR, exist_ok=True)
        return REPLAY_LOG_DIR
    return REPLAY_LOG_DIR


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
    return os.path.join(_replay_log_dir(), f"{game_id}.json")


def replay_storage_backend() -> str:
    configured = os.getenv("REPLAY_STORAGE_BACKEND", "").strip().lower()
    if configured in {"db", "file"}:
        return configured
    return "file"


def _db_game_id(game_id: UUID | str) -> UUID:
    if isinstance(game_id, UUID):
        return game_id
    return UUID(str(game_id))


def _unwrap_singleton(value: Any) -> Any:
    while isinstance(value, list) and len(value) == 1:
        value = value[0]
    return value


def _as_int(value: Any, default: int | None = 0) -> int | None:
    value = _unwrap_singleton(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return value
    return [value]


def _normalize_numeric_list(value: Any) -> list[int]:
    return [_as_int(item, 0) or 0 for item in _as_list(value)]


def summarize_transition_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return with_state_contract(
            {"players": {}},
            schema_version=REPLAY_SUMMARY_SCHEMA_VERSION,
            state_kind=REPLAY_SUMMARY_STATE_KIND,
            producer="replay-logger",
            source_state_kind="unknown",
        )

    if state.get("state_kind") == REPLAY_SUMMARY_STATE_KIND:
        return with_state_contract(
            state,
            schema_version=REPLAY_SUMMARY_SCHEMA_VERSION,
            state_kind=REPLAY_SUMMARY_STATE_KIND,
            producer="replay-logger",
            source_state_kind=state.get("source_state_kind") or REPLAY_SUMMARY_STATE_KIND,
        )

    global_state = state.get("global_state") or {}
    players = state.get("players") or {}
    summary_players: dict[str, Any] = {}
    for player_key, player_state in players.items():
        if not isinstance(player_state, dict):
            continue

        plantations_counter = Counter()
        for tile_id in _normalize_numeric_list(player_state.get("island_tiles", [])):
            if tile_id == int(TileType.EMPTY):
                continue
            plantations_counter[_tile_name(tile_id).lower().replace(" ", "_")] += 1

        buildings = [
            _building_name(building_id).lower().replace(" ", "_")
            for building_id in _normalize_numeric_list(player_state.get("city_buildings", []))
            if building_id not in (int(BuildingType.EMPTY), int(BuildingType.OCCUPIED_SPACE))
        ]

        goods_values = _normalize_numeric_list(player_state.get("goods", []))
        goods = {
            _good_name(idx).lower(): count
            for idx, count in enumerate(goods_values)
            if count
        }

        summary_players[player_key] = {
            "doubloons": _as_int(player_state.get("doubloons", 0), 0),
            "vp": _as_int(player_state.get("vp_chips", 0), 0),
            "goods": goods,
            "plantations": dict(plantations_counter),
            "buildings": buildings,
            "unplaced_colonists": _as_int(player_state.get("unplaced_colonists", 0), 0),
        }

    phase_id = _as_int(global_state.get("current_phase"), None)
    return with_state_contract({
        "phase": _phase_name(phase_id),
        "phase_id": phase_id,
        "current_player": _as_int(global_state.get("current_player"), None),
        "governor": _as_int(global_state.get("governor_idx"), None),
        "vp_supply": _as_int(global_state.get("vp_chips"), None),
        "colonist_supply": _as_int(global_state.get("colonists_supply"), None),
        "colonist_ship": _as_int(global_state.get("colonists_ship"), None),
        "players": summary_players,
    },
        schema_version=REPLAY_SUMMARY_SCHEMA_VERSION,
        state_kind=REPLAY_SUMMARY_STATE_KIND,
        producer="replay-logger",
        source_state_kind=extract_state_kind(state, MODEL_OBSERVATION_STATE_KIND),
    )


def _describe_delta(before_value: Any, after_value: Any, label: str) -> str | None:
    before_value = _unwrap_singleton(before_value)
    after_value = _unwrap_singleton(after_value)
    if not isinstance(before_value, (int, float)) or not isinstance(after_value, (int, float)):
        if before_value == after_value:
            return None
        return f"{label} {before_value} -> {after_value}"
    delta = after_value - before_value
    if delta == 0:
        return None
    sign = "+" if delta > 0 else ""
    return f"{label} {sign}{delta}"


def _build_commentary(
    *,
    player_key: str | None,
    before_summary: dict[str, Any],
    after_summary: dict[str, Any],
    reward: float,
    done: bool,
) -> str:
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


def _degraded_summary(state: dict[str, Any] | None, exc: Exception) -> dict[str, Any]:
    return with_state_contract(
        {
            "players": {},
            "degraded": True,
            "validation_error": str(exc),
        },
        schema_version=REPLAY_SUMMARY_SCHEMA_VERSION,
        state_kind=REPLAY_SUMMARY_STATE_KIND,
        producer="replay-logger",
        source_state_kind=extract_state_kind(state, MODEL_OBSERVATION_STATE_KIND),
    )


def _safe_summary(state: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    try:
        return summarize_transition_state(state), "ok"
    except Exception as exc:
        return _degraded_summary(state, exc), "degraded"


def describe_action(action_id: int, *, state_before: dict[str, Any] | None = None) -> str:
    if 0 <= action_id <= 7:
        return f"Select Role: {_role_name(action_id)}"

    if 8 <= action_id <= 13:
        face_up = _normalize_numeric_list(
            ((state_before or {}).get("global_state") or {}).get("face_up_plantations") or []
        )
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
    adapter_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    phase_id = _as_int(((state_before or {}).get("global_state") or {}).get("current_phase"), None)
    player_key = f"player_{player_index}" if player_index is not None else None
    before_summary, before_status = _safe_summary(state_before)
    after_summary, after_status = _safe_summary(state_after)
    degraded_replay_used = before_status != "ok" or after_status != "ok"

    commentary = None
    commentary_status = "ok"
    if not degraded_replay_used:
        try:
            commentary = _build_commentary(
                player_key=player_key,
                before_summary=before_summary,
                after_summary=after_summary,
                reward=reward,
                done=done,
            )
        except Exception:
            commentary_status = "degraded"
            degraded_replay_used = True
    else:
        commentary_status = "degraded"

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
        "commentary": commentary,
        "commentary_status": commentary_status,
        "summary_validation_status": "ok" if not degraded_replay_used else "degraded",
        "degraded_replay_used": degraded_replay_used,
        "state_before_kind": extract_state_kind(state_before, MODEL_OBSERVATION_STATE_KIND),
        "state_after_kind": extract_state_kind(state_after, MODEL_OBSERVATION_STATE_KIND),
        "state_summary_before": before_summary,
        "state_summary_after": after_summary,
    }
    if model_info is not None:
        entry["model_info"] = enrich_actor_snapshot(model_info)
    if adapter_info is not None:
        entry["adapter_info"] = dict(adapter_info)
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


def _load_payload_from_db(*, game_id: UUID | str, db: Session) -> dict[str, Any] | None:
    replay = db.query(Replay).filter(Replay.game_id == _db_game_id(game_id)).first()
    payload = replay.payload if replay else None
    return payload if isinstance(payload, dict) else None


def _write_payload_to_db(*, game_id: UUID | str, payload: dict[str, Any], db: Session) -> None:
    replay = db.query(Replay).filter(Replay.game_id == _db_game_id(game_id)).first()
    if replay is None:
        replay = Replay(game_id=_db_game_id(game_id), payload=payload)
        db.add(replay)
    else:
        replay.payload = payload
    db.flush()


def replay_payload_exists(*, game_id: UUID | str, db: Session | None = None) -> bool:
    if replay_storage_backend() == "db":
        if db is None:
            return False
        return _load_payload_from_db(game_id=game_id, db=db) is not None
    return os.path.exists(get_replay_file_path(game_id))


def load_replay_payload(*, game_id: UUID | str, db: Session | None = None) -> dict[str, Any] | None:
    if replay_storage_backend() == "db":
        if db is None:
            return None
        return _load_payload_from_db(game_id=game_id, db=db)
    try:
        return _load_payload(get_replay_file_path(game_id))
    except (OSError, json.JSONDecodeError):
        return None


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
        db: Session | None = None,
    ) -> str:
        storage_backend = replay_storage_backend()
        if storage_backend == "db":
            if db is None:
                raise RuntimeError("Replay DB storage requires a database session")
            payload = _load_payload_from_db(game_id=game_id, db=db) or _base_payload(
                game_id=game_id,
                title=title,
                status=status,
                host_id=host_id,
                players=players,
                model_versions=model_versions,
                initial_state_summary=initial_state_summary,
            )
        else:
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
        if storage_backend == "db":
            _write_payload_to_db(game_id=game_id, payload=payload, db=db)
        else:
            _write_payload(path, payload)
            return path
        return str(game_id)

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
        db: Session | None = None,
    ) -> str:
        storage_backend = replay_storage_backend()
        if storage_backend == "db":
            if db is None:
                raise RuntimeError("Replay DB storage requires a database session")
            payload = _load_payload_from_db(game_id=game_id, db=db) or _base_payload(
                game_id=game_id,
                title=title,
                status=status,
                host_id=host_id,
                players=players,
                model_versions=model_versions,
                initial_state_summary=None,
            )
        else:
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
        if storage_backend == "db":
            _write_payload_to_db(game_id=game_id, payload=payload, db=db)
        else:
            _write_payload(path, payload)
            return path
        return str(game_id)
