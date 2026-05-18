"""
Generate an SVG chart for PPO win rates in games that include humans.

Usage:
    python -m scripts.visualize_ppo_human_winrate --output ppo_human_winrate.svg
    python -m scripts.visualize_ppo_human_winrate --json-output ppo_human_winrate.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from html import escape
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.analytics import ppo_lineup_games


REQUESTED_MATCHUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("human + ppo + action_value", ("action_value", "human", "ppo")),
    ("human + ppo + ppo", ("human", "ppo", "ppo")),
)


def _build_session():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("오류: DATABASE_URL 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        raise SystemExit(1)

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.execute(text("SET TRANSACTION READ ONLY"))
    return db


def _empty_stats(lineup_signature: str) -> dict[str, Any]:
    return {
        "lineup_signature": lineup_signature,
        "games": 0,
        "ppo_wins": 0,
        "ppo_losses": 0,
        "draws": 0,
        "win_rate": 0.0,
    }


def _finalize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    games = int(stats["games"])
    wins = int(stats["ppo_wins"])
    return {
        **stats,
        "win_rate": round(wins / games, 4) if games > 0 else 0.0,
    }


def _lineup_parts(lineup_signature: str) -> list[str]:
    return [part.strip() for part in lineup_signature.split(">") if part.strip()]


def _add_result(stats: dict[str, Any], ppo_result: Any) -> None:
    stats["games"] += 1
    if ppo_result == "win":
        stats["ppo_wins"] += 1
    elif ppo_result == "draw":
        stats["draws"] += 1
    else:
        stats["ppo_losses"] += 1


def summarize_ppo_human_rows(
    rows: list[dict[str, Any]],
    *,
    min_games: int = 1,
) -> list[dict[str, Any]]:
    """Return overall and lineup-level PPO win-rate rows for games with humans."""
    grouped: dict[str, dict[str, Any]] = {}
    overall = _empty_stats("overall")

    for row in rows:
        lineup_signature = str(row.get("lineup_signature") or "")
        parts = _lineup_parts(lineup_signature)
        if "human" not in parts:
            continue

        stats = grouped.setdefault(lineup_signature, _empty_stats(lineup_signature))
        for target in (overall, stats):
            _add_result(target, row.get("ppo_result"))

    if overall["games"] == 0:
        return []

    result = [_finalize_stats(overall)]
    lineup_rows = [
        _finalize_stats(stats)
        for stats in grouped.values()
        if stats["games"] >= min_games
    ]
    lineup_rows.sort(
        key=lambda row: (
            -row["games"],
            -row["win_rate"],
            row["lineup_signature"],
        )
    )
    result.extend(lineup_rows)
    return result


def summarize_requested_matchups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the two requested PPO-human matchup buckets, ignoring seat order."""
    grouped = {
        label: _empty_stats(label)
        for label, _composition in REQUESTED_MATCHUPS
    }
    composition_to_label = {
        composition: label
        for label, composition in REQUESTED_MATCHUPS
    }

    for row in rows:
        parts = tuple(sorted(_lineup_parts(str(row.get("lineup_signature") or ""))))
        label = composition_to_label.get(parts)
        if label is None:
            continue
        _add_result(grouped[label], row.get("ppo_result"))

    return [
        _finalize_stats(grouped[label])
        for label, _composition in REQUESTED_MATCHUPS
    ]


def render_svg_chart(
    summary: list[dict[str, Any]],
    *,
    title: str = "PPO Win Rate vs Human Games",
) -> str:
    width = 1100
    margin_x = 40
    label_x = 48
    bar_x = 360
    bar_width = 520
    row_height = 58
    header_height = 96
    footer_height = 36
    height = header_height + max(len(summary), 1) * row_height + footer_height

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{margin_x}" y="42" font-family="Arial, sans-serif" font-size="26" font-weight="700" fill="#1f2937">{escape(title)}</text>',
        f'<text x="{margin_x}" y="70" font-family="Arial, sans-serif" font-size="14" fill="#6b7280">PPO win rate in FINISHED 3-player games that include at least one human.</text>',
    ]

    if not summary:
        lines.extend(
            [
                f'<text x="{margin_x}" y="{header_height + 28}" font-family="Arial, sans-serif" font-size="18" fill="#6b7280">No PPO-human games found.</text>',
                "</svg>",
            ]
        )
        return "\n".join(lines)

    for index, row in enumerate(summary):
        y = header_height + index * row_height
        rate = float(row["win_rate"])
        filled = int(bar_width * rate)
        label = str(row["lineup_signature"])
        percent = f"{rate * 100:.1f}%"
        detail = (
            f'{row["games"]} games | '
            f'{row["ppo_wins"]} W / {row["ppo_losses"]} L / {row["draws"]} D'
        )
        bar_color = "#0f766e" if label == "overall" else "#2563eb"

        lines.extend(
            [
                f'<text x="{label_x}" y="{y + 24}" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#111827">{escape(label)}</text>',
                f'<text x="{label_x}" y="{y + 44}" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{escape(detail)}</text>',
                f'<rect x="{bar_x}" y="{y + 10}" width="{bar_width}" height="26" rx="4" fill="#e5e7eb"/>',
                f'<rect x="{bar_x}" y="{y + 10}" width="{filled}" height="26" rx="4" fill="{bar_color}"/>',
                f'<text x="{bar_x + bar_width + 18}" y="{y + 29}" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#111827">{percent}</text>',
            ]
        )

    lines.append("</svg>")
    return "\n".join(lines)


def write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visualize_ppo_human_winrate",
        description="PPO가 사람이 포함된 대국에서 기록한 승률을 SVG로 시각화합니다.",
    )
    parser.add_argument(
        "--output",
        default="ppo_human_winrate.svg",
        help="SVG 출력 경로 (기본: ppo_human_winrate.svg)",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="요약 JSON도 저장할 경로",
    )
    parser.add_argument(
        "--min-games",
        type=int,
        default=1,
        help="조합별 행을 표시할 최소 게임 수 (기본: 1)",
    )
    parser.add_argument(
        "--title",
        default="PPO Win Rate: Target Human Matchups",
        help="SVG 차트 제목",
    )
    parser.add_argument(
        "--all-lineups",
        action="store_true",
        help="요청된 2개 matchup 대신 사람 포함 PPO 전체와 좌석별 조합을 모두 표시",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    db = _build_session()
    try:
        rows = ppo_lineup_games(db, limit=0)
        if args.all_lineups:
            summary = summarize_ppo_human_rows(rows, min_games=max(args.min_games, 1))
        else:
            summary = summarize_requested_matchups(rows)
        svg = render_svg_chart(summary, title=args.title)
        write_text(args.output, svg)
        if args.json_output:
            write_text(
                args.json_output,
                json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            )
        print(f"wrote SVG: {args.output}")
        if args.json_output:
            print(f"wrote JSON: {args.json_output}")
        print(f"rows: {len(summary)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
