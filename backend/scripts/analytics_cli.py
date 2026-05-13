"""
analytics_cli.py — PuCo RL 분석 CLI

서브커맨드:
    list-users          최근 게임 수 기준 사용자 목록
    win-rate-by-bot     봇 종류별 승률
    win-rate-by-count   판수 누적별 봇 대상 승률
    recent-games        최근 게임 결과

사용법 (도커 내부):
    python -m scripts.analytics_cli --help
    python -m scripts.analytics_cli list-users
    python -m scripts.analytics_cli win-rate-by-bot --user-id <UUID>
    python -m scripts.analytics_cli win-rate-by-count --user-id <UUID> --bucket 10
    python -m scripts.analytics_cli recent-games --user-id <UUID> --limit 10 --json

환경변수:
    DATABASE_URL  (필수) — PostgreSQL 연결 문자열
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# castone/backend 를 sys.path 에 추가해 app 모듈을 import 할 수 있게 함
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.analytics import (
    list_users,
    win_rate_by_bot_type,
    win_rate_by_game_count,
    recent_games,
)


# ---------------------------------------------------------------------------
# 테이블 출력 (순수 표준 라이브러리)
# ---------------------------------------------------------------------------

def _print_table(rows: list[dict], cols: list[str]) -> None:
    if not rows:
        print("(결과 없음)")
        return
    widths = [
        max(len(str(r.get(c, ""))) for r in [*rows, {c: c}])
        for c in cols
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*cols))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt.format(*[str(r.get(c, "")) for c in cols]))


# ---------------------------------------------------------------------------
# DB 연결
# ---------------------------------------------------------------------------

def _build_session():
    """DATABASE_URL 을 읽어 SQLAlchemy Session 을 반환한다."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("오류: DATABASE_URL 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.execute(text("SET TRANSACTION READ ONLY"))
    return db


# ---------------------------------------------------------------------------
# 서브커맨드 핸들러
# ---------------------------------------------------------------------------

def handle_list_users(args: argparse.Namespace, db=None) -> None:
    """list-users 서브커맨드 핸들러."""
    close_after = db is None
    if db is None:
        db = _build_session()
    try:
        limit = getattr(args, "limit", 20) or 20
        rows = list_users(db, limit=limit)
        cols = ["user_id", "nickname", "total_games", "last_game_at"]
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            _print_table(rows, cols)
    finally:
        if close_after:
            db.close()


def handle_win_rate_by_bot(args: argparse.Namespace, db=None) -> None:
    """win-rate-by-bot 서브커맨드 핸들러."""
    close_after = db is None
    if db is None:
        db = _build_session()
    try:
        rows = win_rate_by_bot_type(db, args.user_id)
        cols = ["bot_type", "games", "wins", "win_rate"]
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            _print_table(rows, cols)
    finally:
        if close_after:
            db.close()


def handle_win_rate_by_count(args: argparse.Namespace, db=None) -> None:
    """win-rate-by-count 서브커맨드 핸들러."""
    close_after = db is None
    if db is None:
        db = _build_session()
    try:
        bucket = getattr(args, "bucket", 5) or 5
        rows = win_rate_by_game_count(db, args.user_id, bucket=bucket)
        cols = ["game_range", "games", "cumulative_wins", "win_rate"]
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            _print_table(rows, cols)
    finally:
        if close_after:
            db.close()


def handle_recent_games(args: argparse.Namespace, db=None) -> None:
    """recent-games 서브커맨드 핸들러."""
    close_after = db is None
    if db is None:
        db = _build_session()
    try:
        limit = getattr(args, "limit", 20) or 20
        rows = recent_games(db, args.user_id, limit=limit)
        cols = ["game_id", "created_at", "result", "opponent_bots"]
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            _print_table(rows, cols)
    finally:
        if close_after:
            db.close()


# ---------------------------------------------------------------------------
# argparse 설정
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analytics_cli",
        description="PuCo RL 분석 CLI",
    )
    sub = parser.add_subparsers(dest="command", metavar="{subcommand}")
    sub.required = True

    # -- list-users --
    p_lu = sub.add_parser("list-users", help="최근 게임 수 기준 사용자 목록")
    p_lu.add_argument("--limit", type=int, default=20, metavar="N", help="출력할 최대 사용자 수 (기본 20)")
    p_lu.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_lu.set_defaults(handler=handle_list_users)

    # -- win-rate-by-bot --
    p_bot = sub.add_parser("win-rate-by-bot", help="봇 종류별 승률")
    p_bot.add_argument("--user-id", required=True, metavar="UUID", help="사용자 UUID")
    p_bot.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_bot.set_defaults(handler=handle_win_rate_by_bot)

    # -- win-rate-by-count --
    p_cnt = sub.add_parser("win-rate-by-count", help="판수 누적별 봇 대상 승률")
    p_cnt.add_argument("--user-id", required=True, metavar="UUID", help="사용자 UUID")
    p_cnt.add_argument("--bucket", type=int, default=5, metavar="N", help="버킷 크기 (기본 5)")
    p_cnt.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_cnt.set_defaults(handler=handle_win_rate_by_count)

    # -- recent-games --
    p_rg = sub.add_parser("recent-games", help="최근 게임 결과")
    p_rg.add_argument("--user-id", required=True, metavar="UUID", help="사용자 UUID")
    p_rg.add_argument("--limit", type=int, default=20, metavar="N", help="출력할 최대 게임 수 (기본 20)")
    p_rg.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_rg.set_defaults(handler=handle_recent_games)

    return parser


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
