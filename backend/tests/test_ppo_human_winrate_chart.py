from __future__ import annotations

from scripts.visualize_ppo_human_winrate import (
    render_svg_chart,
    summarize_ppo_human_rows,
    summarize_requested_matchups,
)


def test_summarize_ppo_human_rows_groups_overall_and_excludes_bot_only():
    rows = [
        {"lineup_signature": "human > ppo > random", "ppo_result": "win"},
        {"lineup_signature": "human > ppo > random", "ppo_result": "loss"},
        {"lineup_signature": "ppo > human > human", "ppo_result": "draw"},
        {"lineup_signature": "ppo > ppo > random", "ppo_result": "win"},
    ]

    summary = summarize_ppo_human_rows(rows)

    assert summary[0] == {
        "lineup_signature": "overall",
        "games": 3,
        "ppo_wins": 1,
        "ppo_losses": 1,
        "draws": 1,
        "win_rate": 0.3333,
    }
    by_lineup = {row["lineup_signature"]: row for row in summary[1:]}
    assert by_lineup["human > ppo > random"]["games"] == 2
    assert by_lineup["human > ppo > random"]["win_rate"] == 0.5
    assert by_lineup["ppo > human > human"]["draws"] == 1
    assert "ppo > ppo > random" not in by_lineup


def test_summarize_ppo_human_rows_applies_min_games_to_lineup_rows_only():
    rows = [
        {"lineup_signature": "human > ppo > random", "ppo_result": "win"},
        {"lineup_signature": "ppo > human > random", "ppo_result": "loss"},
    ]

    summary = summarize_ppo_human_rows(rows, min_games=2)

    assert summary == [
        {
            "lineup_signature": "overall",
            "games": 2,
            "ppo_wins": 1,
            "ppo_losses": 1,
            "draws": 0,
            "win_rate": 0.5,
        }
    ]


def test_summarize_requested_matchups_groups_target_compositions_only():
    rows = [
        {"lineup_signature": "human > ppo > action_value", "ppo_result": "win"},
        {"lineup_signature": "action_value > human > ppo", "ppo_result": "loss"},
        {"lineup_signature": "ppo > human > ppo", "ppo_result": "draw"},
        {"lineup_signature": "human > ppo > ppo", "ppo_result": "win"},
        {"lineup_signature": "human > ppo > random", "ppo_result": "win"},
    ]

    summary = summarize_requested_matchups(rows)

    assert summary == [
        {
            "lineup_signature": "human + ppo + action_value",
            "games": 2,
            "ppo_wins": 1,
            "ppo_losses": 1,
            "draws": 0,
            "win_rate": 0.5,
        },
        {
            "lineup_signature": "human + ppo + ppo",
            "games": 2,
            "ppo_wins": 1,
            "ppo_losses": 0,
            "draws": 1,
            "win_rate": 0.5,
        },
    ]


def test_summarize_requested_matchups_keeps_zero_rows_for_requested_buckets():
    summary = summarize_requested_matchups([])

    assert summary == [
        {
            "lineup_signature": "human + ppo + action_value",
            "games": 0,
            "ppo_wins": 0,
            "ppo_losses": 0,
            "draws": 0,
            "win_rate": 0.0,
        },
        {
            "lineup_signature": "human + ppo + ppo",
            "games": 0,
            "ppo_wins": 0,
            "ppo_losses": 0,
            "draws": 0,
            "win_rate": 0.0,
        },
    ]


def test_render_svg_chart_contains_expected_labels_and_escapes_text():
    summary = [
        {
            "lineup_signature": "overall",
            "games": 3,
            "ppo_wins": 2,
            "ppo_losses": 1,
            "draws": 0,
            "win_rate": 0.6667,
        },
        {
            "lineup_signature": "human & ppo > random",
            "games": 1,
            "ppo_wins": 1,
            "ppo_losses": 0,
            "draws": 0,
            "win_rate": 1.0,
        },
    ]

    svg = render_svg_chart(summary, title="PPO & Human Win Rate")

    assert svg.startswith("<svg")
    assert "PPO &amp; Human Win Rate" in svg
    assert "human &amp; ppo &gt; random" in svg
    assert "66.7%" in svg
    assert "100.0%" in svg
