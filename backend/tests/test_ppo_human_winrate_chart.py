from __future__ import annotations

from scripts.visualize_ppo_human_winrate import (
    build_report_summary,
    render_svg_chart,
    summarize_ppo_human_rows,
    summarize_requested_matchups,
)


def test_summarize_ppo_human_rows_groups_overall_and_excludes_bot_only():
    rows = [
        {"lineup_signature": "human > ppo > random", "ppo_result": "win", "best_ppo_rank": 1},
        {"lineup_signature": "human > ppo > random", "ppo_result": "loss", "best_ppo_rank": 2},
        {"lineup_signature": "ppo > human > human", "ppo_result": "draw", "best_ppo_rank": None},
        {"lineup_signature": "ppo > ppo > random", "ppo_result": "win", "best_ppo_rank": 1},
    ]

    summary = summarize_ppo_human_rows(rows)

    assert summary[0] == {
        "lineup_signature": "overall",
        "games": 3,
        "ppo_wins": 1,
        "ppo_losses": 1,
        "draws": 1,
        "win_rate": 0.3333,
        "first_place_games": 1,
        "second_place_games": 1,
        "third_place_games": 0,
        "rank_games": 2,
        "unknown_rank_games": 1,
        "first_place_rate": 0.5,
        "second_place_rate": 0.5,
        "third_place_rate": 0.0,
    }
    by_lineup = {row["lineup_signature"]: row for row in summary[1:]}
    assert by_lineup["human > ppo > random"]["games"] == 2
    assert by_lineup["human > ppo > random"]["win_rate"] == 0.5
    assert by_lineup["human > ppo > random"]["first_place_rate"] == 0.5
    assert by_lineup["human > ppo > random"]["second_place_rate"] == 0.5
    assert by_lineup["ppo > human > human"]["draws"] == 1
    assert by_lineup["ppo > human > human"]["rank_games"] == 0
    assert by_lineup["ppo > human > human"]["first_place_rate"] is None
    assert "ppo > ppo > random" not in by_lineup


def test_summarize_ppo_human_rows_applies_min_games_to_lineup_rows_only():
    rows = [
        {"lineup_signature": "human > ppo > random", "ppo_result": "win", "best_ppo_rank": 1},
        {"lineup_signature": "ppo > human > random", "ppo_result": "loss", "best_ppo_rank": 2},
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
            "first_place_games": 1,
            "second_place_games": 1,
            "third_place_games": 0,
            "rank_games": 2,
            "unknown_rank_games": 0,
            "first_place_rate": 0.5,
            "second_place_rate": 0.5,
            "third_place_rate": 0.0,
        }
    ]


def test_summarize_requested_matchups_groups_target_compositions_only():
    rows = [
        {"lineup_signature": "human > ppo > action_value", "ppo_result": "win", "best_ppo_rank": 1},
        {"lineup_signature": "action_value > human > ppo", "ppo_result": "loss", "best_ppo_rank": 2},
        {"lineup_signature": "ppo > human > ppo", "ppo_result": "draw", "best_ppo_rank": None},
        {"lineup_signature": "human > ppo > ppo", "ppo_result": "win", "best_ppo_rank": 1},
        {"lineup_signature": "human > ppo > random", "ppo_result": "win", "best_ppo_rank": 1},
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
            "first_place_games": 1,
            "second_place_games": 1,
            "third_place_games": 0,
            "rank_games": 2,
            "unknown_rank_games": 0,
            "first_place_rate": 0.5,
            "second_place_rate": 0.5,
            "third_place_rate": 0.0,
        },
        {
            "lineup_signature": "human + ppo + ppo",
            "games": 2,
            "ppo_wins": 1,
            "ppo_losses": 0,
            "draws": 1,
            "win_rate": 0.5,
            "first_place_games": 1,
            "second_place_games": 0,
            "third_place_games": 0,
            "rank_games": 1,
            "unknown_rank_games": 1,
            "first_place_rate": 1.0,
            "second_place_rate": 0.0,
            "third_place_rate": 0.0,
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
            "first_place_games": 0,
            "second_place_games": 0,
            "third_place_games": 0,
            "rank_games": 0,
            "unknown_rank_games": 0,
            "first_place_rate": None,
            "second_place_rate": None,
            "third_place_rate": None,
        },
        {
            "lineup_signature": "human + ppo + ppo",
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
        },
    ]


