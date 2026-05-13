"""
Tests for backend/app/services/analytics/queries.py

Run inside Docker:
    docker compose run --rm backend pytest backend/tests/test_analytics_service.py -v
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from app.db.models import GameSession, User
from app.services.analytics import (
    get_user_games,
    win_rate_by_bot_type,
    win_rate_by_game_count,
    list_users,
    recent_games,
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
        """If a game has BOT_ppo and BOT_ppo_2, ppo should only count as 1 game."""
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
