"""
Rendering library for PPO rank-distribution SVG charts (human-included matchups).

This module exposes pure rendering / aggregation helpers. The CLI entry point
lives in `scripts.analytics_cli` (subcommand `ppo-human-winrate`).
"""
from __future__ import annotations

import math
from html import escape
from pathlib import Path
from typing import Any


REQUESTED_MATCHUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("human + ppo + action_value", ("action_value", "human", "ppo")),
    ("human + ppo + ppo", ("human", "ppo", "ppo")),
)
DISPLAY_LABELS = {
    "human": "사람",
    "ppo": "PPO",
    "human + ppo + action_value": "사람 + PPO + action_value",
    "human + ppo + ppo": "사람 + PPO + PPO",
}
RANK_BARS: tuple[tuple[str, str, str], ...] = (
    ("1등", "first_place_rate", "#4F6F9B"),
    ("2등", "second_place_rate", "#3F8E7C"),
    ("3등", "third_place_rate", "#7FB28F"),
)


def _empty_stats(lineup_signature: str) -> dict[str, Any]:
    return {
        "lineup_signature": lineup_signature,
        "games": 0,
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
    rank_games = int(stats["rank_games"])
    first_place_games = int(stats["first_place_games"])
    second_place_games = int(stats["second_place_games"])
    third_place_games = int(stats["third_place_games"])
    return {
        **stats,
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


def _accumulate_rank(stats: dict[str, Any], best_ppo_rank: Any) -> None:
    stats["games"] += 1
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


def _translate_part(part: str) -> str:
    normalized = part.strip()
    direct = DISPLAY_LABELS.get(normalized)
    if direct is not None:
        return str(direct)
    return normalized.replace("human", "사람").replace("ppo", "PPO")


def display_label(lineup_signature: str) -> str:
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


def _count_field_for(rate_field: str) -> str:
    return rate_field.replace("_rate", "_games")


def _count_axis_ticks(max_value: int) -> list[int]:
    """Return integer y-axis ticks (starting at 0) for an absolute-count axis."""
    if max_value <= 0:
        return [0, 1]
    target_steps = 5
    raw_step = max_value / target_steps
    magnitude = 10 ** math.floor(math.log10(raw_step)) if raw_step >= 1 else 1
    normalized = raw_step / magnitude
    if normalized <= 1:
        nice_step = 1 * magnitude
    elif normalized <= 2:
        nice_step = 2 * magnitude
    elif normalized <= 5:
        nice_step = 5 * magnitude
    else:
        nice_step = 10 * magnitude
    nice_step = max(1, int(nice_step))
    y_max = math.ceil(max_value / nice_step) * nice_step
    return list(range(0, y_max + 1, nice_step))


def summarize_requested_matchups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the two requested PPO-human matchup buckets, ignoring seat order."""
    grouped = {label: _empty_stats(label) for label, _composition in REQUESTED_MATCHUPS}
    composition_to_label = {
        composition: label for label, composition in REQUESTED_MATCHUPS
    }

    for row in rows:
        parts = tuple(sorted(_lineup_parts(str(row.get("lineup_signature") or ""))))
        label = composition_to_label.get(parts)
        if label is None:
            continue
        _accumulate_rank(grouped[label], row.get("best_ppo_rank"))

    return [
        _finalize_stats(grouped[label]) for label, _composition in REQUESTED_MATCHUPS
    ]


def render_rank_bar_chart(stats: dict[str, Any], *, title: str | None = None) -> str:
    """Render a vertical bar chart of PPO rank distribution for one matchup."""
    width = 520
    height = 420
    margin_left = 72
    margin_right = 32
    margin_top = 88
    margin_bottom = 64

    plot_x_start = margin_left
    plot_x_end = width - margin_right
    plot_y_top = margin_top
    plot_y_bottom = height - margin_bottom
    plot_width = plot_x_end - plot_x_start
    plot_height = plot_y_bottom - plot_y_top

    matchup_label = display_label(str(stats.get("lineup_signature") or ""))
    chart_title = title if title is not None else matchup_label
    subtitle = "PPO 순위 분포"

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width // 2}" y="38" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#1f2937">{escape(chart_title)}</text>',
        f'<text x="{width // 2}" y="62" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#6b7280">{escape(subtitle)}</text>',
    ]

    rank_games = int(stats.get("rank_games") or 0)
    rank_counts = [
        int(stats.get(_count_field_for(field)) or 0)
        for _label, field, _color in RANK_BARS
    ]
    max_bar_value = max(rank_counts) if rank_counts else 0
    ticks = _count_axis_ticks(max_bar_value)
    y_max = ticks[-1] if ticks else 1

    for tick in ticks:
        y = plot_y_bottom - (tick / y_max) * plot_height if y_max > 0 else plot_y_bottom
        lines.append(
            f'<line x1="{plot_x_start}" y1="{y:.1f}" x2="{plot_x_end}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1"/>'
        )
        lines.append(
            f'<text x="{plot_x_start - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="Arial, sans-serif" font-size="11" fill="#6b7280">{tick}판</text>'
        )

    lines.append(
        f'<line x1="{plot_x_start}" y1="{plot_y_top}" x2="{plot_x_start}" y2="{plot_y_bottom}" stroke="#9ca3af" stroke-width="1"/>'
    )
    lines.append(
        f'<line x1="{plot_x_start}" y1="{plot_y_bottom}" x2="{plot_x_end}" y2="{plot_y_bottom}" stroke="#9ca3af" stroke-width="1"/>'
    )

    if rank_games <= 0:
        lines.append(
            f'<text x="{width // 2}" y="{(plot_y_top + plot_y_bottom) / 2:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" fill="#6b7280">순위 집계 데이터 없음</text>'
        )
        lines.append("</svg>")
        return "\n".join(lines)

    bar_count = len(RANK_BARS)
    gap = 32
    bar_width = (plot_width - gap * (bar_count + 1)) / bar_count

    for index, (label, field, color) in enumerate(RANK_BARS):
        rate = float(stats.get(field) or 0.0)
        count = int(stats.get(_count_field_for(field)) or 0)
        bar_left = plot_x_start + gap + index * (bar_width + gap)
        bar_top = plot_y_bottom - (count / y_max) * plot_height if y_max > 0 else plot_y_bottom
        bar_height = plot_y_bottom - bar_top
        center_x = bar_left + bar_width / 2

        if bar_height > 0:
            lines.append(
                f'<rect x="{bar_left:.1f}" y="{bar_top:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="{color}"/>'
            )
        label_inside = bar_height >= 22
        value_y = bar_top + bar_height / 2 + 5 if label_inside else bar_top - 8
        value_fill = "#ffffff" if label_inside else "#1f2937"
        lines.append(
            f'<text x="{center_x:.1f}" y="{value_y:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="{value_fill}">{escape(_format_percent(rate))}</text>'
        )
        lines.append(
            f'<text x="{center_x:.1f}" y="{plot_y_bottom + 22:.1f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#374151">{escape(label)}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


def write_text(path: str | Path, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