def test_build_report_summary_uses_target_matchups_by_default():
    rows = [
        {"lineup_signature": "human > ppo > action_value", "ppo_result": "win", "best_ppo_rank": 1},
        {"lineup_signature": "ppo > human > action_value", "ppo_result": "loss", "best_ppo_rank": 2},
        {"lineup_signature": "human > ppo > ppo", "ppo_result": "win", "best_ppo_rank": 1},
        {"lineup_signature": "human > ppo > random", "ppo_result": "win", "best_ppo_rank": 1},
    ]

    summary = build_report_summary(rows, all_lineups=False, min_games=99)

    assert summary == [
        {
            "lineup_signature": "human + ppo + action_value",
            "games": 2,
            "ppo_wins": 1,
            "ppo_losses": 1,
            "draws": 0,
            "win_rate": 0.5,
            "first_place_games": 1,
            "second_place_games": 1,
            "third_place_games": 0,
            "rank_games": 2,
            "unknown_rank_games": 0,
            "first_place_rate": 0.5,
            "second_place_rate": 0.5,
            "third_place_rate": 0.0,
        },
        {
            "lineup_signature": "human + ppo + ppo",
            "games": 1,
            "ppo_wins": 1,
            "ppo_losses": 0,
            "draws": 0,
            "win_rate": 1.0,
            "first_place_games": 1,
            "second_place_games": 0,
            "third_place_games": 0,
            "rank_games": 1,
            "unknown_rank_games": 0,
            "first_place_rate": 1.0,
            "second_place_rate": 0.0,
            "third_place_rate": 0.0,
        },
    ]


def test_build_report_summary_can_show_all_human_ppo_lineups_with_min_games():
    rows = [
        {"lineup_signature": "human > ppo > action_value", "ppo_result": "win", "best_ppo_rank": 1},
        {"lineup_signature": "ppo > human > action_value", "ppo_result": "loss", "best_ppo_rank": 2},
        {"lineup_signature": "human > ppo > ppo", "ppo_result": "win", "best_ppo_rank": 1},
        {"lineup_signature": "ppo > ppo > random", "ppo_result": "win", "best_ppo_rank": 1},
    ]

    summary = build_report_summary(rows, all_lineups=True, min_games=2)

    assert summary == [
        {
            "lineup_signature": "overall",
            "games": 3,
            "ppo_wins": 2,
            "ppo_losses": 1,
            "draws": 0,
            "win_rate": 0.6667,
            "first_place_games": 2,
            "second_place_games": 1,
            "third_place_games": 0,
            "rank_games": 3,
            "unknown_rank_games": 0,
            "first_place_rate": 0.6667,
            "second_place_rate": 0.3333,
            "third_place_rate": 0.0,
        },
    ]


def test_render_svg_chart_contains_expected_labels_and_escapes_text():
    summary = [
        {
            "lineup_signature": "human + ppo + action_value",
            "games": 6,
            "ppo_wins": 0,
            "ppo_losses": 2,
            "draws": 4,
            "win_rate": 0.0,
            "first_place_games": 0,
            "second_place_games": 1,
            "third_place_games": 1,
            "rank_games": 2,
            "unknown_rank_games": 4,
            "first_place_rate": 0.0,
            "second_place_rate": 0.5,
            "third_place_rate": 0.5,
        },
        {
            "lineup_signature": "human & ppo > random",
            "games": 1,
            "ppo_wins": 1,
            "ppo_losses": 0,
            "draws": 0,
            "win_rate": 1.0,
            "first_place_games": 1,
            "second_place_games": 0,
            "third_place_games": 0,
            "rank_games": 1,
            "unknown_rank_games": 0,
            "first_place_rate": 1.0,
            "second_place_rate": 0.0,
            "third_place_rate": 0.0,
        },
    ]

    svg = render_svg_chart(summary, title="PPO & Human Win Rate")

    assert svg.startswith("<svg")
    assert "PPO &amp; Human Win Rate" in svg
    assert "대국 조합" in svg
    assert "순위 분포" in svg
    assert "승/패/무승부 분포" in svg
    assert "사람 + PPO + action_value" in svg
    assert "사람 &amp; PPO &gt; random" in svg
    assert "전적: 총 6판, 0승 2패 4무승부" in svg
    assert "순위 집계 2판, 미집계 4판" in svg
    assert "1등 0판" in svg
    assert "2등 1판" in svg
    assert "미집계 4판" in svg
    assert "승 0판" in svg
    assert "패 2판" in svg
    assert "무 4판" in svg
    assert "100.0%" not in svg
