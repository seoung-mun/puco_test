"""
Tests for backend/app/services/analytics/queries.py

Run inside Docker:
    docker compose run --rm backend pytest backend/tests/test_analytics_service.py -v
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from app.db.models import GameSession, Replay, User
from app.services.analytics import (
    get_user_games,
    lineup_summary,
    win_rate_by_bot_type,
    win_rate_by_game_count,
    list_users,
    recent_games,
    resolve_user_id_or_nickname,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(db, nickname="Player") -> User:
    u = User(
        id=uuid.uuid4(),
        google_id=f"gid_{uuid.uuid4().hex}",
        nickname=f"{nickname}_{uuid.uuid4().hex[:4]}",
    )
    db.add(u)
    return u


def make_game(
    db,
    players: list[str],
    status: str = "FINISHED",
    winner_id: str | None = None,
    created_at: datetime | None = None,
) -> GameSession:
    g = GameSession(
        id=uuid.uuid4(),
        title=f"Game_{uuid.uuid4().hex[:6]}",
        status=status,
        num_players=len(players),
        players=players,
        winner_id=winner_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(g)
    return g


def make_replay(
    db,
    game_id,
    *,
    final_scores: list[dict],
) -> Replay:
    replay = Replay(
        game_id=game_id,
        payload={
            "format": "backend-replay.v2",
            "game_id": str(game_id),
            "entries": [],
            "final_scores": final_scores,
        },
    )
    db.add(replay)
    return replay


def _base_ts(offset_seconds: int = 0) -> datetime:
    """Return a deterministic UTC timestamp offset from a fixed point."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(seconds=offset_seconds)


# ===========================================================================
# get_user_games
# ===========================================================================

class TestGetUserGames:
    def test_returns_only_finished_games(self, db):
        user = make_user(db)
        uid = str(user.id)
        finished = make_game(db, [uid, "BOT_ppo"], status="FINISHED")
        make_game(db, [uid, "BOT_ppo"], status="PROGRESS")
        make_game(db, [uid, "BOT_ppo"], status="WAITING")
        db.flush()

        result = get_user_games(db, uid)
        assert len(result) == 1
        assert result[0].id == finished.id

    def test_returns_only_games_user_participated_in(self, db):
        user1 = make_user(db, "P1")
        user2 = make_user(db, "P2")
        uid1, uid2 = str(user1.id), str(user2.id)
        g1 = make_game(db, [uid1, "BOT_ppo"], status="FINISHED")
        make_game(db, [uid2, "BOT_random"], status="FINISHED")
        db.flush()

        result = get_user_games(db, uid1)
        assert len(result) == 1
        assert result[0].id == g1.id

    def test_ordered_by_created_at_asc(self, db):
        user = make_user(db)
        uid = str(user.id)
        g1 = make_game(db, [uid, "BOT_ppo"], created_at=_base_ts(100))
        g2 = make_game(db, [uid, "BOT_ppo"], created_at=_base_ts(200))
        g3 = make_game(db, [uid, "BOT_ppo"], created_at=_base_ts(50))
        db.flush()

        result = get_user_games(db, uid)
        assert [g.id for g in result] == [g3.id, g1.id, g2.id]

    def test_no_games_returns_empty_list(self, db):
        user = make_user(db)
        db.flush()
        result = get_user_games(db, str(user.id))
        assert result == []

    def test_excludes_games_with_only_bots(self, db):
        user = make_user(db)
        uid = str(user.id)
        # game without user
        make_game(db, ["BOT_ppo", "BOT_random"], status="FINISHED")
        db.flush()

        result = get_user_games(db, uid)
        assert result == []


# ===========================================================================
# win_rate_by_bot_type
# ===========================================================================

