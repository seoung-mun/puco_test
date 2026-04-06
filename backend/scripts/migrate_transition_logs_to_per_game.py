#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_LOG_DIR = REPO_ROOT / "data" / "logs"
DEFAULT_OUTPUT_DIR = LEGACY_LOG_DIR / "games"


def iter_legacy_paths(input_paths: list[str] | None) -> list[Path]:
    if input_paths:
        paths: list[Path] = []
        for raw in input_paths:
            path = Path(raw).resolve()
            if path.is_file():
                paths.append(path)
            elif path.is_dir():
                paths.extend(sorted(path.glob("transitions_*.jsonl")))
        return sorted(dict.fromkeys(paths))
    return sorted(LEGACY_LOG_DIR.glob("transitions_*.jsonl"))


def migrate(paths: list[Path], output_dir: Path, overwrite: bool = False) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[str]] = defaultdict(list)

    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                game_id = record.get("game_id")
                if not game_id:
                    continue
                grouped[str(game_id)].append(json.dumps(record))

    file_count = 0
    row_count = 0
    for game_id, rows in grouped.items():
        target = output_dir / f"{game_id}.jsonl"
        mode = "w" if overwrite else "a"
        with target.open(mode, encoding="utf-8") as handle:
            for row in rows:
                handle.write(row + "\n")
        file_count += 1
        row_count += len(rows)

    return file_count, row_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Split legacy daily transition logs into one JSONL per game.")
    parser.add_argument("paths", nargs="*", help="Optional legacy transitions_*.jsonl files or directories")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for per-game JSONL files. Default: data/logs/games",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing per-game files instead of appending.",
    )
    args = parser.parse_args()

    legacy_paths = iter_legacy_paths(args.paths)
    if not legacy_paths:
        print("No legacy transitions_*.jsonl files found.")
        return

    file_count, row_count = migrate(
        paths=legacy_paths,
        output_dir=Path(args.output_dir).resolve(),
        overwrite=args.overwrite,
    )
    print(f"Migrated {row_count} rows into {file_count} per-game files.")


if __name__ == "__main__":
    main()
