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
DISPLAY_LABELS = {
    "overall": "전체 사람 포함 PPO 대국",
    "human": "사람",
    "ppo": "PPO",
    "human + ppo + action_value": "사람 + PPO + action_value",
    "human + ppo + ppo": "사람 + PPO + PPO",
}
RANK_SEGMENTS: tuple[tuple[str, str, str], ...] = (
    ("1등", "first_place_games", "#16a34a"),
    ("2등", "second_place_games", "#2563eb"),
    ("3등", "third_place_games", "#f59e0b"),
    ("미집계", "unknown_rank_games", "#9ca3af"),
)
OUTCOME_SEGMENTS: tuple[tuple[str, str, str], ...] = (
    ("승", "ppo_wins", "#16a34a"),
    ("패", "ppo_losses", "#dc2626"),
    ("무", "draws", "#6b7280"),
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
        "first_place_games": 0,
        "second_place_games": 0,
        "third_place_games": 0,
        "rank_games": 0,
        "unknown_rank_games": 0,
        "first_place_rate": None,
        "second_place_rate": None,
        "third_place_rate": None,
    }


def _finalize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    games = int(stats["games"])
    wins = int(stats["ppo_wins"])
    rank_games = int(stats["rank_games"])
    first_place_games = int(stats["first_place_games"])
    second_place_games = int(stats["second_place_games"])
    third_place_games = int(stats["third_place_games"])
    return {
        **stats,
        "win_rate": round(wins / games, 4) if games > 0 else 0.0,
        "first_place_rate": (
            round(first_place_games / rank_games, 4) if rank_games > 0 else None
        ),
        "second_place_rate": (
            round(second_place_games / rank_games, 4) if rank_games > 0 else None
        ),
        "third_place_rate": (
            round(third_place_games / rank_games, 4) if rank_games > 0 else None
        ),
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


def _add_rank(stats: dict[str, Any], best_ppo_rank: Any) -> None:
    if best_ppo_rank == 1:
        stats["first_place_games"] += 1
        stats["rank_games"] += 1
        return
    if best_ppo_rank == 2:
        stats["second_place_games"] += 1
        stats["rank_games"] += 1
        return
    if best_ppo_rank == 3:
        stats["third_place_games"] += 1
        stats["rank_games"] += 1
        return
    stats["unknown_rank_games"] += 1


def _add_row(stats: dict[str, Any], row: dict[str, Any]) -> None:
    _add_result(stats, row.get("ppo_result"))
    _add_rank(stats, row.get("best_ppo_rank"))


def _translate_part(part: str) -> str:
    normalized = part.strip()
    direct = DISPLAY_LABELS.get(normalized)
    if direct is not None:
        return str(direct)

    translated = normalized.replace("human", "사람").replace("ppo", "PPO")
    return translated


def _display_label(lineup_signature: str) -> str:
    direct = DISPLAY_LABELS.get(lineup_signature)
    if direct is not None:
        return str(direct)

    for separator in (" + ", " > "):
        if separator in lineup_signature:
            parts = [_translate_part(part) for part in lineup_signature.split(separator)]
            return separator.join(parts)
    return lineup_signature


def _format_percent(rate: float | None) -> str:
    if rate is None:
        return "-"
    return f"{rate * 100:.1f}%"


def _format_record(row: dict[str, Any]) -> str:
    return (
        f'전적: 총 {row["games"]}판, '
        f'{row["ppo_wins"]}승 {row["ppo_losses"]}패 {row["draws"]}무승부'
    )


def _format_rank_note(row: dict[str, Any]) -> str:
    rank_games = int(row["rank_games"])
    unknown_rank_games = int(row["unknown_rank_games"])
    if rank_games <= 0:
        if int(row["games"]) <= 0:
            return "순위 집계 대상 경기 없음"
        return f'순위 데이터 없음 ({row["games"]}판)'
    if unknown_rank_games > 0:
        return f"순위 집계 {rank_games}판, 미집계 {unknown_rank_games}판"
    return f"순위 집계 {rank_games}판"


def _format_segment_legend(
    row: dict[str, Any],
    segments: tuple[tuple[str, str, str], ...],
) -> str:
    parts = [
        f'{label} {int(row.get(field) or 0)}판'
        for label, field, _color in segments
    ]
    return " | ".join(parts)


def _render_stacked_bar(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    total: int,
    row: dict[str, Any],
    segments: tuple[tuple[str, str, str], ...],
) -> list[str]:
    lines = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="5" fill="#e5e7eb"/>'
    ]
    if total <= 0:
        return lines

    current_x = x
    remaining_width = width
    non_zero_segments = [
        (label, field, color, int(row.get(field) or 0))
        for label, field, color in segments
        if int(row.get(field) or 0) > 0
    ]
    for index, (_label, _field, color, count) in enumerate(non_zero_segments):
        if index == len(non_zero_segments) - 1:
            segment_width = remaining_width
        else:
            segment_width = round(width * (count / total))
            segment_width = min(segment_width, remaining_width)
        if segment_width <= 0:
            continue
        lines.append(
            f'<rect x="{current_x}" y="{y}" width="{segment_width}" height="{height}" rx="5" fill="{color}"/>'
        )
        current_x += segment_width
        remaining_width -= segment_width
    return lines


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
            _add_row(target, row)

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
        _add_row(grouped[label], row)

    return [
        _finalize_stats(grouped[label])
        for label, _composition in REQUESTED_MATCHUPS
    ]


