#!/usr/bin/env python3
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


PASS_ACTION = 15
ROLE_SELECTION_PHASE = 8
TRADER_PHASE = 4
CAPTAIN_PHASE = 5


def _iter_records(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _resolve_phase(record: dict) -> int | None:
    if record.get("phase_id_before") is not None:
        return int(record["phase_id_before"])
    state_before = record.get("state_before") or {}
    global_state = state_before.get("global_state") or {}
    phase = global_state.get("current_phase")
    return int(phase) if phase is not None else None


def _resolve_bot_type(actor_id: str) -> str:
    actor = str(actor_id)
    if not actor.startswith("BOT_"):
        return "human"
    suffix = actor[4:].lower()
    if "_" in suffix:
        return suffix.split("_", 1)[0]
    return suffix or "random"


def analyze(path: Path) -> dict:
    role_counts = Counter()
    trader_counts = Counter()
    captain_counts = Counter()
    phase_counts = Counter()
    bot_counts = Counter()
    valid_action_counts = defaultdict(list)

    for record in _iter_records(path):
        actor_id = str(record.get("actor_id", ""))
        if not actor_id.startswith("BOT_"):
            continue

        bot_type = _resolve_bot_type(actor_id)
        phase_id = _resolve_phase(record)
        action = record.get("action")
        action_mask = record.get("action_mask_before") or []
        valid_count = sum(1 for allowed in action_mask if allowed)

        bot_counts[bot_type] += 1
        if phase_id is not None:
            phase_counts[(bot_type, phase_id)] += 1
            valid_action_counts[(bot_type, phase_id)].append(valid_count)

        if phase_id == ROLE_SELECTION_PHASE:
            role_counts[(bot_type, action)] += 1
        elif phase_id == TRADER_PHASE:
            trader_counts[(bot_type, "pass" if action == PASS_ACTION else "sell")] += 1
        elif phase_id == CAPTAIN_PHASE:
            captain_counts[(bot_type, "pass" if action == PASS_ACTION else "load")] += 1

    return {
        "bot_counts": bot_counts,
        "phase_counts": phase_counts,
        "role_counts": role_counts,
        "trader_counts": trader_counts,
        "captain_counts": captain_counts,
        "valid_action_counts": valid_action_counts,
    }


def _print_section(title: str, entries):
    print(f"\n[{title}]")
    if not entries:
        print("no data")
        return
    for key, value in entries:
        print(f"{key}: {value}")


def main():
    parser = argparse.ArgumentParser(description="Analyze bot transitions from ML logs.")
    parser.add_argument("path", type=Path, help="Path to transitions_*.jsonl")
    args = parser.parse_args()

    result = analyze(args.path)

    _print_section(
        "bot_counts",
        sorted(result["bot_counts"].items()),
    )
    _print_section(
        "role_selection",
        sorted(result["role_counts"].items()),
    )
    _print_section(
        "trader",
        sorted(result["trader_counts"].items()),
    )
    _print_section(
        "captain",
        sorted(result["captain_counts"].items()),
    )

    avg_valid = []
    for key, counts in sorted(result["valid_action_counts"].items()):
        if not counts:
            continue
        avg_valid.append((key, round(sum(counts) / len(counts), 2)))
    _print_section("avg_valid_actions", avg_valid)


if __name__ == "__main__":
    main()