class TestWinRateByBotType:
    def test_win_counted_correctly(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=uid)   # win vs ppo
        make_game(db, [uid, "BOT_ppo"], winner_id=None)  # draw vs ppo
        db.flush()

        result = win_rate_by_bot_type(db, uid)
        assert len(result) == 1
        ppo = result[0]
        assert ppo["bot_type"] == "ppo"
        assert ppo["games"] == 2
        assert ppo["wins"] == 1
        assert ppo["win_rate"] == 0.5

    def test_ppo_vs_random_split(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=uid)        # ppo: win
        make_game(db, [uid, "BOT_random"], winner_id=uid)     # random: win
        make_game(db, [uid, "BOT_random"], winner_id=None)    # random: draw
        db.flush()

        result = win_rate_by_bot_type(db, uid)
        by_type = {r["bot_type"]: r for r in result}
        assert "ppo" in by_type
        assert "random" in by_type
        assert by_type["ppo"]["games"] == 1
        assert by_type["ppo"]["wins"] == 1
        assert by_type["random"]["games"] == 2
        assert by_type["random"]["wins"] == 1

    def test_sorted_by_games_desc(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=uid)
        make_game(db, [uid, "BOT_random"], winner_id=uid)
        make_game(db, [uid, "BOT_random"], winner_id=uid)
        db.flush()

        result = win_rate_by_bot_type(db, uid)
        assert result[0]["bot_type"] == "random"  # 2 games
        assert result[1]["bot_type"] == "ppo"     # 1 game

    def test_same_bot_type_multiple_bots_counted_once_per_game(self, db):
        """같은 게임에 같은 bot_type 이 두 번 나와도 게임 수는 1로 카운트."""
        user = make_user(db)
        uid = str(user.id)
        # Two bots of same type in one game
        make_game(db, [uid, "BOT_ppo", "BOT_ppo"], winner_id=uid)
        db.flush()

        result = win_rate_by_bot_type(db, uid)
        ppo = next(r for r in result if r["bot_type"] == "ppo")
        assert ppo["games"] == 1

    def test_no_games_returns_empty(self, db):
        user = make_user(db)
        db.flush()
        assert win_rate_by_bot_type(db, str(user.id)) == []

    def test_all_draws_win_rate_zero(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=None)
        make_game(db, [uid, "BOT_ppo"], winner_id=None)
        db.flush()

        result = win_rate_by_bot_type(db, uid)
        assert result[0]["wins"] == 0
        assert result[0]["win_rate"] == 0.0

    def test_null_winner_id_not_counted_as_win(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=None)
        db.flush()

        result = win_rate_by_bot_type(db, uid)
        assert result[0]["wins"] == 0


# ===========================================================================
# win_rate_by_game_count
# ===========================================================================

class TestWinRateByGameCount:
    def _make_games(self, db, uid: str, results: list[str | None]) -> None:
        """results: list of winner_id or None (draw). Creates in order."""
        for i, w in enumerate(results):
            make_game(db, [uid, "BOT_ppo"], winner_id=w, created_at=_base_ts(i))
        db.flush()

    def test_exactly_5_games(self, db):
        user = make_user(db)
        uid = str(user.id)
        # win, win, loss, loss, win → 3 wins
        self._make_games(db, uid, [uid, uid, None, None, uid])

        result = win_rate_by_game_count(db, uid, bucket=5)
        assert len(result) == 1
        r = result[0]
        assert r["game_range"] == "1-5"
        assert r["games"] == 5
        assert r["cumulative_wins"] == 3
        assert r["win_rate"] == pytest.approx(0.6)

    def test_fewer_than_bucket_always_included(self, db):
        user = make_user(db)
        uid = str(user.id)
        self._make_games(db, uid, [uid, uid])  # 2 games, bucket=5

        result = win_rate_by_game_count(db, uid, bucket=5)
        assert len(result) == 1
        r = result[0]
        assert r["game_range"] == "1-2"
        assert r["games"] == 2
        assert r["cumulative_wins"] == 2

    def test_more_than_bucket_includes_last(self, db):
        user = make_user(db)
        uid = str(user.id)
        # 7 games: bucket=5 → emit at 5, then at 7 (last)
        self._make_games(db, uid, [uid, uid, uid, uid, uid, None, uid])

        result = win_rate_by_game_count(db, uid, bucket=5)
        assert len(result) == 2
        assert result[0]["game_range"] == "1-5"
        assert result[0]["cumulative_wins"] == 5
        assert result[1]["game_range"] == "6-7"
        assert result[1]["games"] == 7
        assert result[1]["cumulative_wins"] == 6

    def test_exactly_10_games(self, db):
        user = make_user(db)
        uid = str(user.id)
        # 10 games, all wins → 2 buckets, no trailing
        self._make_games(db, uid, [uid] * 10)

        result = win_rate_by_game_count(db, uid, bucket=5)
        assert len(result) == 2
        assert result[0]["game_range"] == "1-5"
        assert result[1]["game_range"] == "6-10"

    def test_no_games_returns_empty(self, db):
        user = make_user(db)
        db.flush()
        assert win_rate_by_game_count(db, str(user.id)) == []

    def test_raises_on_zero_bucket(self, db):
        """bucket=0 은 ValueError"""
        user = make_user(db, "P")
        db.flush()
        with pytest.raises(ValueError, match="positive integer"):
            win_rate_by_game_count(db, str(user.id), bucket=0)

    def test_raises_on_negative_bucket(self, db):
        """bucket=-1 은 ValueError"""
        user = make_user(db, "P2")
        db.flush()
        with pytest.raises(ValueError, match="positive integer"):
            win_rate_by_game_count(db, str(user.id), bucket=-1)

    def test_single_game_always_included(self, db):
        user = make_user(db)
        uid = str(user.id)
        self._make_games(db, uid, [uid])

        result = win_rate_by_game_count(db, uid, bucket=5)
        assert len(result) == 1
        assert result[0]["games"] == 1
        assert result[0]["cumulative_wins"] == 1


