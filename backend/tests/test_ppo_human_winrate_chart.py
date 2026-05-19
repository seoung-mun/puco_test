from __future__ import annotations

from scripts.visualize_ppo_human_winrate import (
    render_rank_bar_chart,
    summarize_requested_matchups,
)


EMPTY_MATCHUP_TEMPLATE = {
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


def test_summarize_requested_matchups_groups_target_compositions_only():
    rows = [
        {"lineup_signature": "human > ppo > action_value", "best_ppo_rank": 1},
        {"lineup_signature": "action_value > human > ppo", "best_ppo_rank": 2},
        {"lineup_signature": "ppo > human > ppo", "best_ppo_rank": None},
        {"lineup_signature": "human > ppo > ppo", "best_ppo_rank": 1},
        {"lineup_signature": "human > ppo > random", "best_ppo_rank": 1},
    ]

    summary = summarize_requested_matchups(rows)

    assert summary == [
        {
            "lineup_signature": "human + ppo + action_value",
            "games": 2,
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
        {"lineup_signature": "human + ppo + action_value", **EMPTY_MATCHUP_TEMPLATE},
        {"lineup_signature": "human + ppo + ppo", **EMPTY_MATCHUP_TEMPLATE},
    ]


def test_summarize_requested_matchups_ignores_outcome_field():
    rows = [
        {"lineup_signature": "human > ppo > action_value", "best_ppo_rank": 3, "ppo_result": "loss"},
        {"lineup_signature": "human > ppo > action_value", "best_ppo_rank": 1, "ppo_result": "win"},
    ]

    summary = summarize_requested_matchups(rows)

    action_value = summary[0]
    assert action_value["games"] == 2
    assert action_value["rank_games"] == 2
    assert action_value["first_place_rate"] == 0.5
    assert action_value["third_place_rate"] == 0.5
    assert "ppo_wins" not in action_value
    assert "win_rate" not in action_value


def test_render_rank_bar_chart_contains_axis_and_percentages():
    stats = {
        "lineup_signature": "human + ppo + action_value",
        "games": 10,
        "first_place_games": 3,
        "second_place_games": 5,
        "third_place_games": 2,
        "rank_games": 10,
        "unknown_rank_games": 0,
        "first_place_rate": 0.3,
        "second_place_rate": 0.5,
        "third_place_rate": 0.2,
    }

    svg = render_rank_bar_chart(stats, title="사람 + PPO + action_value")

    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "사람 + PPO + action_value" in svg
    assert "PPO 순위 분포" in svg
    assert "1등" in svg and "2등" in svg and "3등" in svg
    assert "0%" in svg and "100%" in svg
    assert "30.0%" in svg
    assert "50.0%" in svg
    assert "20.0%" in svg
    assert "fill=\"#4F6F9B\"" in svg
    assert "fill=\"#3F8E7C\"" in svg
    assert "fill=\"#7FB28F\"" in svg


def test_render_rank_bar_chart_shows_fallback_when_no_rank_data():
    stats = {
        "lineup_signature": "human + ppo + ppo",
        "games": 4,
        "first_place_games": 0,
        "second_place_games": 0,
        "third_place_games": 0,
        "rank_games": 0,
        "unknown_rank_games": 4,
        "first_place_rate": None,
        "second_place_rate": None,
        "third_place_rate": None,
    }

    svg = render_rank_bar_chart(stats)

    assert "순위 집계 데이터 없음" in svg
    assert "fill=\"#4F6F9B\"" not in svg
    assert "fill=\"#3F8E7C\"" not in svg


def test_render_rank_bar_chart_escapes_title():
    stats = {
        "lineup_signature": "human + ppo + ppo",
        "games": 1,
        "first_place_games": 1,
        "second_place_games": 0,
        "third_place_games": 0,
        "rank_games": 1,
        "unknown_rank_games": 0,
        "first_place_rate": 1.0,
        "second_place_rate": 0.0,
        "third_place_rate": 0.0,
    }

    svg = render_rank_bar_chart(stats, title="PPO <human> & friends")

    assert "PPO &lt;human&gt; &amp; friends" in svg
