from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = REPO_ROOT / "data" / "logs"


@dataclass
class GameSessionSnapshot:
    game_id: str
    title: str | None
    status: str | None
    host_id: str | None
    players: list[str]
    model_versions: dict[str, Any]
    created_at: str | None


@dataclass
class GameLogSnapshot:
    id: int | None
    game_id: str
    round: int | None
    step: int | None
    actor_id: str | None
    action: int | None
    action_data: dict[str, Any]
    available_options: list[Any]
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    state_summary: dict[str, Any] | None
    timestamp: str | None


@dataclass
class DataContext:
    game_id: str | None
    db_url: str | None
    room: GameSessionSnapshot | None
    game_logs: list[GameLogSnapshot]
    transitions: list[dict[str, Any]]
    transition_files: list[Path]
    warnings: list[str]


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--game-id", help="Target game UUID. If omitted, try the newest game in logs/DB.")
    parser.add_argument("--db-url", help="Database URL. Defaults to DATABASE_URL if set.")
    parser.add_argument(
        "--jsonl",
        action="append",
        dest="jsonl_paths",
        help="Specific transition JSONL file. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output",
        help="Write the generated markdown to this path. Prints to stdout when omitted.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Maximum number of step rows to render in detailed sections.",
    )
    parser.add_argument(
        "--lang",
        choices=("en", "ko"),
        default=os.getenv("VIS_LANG", "en"),
        help="Report language. Supported: en, ko.",
    )
    return parser


def resolve_db_url(explicit: str | None) -> str | None:
    return explicit or os.getenv("DATABASE_URL")


def _coerce_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.min
    text_value = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text_value)
    except ValueError:
        return datetime.min


def discover_transition_files(explicit_paths: Sequence[str] | None = None) -> list[Path]:
    if explicit_paths:
        resolved: list[Path] = []
        for path_str in explicit_paths:
            path = Path(path_str).resolve()
            if path.is_file():
                resolved.append(path)
            elif path.is_dir():
                game_dir = path / "games"
                if game_dir.exists():
                    resolved.extend(sorted(game_dir.rglob("*.jsonl")))
                else:
                    resolved.extend(sorted(path.rglob("*.jsonl")))
        return sorted(dict.fromkeys(resolved))
    if not DEFAULT_LOG_DIR.exists():
        return []
    per_game_dir = DEFAULT_LOG_DIR / "games"
    if per_game_dir.exists():
        per_game_files = sorted(per_game_dir.rglob("*.jsonl"))
        if per_game_files:
            return per_game_files
    return sorted(DEFAULT_LOG_DIR.glob("transitions_*.jsonl"))