# ===========================================================================
# list_users
# ===========================================================================

class TestListUsers:
    def test_returns_users_sorted_by_game_count_desc(self, db):
        u1 = make_user(db, "Active")
        u2 = make_user(db, "Inactive")
        uid1, uid2 = str(u1.id), str(u2.id)
        # u1 has 2 games, u2 has 0
        make_game(db, [uid1, "BOT_ppo"])
        make_game(db, [uid1, "BOT_random"])
        db.flush()

        # Use a large limit to capture all rows; then filter to our two test users
        result = list_users(db, limit=1000)
        ids = [r["user_id"] for r in result]
        # Both users must appear in results
        assert uid1 in ids
        assert uid2 in ids
        # User with games must rank above user with no games
        assert ids.index(uid1) < ids.index(uid2)

    def test_includes_users_with_no_games(self, db):
        user = make_user(db, "NoGames")
        db.flush()

        result = list_users(db, limit=100)
        user_ids = [r["user_id"] for r in result]
        assert str(user.id) in user_ids

    def test_users_total_games_uses_jsonb_not_column(self, db):
        """The users.total_games column is always 0; our aggregation must be correct."""
        user = make_user(db, "Tester")
        uid = str(user.id)
        # Column stays 0, but we have 3 FINISHED games
        make_game(db, [uid, "BOT_ppo"])
        make_game(db, [uid, "BOT_ppo"])
        make_game(db, [uid, "BOT_random"])
        db.flush()

        result = list_users(db, limit=10)
        row = next(r for r in result if r["user_id"] == uid)
        # users.total_games column would return 0; our query must return 3
        assert row["total_games"] == 3

    def test_only_finished_games_counted(self, db):
        user = make_user(db, "Mixed")
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], status="FINISHED")
        make_game(db, [uid, "BOT_ppo"], status="PROGRESS")
        db.flush()

        result = list_users(db, limit=10)
        row = next(r for r in result if r["user_id"] == uid)
        assert row["total_games"] == 1

    def test_limit_respected(self, db):
        for i in range(5):
            make_user(db, f"U{i}")
        db.flush()

        result = list_users(db, limit=3)
        assert len(result) <= 3

    def test_last_game_at_populated(self, db):
        user = make_user(db, "WithGames")
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], created_at=_base_ts(100))
        make_game(db, [uid, "BOT_ppo"], created_at=_base_ts(500))
        db.flush()

        result = list_users(db, limit=10)
        row = next(r for r in result if r["user_id"] == uid)
        assert row["last_game_at"] is not None

    def test_last_game_at_none_for_user_with_no_games(self, db):
        user = make_user(db, "NoGames2")
        db.flush()

        result = list_users(db, limit=100)
        row = next(r for r in result if r["user_id"] == str(user.id))
        assert row["last_game_at"] is None


# ===========================================================================
# recent_games
# ===========================================================================