def build_report_summary(
    rows: list[dict[str, Any]],
    *,
    all_lineups: bool = False,
    min_games: int = 1,
) -> list[dict[str, Any]]:
    if all_lineups:
        return summarize_ppo_human_rows(rows, min_games=max(min_games, 1))
    return summarize_requested_matchups(rows)


def render_svg_chart(
    summary: list[dict[str, Any]],
    *,
    title: str = "사람 포함 대국에서의 PPO 성적",
) -> str:
    width = 1380
    margin_x = 40
    header_height = 118
    table_header_height = 44
    row_height = 112
    footer_height = 24
    height = header_height + table_header_height + max(len(summary), 1) * row_height + footer_height

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{margin_x}" y="42" font-family="Arial, sans-serif" font-size="26" font-weight="700" fill="#1f2937">{escape(title)}</text>',
        f'<text x="{margin_x}" y="70" font-family="Arial, sans-serif" font-size="14" fill="#6b7280">사람이 포함된 FINISHED 3인 대국에서 PPO 기준 성적을 누적 막대로 시각화한 결과입니다.</text>',
        f'<text x="{margin_x}" y="92" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">순위 분포는 1등/2등/3등/미집계를 모두 포함하며, 승패 분포는 전체 경기 기준입니다.</text>',
    ]

    if not summary:
        lines.extend(
            [
                f'<text x="{margin_x}" y="{header_height + 28}" font-family="Arial, sans-serif" font-size="18" fill="#6b7280">사람이 포함된 PPO 대국 데이터가 없습니다.</text>',
                "</svg>",
            ]
        )
        return "\n".join(lines)

    columns = [
        ("대국 조합", 48),
        ("순위 분포", 320),
        ("승/패/무승부 분포", 760),
        ("요약", 1088),
    ]
    table_y = header_height
    lines.append(
        f'<rect x="{margin_x}" y="{table_y}" width="{width - margin_x * 2}" height="{table_header_height}" rx="6" fill="#f3f4f6"/>'
    )
    for header, x in columns:
        lines.append(
            f'<text x="{x}" y="{table_y + 28}" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#374151">{escape(header)}</text>'
        )

    for index, row in enumerate(summary):
        y = table_y + table_header_height + index * row_height
        bg_fill = "#ffffff" if index % 2 == 0 else "#f9fafb"
        label = _display_label(str(row["lineup_signature"]))
        record = _format_record(row)
        rank_note = _format_rank_note(row)
        rank_legend = _format_segment_legend(row, RANK_SEGMENTS)
        outcome_legend = _format_segment_legend(row, OUTCOME_SEGMENTS)
        rank_bar_y = y + 20
        outcome_bar_y = y + 20
        rank_total = int(row["games"])
        outcome_total = int(row["games"])

        lines.extend(
            [
                f'<rect x="{margin_x}" y="{y}" width="{width - margin_x * 2}" height="{row_height}" fill="{bg_fill}"/>',
                f'<line x1="{margin_x}" y1="{y + row_height}" x2="{width - margin_x}" y2="{y + row_height}" stroke="#e5e7eb"/>',
                f'<text x="{columns[0][1]}" y="{y + 34}" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#111827">{escape(label)}</text>',
                f'<text x="{columns[0][1]}" y="{y + 60}" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{escape(record)}</text>',
                f'<text x="{columns[0][1]}" y="{y + 84}" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{escape(rank_note)}</text>',
                f'<text x="{columns[3][1]}" y="{y + 34}" font-family="Arial, sans-serif" font-size="14" font-weight="700" fill="#2563eb">총 {row["games"]}판</text>',
                f'<text x="{columns[3][1]}" y="{y + 58}" font-family="Arial, sans-serif" font-size="12" fill="#374151">{escape(record)}</text>',
                f'<text x="{columns[3][1]}" y="{y + 82}" font-family="Arial, sans-serif" font-size="12" fill="#6b7280">{escape(rank_note)}</text>',
            ]
        )
        lines.extend(
            _render_stacked_bar(
                x=columns[1][1],
                y=rank_bar_y,
                width=360,
                height=16,
                total=rank_total,
                row=row,
                segments=RANK_SEGMENTS,
            )
        )
        lines.extend(
            _render_stacked_bar(
                x=columns[2][1],
                y=outcome_bar_y,
                width=280,
                height=16,
                total=outcome_total,
                row=row,
                segments=OUTCOME_SEGMENTS,
            )
        )
        lines.extend(
            [
                f'<text x="{columns[1][1]}" y="{y + 52}" font-family="Arial, sans-serif" font-size="12" fill="#374151">{escape(rank_legend)}</text>',
                f'<text x="{columns[2][1]}" y="{y + 52}" font-family="Arial, sans-serif" font-size="12" fill="#374151">{escape(outcome_legend)}</text>',
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
        default="사람 포함 대국에서의 PPO 성적",
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
        summary = build_report_summary(
            rows,
            all_lineups=args.all_lineups,
            min_games=args.min_games,
        )
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
