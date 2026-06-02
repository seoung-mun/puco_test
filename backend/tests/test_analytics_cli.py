"""
Tests for backend/scripts/analytics_cli.py

Run inside Docker:
    docker compose run --rm backend pytest backend/tests/test_analytics_cli.py -v

각 핸들러 함수를 DB fixture + argparse.Namespace 로 직접 호출해 테스트한다.
subprocess 를 사용하지 않으므로 실제 DB 트랜잭션 내에서 롤백된다.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone, timedelta
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest

# CLI 핸들러/유틸 직접 import
from scripts.analytics_cli import (
    _print_table,
    handle_list_users,
    handle_win_rate_by_bot,
    handle_win_rate_by_count,
    handle_recent_games,
    build_parser,
)
from app.db.models import GameSession, User


# ---------------------------------------------------------------------------
# Helpers (test_analytics_service.py 와 동일 패턴)
# ---------------------------------------------------------------------------

def make_user(db, nickname: str = "Player") -> User:
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


def _ns(**kwargs) -> argparse.Namespace:
    """Convenience: build an argparse.Namespace with sane defaults."""
    defaults = {"json": False, "limit": 20, "bucket": 5, "user_id": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# _print_table
# ---------------------------------------------------------------------------

class TestPrintTable:
    def test_empty_rows(self, capsys):
        _print_table([], ["a", "b"])
        out = capsys.readouterr().out
        assert "(결과 없음)" in out

    def test_headers_printed(self, capsys):
        _print_table([{"a": "x", "b": "y"}], ["a", "b"])
        out = capsys.readouterr().out
        assert "a" in out
        assert "b" in out

    def test_separator_line(self, capsys):
        _print_table([{"col": "val"}], ["col"])
        lines = capsys.readouterr().out.strip().splitlines()
        # lines: header, separator, data
        assert len(lines) == 3
        assert set(lines[1].strip()) <= {"-", " "}

    def test_values_appear(self, capsys):
        _print_table([{"x": "hello", "y": "world"}], ["x", "y"])
        out = capsys.readouterr().out
        assert "hello" in out
        assert "world" in out

    def test_missing_key_renders_empty_string(self, capsys):
        _print_table([{"a": "val"}], ["a", "b"])
        out = capsys.readouterr().out
        # Should not raise; 'b' column appears as empty string
        assert "val" in out


# ---------------------------------------------------------------------------
# handle_list_users
# ---------------------------------------------------------------------------

class TestHandleListUsers:
    def test_table_output(self, db, capsys):
        u = make_user(db, "ListUser")
        uid = str(u.id)
        make_game(db, [uid, "BOT_ppo"])
        db.flush()

        handle_list_users(_ns(), db=db)
        out = capsys.readouterr().out
        assert "user_id" in out
        assert uid in out

    def test_json_output(self, db, capsys):
        u = make_user(db, "JsonUser")
        uid = str(u.id)
        make_game(db, [uid, "BOT_random"])
        db.flush()

        handle_list_users(_ns(json=True), db=db)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        ids = [r["user_id"] for r in data]
        assert uid in ids

    def test_empty_db_shows_no_result(self, db, capsys):
        """DB에 사용자가 없어도 오류 없이 동작해야 한다."""
        handle_list_users(_ns(), db=db)
        # list_users는 항상 users 테이블을 left join 하므로 결과가 0행일 수도 있다
        # — 오류 없이 끝나는 것만 검증
        capsys.readouterr()  # consume output

    def test_limit_option(self, db, capsys):
        for i in range(5):
            make_user(db, f"LimitU{i}")
        db.flush()

        handle_list_users(_ns(limit=2), db=db)
        out = capsys.readouterr().out
        # 헤더+구분선+데이터 합계 행 수가 2+2 = 4 이하여야 함
        data_lines = [l for l in out.strip().splitlines() if l and not l.startswith("-") and "user_id" not in l]
        assert len(data_lines) <= 2

    def test_mock_list_users_called_with_db(self, db, capsys):
        """list_users 서비스 함수가 올바르게 호출되는지 mock 으로 검증."""
        with patch("scripts.analytics_cli.list_users") as mock_fn:
            mock_fn.return_value = [
                {"user_id": "aaa", "nickname": "Alice", "total_games": 5, "last_game_at": None}
            ]
            handle_list_users(_ns(), db=db)
            mock_fn.assert_called_once_with(db, limit=20)

        out = capsys.readouterr().out
        assert "aaa" in out
        assert "Alice" in out


# ---------------------------------------------------------------------------
# handle_win_rate_by_bot
# ---------------------------------------------------------------------------

class TestHandleWinRateByBot:
    def test_table_output(self, db, capsys):
        u = make_user(db, "BotUser")
        uid = str(u.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=uid)
        make_game(db, [uid, "BOT_random"])
        db.flush()

        handle_win_rate_by_bot(_ns(user_id=uid), db=db)
        out = capsys.readouterr().out
        assert "bot_type" in out
        assert "win_rate" in out

    def test_json_output(self, db, capsys):
        u = make_user(db, "BotJsonUser")
        uid = str(u.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=uid)
        db.flush()

        handle_win_rate_by_bot(_ns(user_id=uid, json=True), db=db)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert data[0]["bot_type"] == "ppo"
        assert data[0]["wins"] == 1

    def test_no_games_shows_no_result(self, db, capsys):
        u = make_user(db, "NoGamesBot")
        uid = str(u.id)
        db.flush()

        handle_win_rate_by_bot(_ns(user_id=uid), db=db)
        out = capsys.readouterr().out
        assert "(결과 없음)" in out

    def test_mock_win_rate_by_bot_type_called(self, db, capsys):
        uid = str(uuid.uuid4())
        with patch("scripts.analytics_cli.win_rate_by_bot_type") as mock_fn:
            mock_fn.return_value = [
                {"bot_type": "ppo", "games": 3, "wins": 2, "win_rate": 0.6667}
            ]
            handle_win_rate_by_bot(_ns(user_id=uid), db=db)
            mock_fn.assert_called_once_with(db, uid)

        out = capsys.readouterr().out
        assert "ppo" in out


# ---------------------------------------------------------------------------
# handle_win_rate_by_count
# ---------------------------------------------------------------------------

class TestHandleWinRateByCount:
    def _make_n_games(self, db, uid: str, n: int) -> None:
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        for i in range(n):
            make_game(db, [uid, "BOT_ppo"], winner_id=uid,
                      created_at=base + timedelta(seconds=i))
        db.flush()

    def test_table_output(self, db, capsys):
        u = make_user(db, "CountUser")
        uid = str(u.id)
        self._make_n_games(db, uid, 6)

        handle_win_rate_by_count(_ns(user_id=uid, bucket=5), db=db)
        out = capsys.readouterr().out
        assert "game_range" in out
        assert "1-5" in out

    def test_json_output(self, db, capsys):
        u = make_user(db, "CountJsonUser")
        uid = str(u.id)
        self._make_n_games(db, uid, 5)

        handle_win_rate_by_count(_ns(user_id=uid, bucket=5, json=True), db=db)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert data[0]["game_range"] == "1-5"

    def test_no_games_shows_no_result(self, db, capsys):
        u = make_user(db, "NoGamesCount")
        uid = str(u.id)
        db.flush()

        handle_win_rate_by_count(_ns(user_id=uid), db=db)
        out = capsys.readouterr().out
        assert "(결과 없음)" in out

    def test_bucket_passed_to_service(self, db, capsys):
        uid = str(uuid.uuid4())
        with patch("scripts.analytics_cli.win_rate_by_game_count") as mock_fn:
            mock_fn.return_value = []
            handle_win_rate_by_count(_ns(user_id=uid, bucket=10), db=db)
            mock_fn.assert_called_once_with(db, uid, bucket=10)
        capsys.readouterr()


# ---------------------------------------------------------------------------
# handle_recent_games
# ---------------------------------------------------------------------------

class TestHandleRecentGames:
    def test_table_output(self, db, capsys):
        u = make_user(db, "RecentUser")
        uid = str(u.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=uid)
        db.flush()

        handle_recent_games(_ns(user_id=uid, limit=20), db=db)
        out = capsys.readouterr().out
        assert "game_id" in out
        assert "result" in out

    def test_json_output(self, db, capsys):
        u = make_user(db, "RecentJsonUser")
        uid = str(u.id)
        make_game(db, [uid, "BOT_random"], winner_id=uid)
        db.flush()

        handle_recent_games(_ns(user_id=uid, limit=20, json=True), db=db)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert data[0]["result"] == "win"

    def test_no_games_shows_no_result(self, db, capsys):
        u = make_user(db, "NoRecentGames")
        uid = str(u.id)
        db.flush()

        handle_recent_games(_ns(user_id=uid), db=db)
        out = capsys.readouterr().out
        assert "(결과 없음)" in out

    def test_limit_passed_to_service(self, db, capsys):
        uid = str(uuid.uuid4())
        with patch("scripts.analytics_cli.recent_games") as mock_fn:
            mock_fn.return_value = []
            handle_recent_games(_ns(user_id=uid, limit=5), db=db)
            mock_fn.assert_called_once_with(db, uid, limit=5)
        capsys.readouterr()

    def test_win_loss_draw_in_output(self, db, capsys):
        u = make_user(db, "WLD")
        uid = str(u.id)
        make_game(db, [uid, "BOT_ppo"], winner_id=uid)       # win
        make_game(db, [uid, "BOT_ppo"], winner_id="BOT_ppo") # loss
        make_game(db, [uid, "BOT_ppo"], winner_id=None)      # draw
        db.flush()

        handle_recent_games(_ns(user_id=uid, limit=20), db=db)
        out = capsys.readouterr().out
        assert "win" in out
        assert "loss" in out
        assert "draw" in out


# ---------------------------------------------------------------------------
# build_parser — argparse 구조 검증
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_four_subcommands_present(self):
        parser = build_parser()
        # argparse 내부에서 subparser choices 를 확인
        subparser_action = next(
            a for a in parser._actions
            if hasattr(a, "_name_parser_map")
        )
        choices = set(subparser_action._name_parser_map.keys())
        assert choices == {"list-users", "win-rate-by-bot", "win-rate-by-count", "recent-games"}

    def test_list_users_defaults(self):
        args = build_parser().parse_args(["list-users"])
        assert args.command == "list-users"
        assert args.limit == 20
        assert args.json is False

    def test_win_rate_by_bot_requires_user_id(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["win-rate-by-bot"])

    def test_win_rate_by_count_bucket_default(self):
        args = build_parser().parse_args(["win-rate-by-count", "--user-id", "abc"])
        assert args.bucket == 5
        assert args.user_id == "abc"

    def test_recent_games_limit_default(self):
        args = build_parser().parse_args(["recent-games", "--user-id", "xyz"])
        assert args.limit == 20

    def test_json_flag_list_users(self):
        args = build_parser().parse_args(["list-users", "--json"])
        assert args.json is True

    def test_json_flag_win_rate_by_bot(self):
        args = build_parser().parse_args(["win-rate-by-bot", "--user-id", "u1", "--json"])
        assert args.json is True