class TestRecentGames:
    def test_win_result(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=uid)
        db.flush()

        result = recent_games(db, uid)
        assert len(result) == 1
        assert result[0]["result"] == "win"

    def test_loss_result(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], winner_id="BOT_ppo")
        db.flush()

        result = recent_games(db, uid)
        assert result[0]["result"] == "loss"

    def test_draw_result_on_null_winner(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=None)
        db.flush()

        result = recent_games(db, uid)
        assert result[0]["result"] == "draw"

    def test_ordered_newest_first(self, db):
        user = make_user(db)
        uid = str(user.id)
        g1 = make_game(db, [uid, "BOT_ppo"], created_at=_base_ts(100))
        g2 = make_game(db, [uid, "BOT_ppo"], created_at=_base_ts(300))
        g3 = make_game(db, [uid, "BOT_ppo"], created_at=_base_ts(200))
        db.flush()

        result = recent_games(db, uid)
        assert [r["game_id"] for r in result] == [
            str(g2.id), str(g3.id), str(g1.id)
        ]

    def test_opponent_bots_identified(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo", "BOT_random"])
        db.flush()

        result = recent_games(db, uid)
        bots = set(result[0]["opponent_bots"])
        assert "ppo" in bots
        assert "random" in bots

    def test_no_games_returns_empty(self, db):
        user = make_user(db)
        db.flush()
        assert recent_games(db, str(user.id)) == []

    def test_limit_respected(self, db):
        user = make_user(db)
        uid = str(user.id)
        for i in range(5):
            make_game(db, [uid, "BOT_ppo"], created_at=_base_ts(i))
        db.flush()

        result = recent_games(db, uid, limit=3)
        assert len(result) == 3

    def test_only_finished_games_returned(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], status="FINISHED")
        make_game(db, [uid, "BOT_ppo"], status="PROGRESS")
        db.flush()

        result = recent_games(db, uid)
        assert len(result) == 1

    def test_winner_id_present_in_result(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=uid)
        db.flush()

        result = recent_games(db, uid)
        assert result[0]["winner_id"] == uid

    def test_game_only_with_bots_excluded(self, db):
        user = make_user(db)
        uid = str(user.id)
        make_game(db, ["BOT_ppo", "BOT_random"])
        db.flush()

        result = recent_games(db, uid)
        assert result == []

    def test_enriches_three_player_recent_games_with_scores_and_ordered_lineup(self, db):
        user = make_user(db, "Alice")
        other = make_user(db, "Bob")
        uid = str(user.id)
        other_id = str(other.id)
        game = make_game(
            db,
            [uid, "BOT_ppo", other_id],
            winner_id=uid,
            created_at=_base_ts(300),
        )
        make_replay(
            db,
            game.id,
            final_scores=[
                {"actor_id": uid, "display_name": user.nickname, "vp": 35, "tiebreaker": 3, "winner": True},
                {"actor_id": other_id, "display_name": other.nickname, "vp": 31, "tiebreaker": 2, "winner": False},
                {"actor_id": "BOT_ppo", "display_name": "ppo", "vp": 27, "tiebreaker": 1, "winner": False},
            ],
        )
        db.flush()

        result = recent_games(db, uid)
        assert result[0]["ordered_players"] == [user.nickname, "ppo", other.nickname]
        assert result[0]["my_seat"] == 1
        assert result[0]["my_rank"] == 1
        assert result[0]["winner_display_name"] == user.nickname
        assert result[0]["my_vp"] == 35
        assert result[0]["benchmark_vp"] == 31
        assert result[0]["vp_gap"] == 4
        assert result[0]["score_data_available"] is True

    def test_recent_games_keeps_rows_when_replay_scores_missing(self, db):
        user = make_user(db, "Alice")
        other = make_user(db, "Bob")
        uid = str(user.id)
        game = make_game(
            db,
            [str(other.id), uid, "BOT_action_value"],
            winner_id=str(other.id),
            created_at=_base_ts(301),
        )
        db.flush()

        result = recent_games(db, uid)
        assert result[0]["game_id"] == str(game.id)
        assert result[0]["ordered_players"] == [other.nickname, user.nickname, "action_value"]
        assert result[0]["my_seat"] == 2
        assert result[0]["winner_display_name"] == other.nickname
        assert result[0]["score_data_available"] is False
        assert result[0]["my_rank"] is None
        assert result[0]["my_vp"] is None
        assert result[0]["benchmark_vp"] is None
        assert result[0]["vp_gap"] is None

    def test_recent_game_enrichment_stays_scoped_to_three_player_games(self, db):
        user = make_user(db, "Alice")
        uid = str(user.id)
        game = make_game(
            db,
            [uid, "BOT_ppo"],
            winner_id=uid,
            created_at=_base_ts(302),
        )
        make_replay(
            db,
            game.id,
            final_scores=[
                {"actor_id": uid, "display_name": user.nickname, "vp": 33, "tiebreaker": 2, "winner": True},
                {"actor_id": "BOT_ppo", "display_name": "PPO Bot", "vp": 25, "tiebreaker": 1, "winner": False},
            ],
        )
        db.flush()

        result = recent_games(db, uid)
        assert "ordered_players" not in result[0]
        assert "my_seat" not in result[0]
        assert "score_data_available" not in result[0]

    def test_recent_games_prefers_replay_display_names_when_scores_exist(self, db):
        user = make_user(db, "Alice")
        other = make_user(db, "Bob")
        uid = str(user.id)
        other_id = str(other.id)
        game = make_game(
            db,
            [uid, "BOT_ppo", other_id],
            winner_id="BOT_ppo",
            created_at=_base_ts(303),
        )
        make_replay(
            db,
            game.id,
            final_scores=[
                {"actor_id": "BOT_ppo", "display_name": "PPO Bot", "vp": 37, "tiebreaker": 4, "winner": True},
                {"actor_id": uid, "display_name": user.nickname, "vp": 31, "tiebreaker": 3, "winner": False},
                {"actor_id": other_id, "display_name": other.nickname, "vp": 28, "tiebreaker": 2, "winner": False},
            ],
        )
        db.flush()

        result = recent_games(db, uid)
        assert result[0]["ordered_players"] == [user.nickname, "PPO Bot", other.nickname]
        assert result[0]["winner_display_name"] == "PPO Bot"