def load_transition_records(paths: Sequence[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    record["_source_file"] = str(path)
                    record["_source_line"] = line_no
                    records.append(record)
        except OSError:
            continue
    return records


def _get_path(data: dict[str, Any] | None, path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def extract_transition_round(record: dict[str, Any]) -> int | None:
    value = _get_path(record, "info.round")
    if value is None:
        value = _get_path(record, "state_after.meta.round")
    return _safe_int(value)


def extract_transition_step(record: dict[str, Any]) -> int | None:
    for path in ("info.step", "state_after.meta.step_count", "state_after.step", "state_before.step"):
        value = _get_path(record, path)
        if value is not None:
            return _safe_int(value)
    return None


def extract_transition_phase(record: dict[str, Any]) -> int | None:
    for path in ("phase_id_before", "state_before.global_state.current_phase", "state_before.meta.phase_id"):
        value = _get_path(record, path)
        if value is not None:
            return _safe_int(value)
    return None


def extract_transition_model_info(record: dict[str, Any]) -> dict[str, Any] | None:
    model_info = record.get("model_info")
    return model_info if isinstance(model_info, dict) else None


def infer_bot_type(actor_id: str | None, model_info: dict[str, Any] | None = None) -> str:
    if model_info and model_info.get("bot_type"):
        return str(model_info["bot_type"])
    actor = str(actor_id or "")
    if not actor.startswith("BOT_"):
        return "human"
    suffix = actor[4:].lower()
    return suffix.split("_", 1)[0] if "_" in suffix else (suffix or "random")


def latest_game_id_from_transitions(records: Sequence[dict[str, Any]]) -> str | None:
    candidates = [
        (_safe_ts(record.get("timestamp")), str(record.get("game_id")))
        for record in records
        if record.get("game_id")
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[-1][1]


def latest_game_id_from_db(db_url: str | None) -> str | None:
    if not db_url:
        return None
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT CAST(id AS TEXT) AS id FROM games ORDER BY created_at DESC LIMIT 1")
            ).mappings().first()
        return str(row["id"]) if row and row.get("id") else None
    except SQLAlchemyError:
        return None


def load_game_session(db_url: str | None, game_id: str | None) -> GameSessionSnapshot | None:
    if not db_url or not game_id:
        return None
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        CAST(id AS TEXT) AS id,
                        title,
                        status,
                        host_id,
                        players,
                        model_versions,
                        created_at
                    FROM games
                    WHERE CAST(id AS TEXT) = :game_id
                    """
                ),
                {"game_id": game_id},
            ).mappings().first()
        if not row:
            return None
        return GameSessionSnapshot(
            game_id=str(row["id"]),
            title=row.get("title"),
            status=row.get("status"),
            host_id=row.get("host_id"),
            players=list(_coerce_json(row.get("players")) or []),
            model_versions=dict(_coerce_json(row.get("model_versions")) or {}),
            created_at=str(row.get("created_at")) if row.get("created_at") is not None else None,
        )
    except SQLAlchemyError:
        return None


def load_game_logs(db_url: str | None, game_id: str | None) -> list[GameLogSnapshot]:
    if not db_url or not game_id:
        return []
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        CAST(game_id AS TEXT) AS game_id,
                        round,
                        step,
                        actor_id,
                        action_data,
                        available_options,
                        state_before,
                        state_after,
                        state_summary,
                        timestamp
                    FROM game_logs
                    WHERE CAST(game_id AS TEXT) = :game_id
                    ORDER BY step ASC, id ASC
                    """
                ),
                {"game_id": game_id},
            ).mappings().all()
    except SQLAlchemyError:
        return []

    result: list[GameLogSnapshot] = []
    for row in rows:
        action_data = dict(_coerce_json(row.get("action_data")) or {})
        result.append(
            GameLogSnapshot(
                id=_safe_int(row.get("id")),
                game_id=str(row.get("game_id")),
                round=_safe_int(row.get("round")),
                step=_safe_int(row.get("step")),
                actor_id=row.get("actor_id"),
                action=_safe_int(action_data.get("action")),
                action_data=action_data,
                available_options=list(_coerce_json(row.get("available_options")) or []),
                state_before=dict(_coerce_json(row.get("state_before")) or {}),
                state_after=dict(_coerce_json(row.get("state_after")) or {}),
                state_summary=_coerce_json(row.get("state_summary")),
                timestamp=str(row.get("timestamp")) if row.get("timestamp") is not None else None,
            )
        )
    return result


def load_context(
    *,
    game_id: str | None,
    db_url: str | None,
    jsonl_paths: Sequence[str] | None,
) -> DataContext:
    warnings: list[str] = []
    resolved_db_url = resolve_db_url(db_url)
    transition_files = discover_transition_files(jsonl_paths)
    all_transitions = load_transition_records(transition_files)

    effective_game_id = game_id or latest_game_id_from_transitions(all_transitions)
    if effective_game_id is None:
        effective_game_id = latest_game_id_from_db(resolved_db_url)

    filtered_transitions = [
        record for record in all_transitions if not effective_game_id or str(record.get("game_id")) == effective_game_id
    ]
    room = load_game_session(resolved_db_url, effective_game_id)
    game_logs = load_game_logs(resolved_db_url, effective_game_id)

    if resolved_db_url is None:
        warnings.append("DATABASE_URL is not set. DB-backed sections are rendered as local-log only.")
    elif room is None and not game_logs:
        warnings.append("DB lookup returned no matching game/session rows for the selected game_id.")

    if not transition_files:
        warnings.append("No transition JSONL files were found under data/logs.")
    elif not filtered_transitions:
        warnings.append("Transition files exist, but no rows matched the selected game_id.")

    if effective_game_id is None:
        warnings.append("No game_id could be inferred from either DB or local transition files.")

    return DataContext(
        game_id=effective_game_id,
        db_url=resolved_db_url,
        room=room,
        game_logs=game_logs,
        transitions=filtered_transitions,
        transition_files=transition_files,
        warnings=warnings,
    )


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    def _cell(value: Any) -> str:
        if value is None:
            return ""
        text_value = str(value).replace("\n", "<br>")
        return text_value.replace("|", "\\|")

    out = [
        "| " + " | ".join(_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(_cell(item) for item in row) + " |")
    return "\n".join(out)


def write_output(path: str | None, content: str) -> None:
    if not path:
        print(content)
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def field_coverage(records: Sequence[dict[str, Any]], field_paths: Sequence[str]) -> list[tuple[str, int, int]]:
    total = len(records)
    result = []
    for field_path in field_paths:
        count = sum(1 for record in records if _get_path(record, field_path) is not None)
        result.append((field_path, count, total))
    return result


def step_key_from_transition(record: dict[str, Any]) -> tuple[int, int, str]:
    round_value = extract_transition_round(record) or -1
    step_value = extract_transition_step(record) or -1
    actor_id = str(record.get("actor_id") or "")
    return (round_value, step_value, actor_id)


def step_key_from_gamelog(log: GameLogSnapshot) -> tuple[int, int, str]:
    return (log.round or -1, log.step or -1, str(log.actor_id or ""))


def build_step_join(
    game_logs: Sequence[GameLogSnapshot],
    transitions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    db_map = {step_key_from_gamelog(log): log for log in game_logs}
    jsonl_map = {step_key_from_transition(record): record for record in transitions}
    keys = sorted(set(db_map) | set(jsonl_map))
    joined = []
    for key in keys:
        joined.append(
            {
                "round": key[0] if key[0] >= 0 else None,
                "step": key[1] if key[1] >= 0 else None,
                "actor_id": key[2] or None,
                "db": db_map.get(key),
                "jsonl": jsonl_map.get(key),
            }
        )
    return joined


def normalize_json_blob(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    except TypeError:
        return repr(value)


def count_chain_breaks(
    records: Sequence[Any],
    *,
    get_before,
    get_after,
) -> tuple[int, list[tuple[int, int]]]:
    breaks: list[tuple[int, int]] = []
    for idx in range(1, len(records)):
        prev_after = normalize_json_blob(get_after(records[idx - 1]))
        curr_before = normalize_json_blob(get_before(records[idx]))
        if prev_after != curr_before:
            breaks.append((idx - 1, idx))
    return len(breaks), breaks


def bullet_list(items: Iterable[str], empty_label: str = "none") -> str:
    values = [f"- {item}" for item in items if item]
    return "\n".join(values) if values else f"- {empty_label}"


def model_snapshot_rows(room: GameSessionSnapshot | None) -> list[list[Any]]:
    if room is None:
        return []
    rows: list[list[Any]] = []
    for player_key, info in sorted(room.model_versions.items()):
        data = info if isinstance(info, dict) else {}
        rows.append(
            [
                player_key,
                data.get("actor_type", ""),
                data.get("bot_type", ""),
                data.get("artifact_name", ""),
                data.get("checkpoint_filename", ""),
                data.get("metadata_source", ""),
            ]
        )
    return rows


def coverage_badge(count: int, total: int, lang: str = "en") -> str:
    if total <= 0:
        return "0/0"
    ratio = count / total
    if ratio == 1.0:
        status = "정상" if lang == "ko" else "OK"
    elif ratio > 0:
        status = "부분" if lang == "ko" else "PARTIAL"
    else:
        status = "누락" if lang == "ko" else "MISSING"
    return f"{count}/{total} ({status})"


def top_game_ids(records: Sequence[dict[str, Any]], limit: int = 5) -> list[tuple[str, int]]:
    counts = Counter(str(record.get("game_id")) for record in records if record.get("game_id"))
    return counts.most_common(limit)