class TestLineupSummary:
    def test_groups_only_finished_three_player_games_and_preserves_order(self, db):
        user = make_user(db, "Alice")
        other = make_user(db, "Bob")
        uid = str(user.id)
        other_id = str(other.id)

        g1 = make_game(db, [uid, other_id, "BOT_ppo"], winner_id=uid, created_at=_base_ts(10))
        g2 = make_game(db, [uid, other_id, "BOT_ppo"], winner_id=other_id, created_at=_base_ts(20))
        g3 = make_game(db, [other_id, uid, "BOT_ppo"], winner_id=uid, created_at=_base_ts(30))
        make_game(db, [uid, other_id, "BOT_ppo", "BOT_random"], winner_id=uid, created_at=_base_ts(40))
        make_game(db, [uid, other_id, "BOT_ppo"], status="PROGRESS", winner_id=uid, created_at=_base_ts(50))

        for game in (g1, g2, g3):
            make_replay(
                db,
                game.id,
                final_scores=[
                    {"actor_id": uid, "display_name": user.nickname, "vp": 35, "tiebreaker": 3, "winner": game.winner_id == uid},
                    {"actor_id": other_id, "display_name": other.nickname, "vp": 31, "tiebreaker": 2, "winner": game.winner_id == other_id},
                    {"actor_id": "BOT_ppo", "display_name": "ppo", "vp": 27, "tiebreaker": 1, "winner": False},
                ],
            )
        db.flush()

        result = lineup_summary(db, uid)
        assert len(result) == 2
        first = result[0]
        second = result[1]
        assert first["ordered_players"] == [user.nickname, other.nickname, "ppo"]
        assert first["games"] == 2
        assert first["my_seat"] == 1
        assert second["ordered_players"] == [other.nickname, user.nickname, "ppo"]
        assert second["games"] == 1
        assert second["my_seat"] == 2

    def test_uses_nicknames_and_bot_display_names_in_lineup_rows(self, db):
        user = make_user(db, "Alice")
        other = make_user(db, "Carol")
        uid = str(user.id)
        game = make_game(db, [uid, str(other.id), "BOT_action_value"], winner_id=uid, created_at=_base_ts(60))
        make_replay(
            db,
            game.id,
            final_scores=[
                {"actor_id": uid, "display_name": user.nickname, "vp": 34, "tiebreaker": 3, "winner": True},
                {"actor_id": str(other.id), "display_name": other.nickname, "vp": 30, "tiebreaker": 2, "winner": False},
                {"actor_id": "BOT_action_value", "display_name": "action_value", "vp": 28, "tiebreaker": 1, "winner": False},
            ],
        )
        db.flush()

        result = lineup_summary(db, uid)
        assert result[0]["lineup"] == f"{user.nickname} > {other.nickname} > action_value"
        assert result[0]["ordered_players"] == [user.nickname, other.nickname, "action_value"]

    def test_uses_one_based_seat_and_averages_vp_gap_when_scores_exist(self, db):
        user = make_user(db, "Alice")
        other = make_user(db, "Bob")
        uid = str(user.id)
        other_id = str(other.id)
        first = make_game(db, [uid, other_id, "BOT_ppo"], winner_id=uid, created_at=_base_ts(100))
        second = make_game(db, [uid, other_id, "BOT_ppo"], winner_id=other_id, created_at=_base_ts(200))
        make_replay(
            db,
            first.id,
            final_scores=[
                {"actor_id": uid, "display_name": user.nickname, "vp": 36, "tiebreaker": 3, "winner": True},
                {"actor_id": other_id, "display_name": other.nickname, "vp": 32, "tiebreaker": 2, "winner": False},
                {"actor_id": "BOT_ppo", "display_name": "ppo", "vp": 25, "tiebreaker": 1, "winner": False},
            ],
        )
        make_replay(
            db,
            second.id,
            final_scores=[
                {"actor_id": other_id, "display_name": other.nickname, "vp": 38, "tiebreaker": 4, "winner": True},
                {"actor_id": uid, "display_name": user.nickname, "vp": 33, "tiebreaker": 3, "winner": False},
                {"actor_id": "BOT_ppo", "display_name": "ppo", "vp": 20, "tiebreaker": 1, "winner": False},
            ],
        )
        db.flush()

        result = lineup_summary(db, uid)
        row = result[0]
        assert row["my_seat"] == 1
        assert row["wins"] == 1
        assert row["losses"] == 1
        assert row["draws"] == 0
        assert row["vp_gap_games"] == 2
        assert row["avg_vp_gap"] == pytest.approx(4.5)

    def test_skips_missing_replay_scores_from_vp_gap_average(self, db):
        user = make_user(db, "Alice")
        other = make_user(db, "Bob")
        uid = str(user.id)
        other_id = str(other.id)

        with_scores = make_game(db, [uid, other_id, "BOT_ppo"], winner_id=uid, created_at=_base_ts(110))
        without_scores = make_game(db, [uid, other_id, "BOT_ppo"], winner_id=uid, created_at=_base_ts(120))
        make_replay(
            db,
            with_scores.id,
            final_scores=[
                {"actor_id": uid, "display_name": user.nickname, "vp": 33, "tiebreaker": 3, "winner": True},
                {"actor_id": other_id, "display_name": other.nickname, "vp": 31, "tiebreaker": 2, "winner": False},
                {"actor_id": "BOT_ppo", "display_name": "ppo", "vp": 20, "tiebreaker": 1, "winner": False},
            ],
        )
        db.flush()

        result = lineup_summary(db, uid)
        row = result[0]
        assert row["games"] == 2
        assert row["vp_gap_games"] == 1
        assert row["avg_vp_gap"] == pytest.approx(2.0)

    def test_groups_lineups_by_stable_player_order_not_replay_display_name_drift(self, db):
        user = make_user(db, "Alice")
        other = make_user(db, "Bob")
        uid = str(user.id)
        other_id = str(other.id)

        first = make_game(db, [uid, other_id, "BOT_ppo"], winner_id=uid, created_at=_base_ts(130))
        second = make_game(db, [uid, other_id, "BOT_ppo"], winner_id=other_id, created_at=_base_ts(140))
        make_replay(
            db,
            first.id,
            final_scores=[
                {"actor_id": uid, "display_name": "Alice-old", "vp": 35, "tiebreaker": 3, "winner": True},
                {"actor_id": other_id, "display_name": "Bob-old", "vp": 31, "tiebreaker": 2, "winner": False},
                {"actor_id": "BOT_ppo", "display_name": "PPO Bot", "vp": 28, "tiebreaker": 1, "winner": False},
            ],
        )
        make_replay(
            db,
            second.id,
            final_scores=[
                {"actor_id": other_id, "display_name": "Bob-new", "vp": 36, "tiebreaker": 4, "winner": True},
                {"actor_id": uid, "display_name": "Alice-new", "vp": 33, "tiebreaker": 3, "winner": False},
                {"actor_id": "BOT_ppo", "display_name": "PPO Bot v2", "vp": 27, "tiebreaker": 1, "winner": False},
            ],
        )
        db.flush()

        result = lineup_summary(db, uid)
        assert len(result) == 1
        assert result[0]["games"] == 2
        assert result[0]["ordered_players"] == [user.nickname, other.nickname, "ppo"]


class TestResolveUserIdOrNickname:
    def test_resolves_user_id_and_unique_nickname_to_user_id(self, db):
        user = make_user(db, "LookupNick")
        db.flush()

        assert resolve_user_id_or_nickname(db, user_id=str(user.id)) == str(user.id)
        resolved = resolve_user_id_or_nickname(db, nickname=user.nickname)
        assert resolved == str(user.id)
