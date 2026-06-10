"""
analytics_cli.py — PuCo RL 분석 CLI

서브커맨드:
    list-users          최근 게임 수 기준 사용자 목록
    win-rate-by-bot     봇 종류별 승률
    win-rate-by-count   판수 누적별 봇 대상 승률
    recent-games        최근 게임 결과
    lineup-summary      3인전 조합 기준 승률/VP 차이 요약
    lineup-games        게임별 조합 상세 결과
    ppo-lineup-games    PPO 포함 게임별 조합 상세 결과
    ppo-human-winrate   사람 포함 PPO 매치업 순위 분포 SVG 차트 생성

사용법 (도커 내부):
    python -m scripts.analytics_cli --help
    python -m scripts.analytics_cli list-users
    python -m scripts.analytics_cli win-rate-by-bot --user-id <UUID>
    python -m scripts.analytics_cli win-rate-by-bot --nickname <NICKNAME>
    python -m scripts.analytics_cli win-rate-by-count --user-id <UUID> --bucket 10
    python -m scripts.analytics_cli recent-games --user-id <UUID> --limit 10 --json
    python -m scripts.analytics_cli lineup-summary --nickname <NICKNAME> --json
    python -m scripts.analytics_cli lineup-games --nickname <NICKNAME> --lineup "tester,ppo,action_value"
    python -m scripts.analytics_cli ppo-lineup-games --lineup "human,ppo,random" --json
    python -m scripts.analytics_cli ppo-human-winrate --output-action-value av.svg --output-ppo ppo.svg

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
    lineup_summary,
    list_users,
    lineup_games,
    ppo_lineup_games,
    resolve_user_id_or_nickname,
    win_rate_by_bot_type,
    win_rate_by_game_count,
    recent_games,
    ppo_vs_humans_summary,
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


def _resolve_target_user_id(db, args: argparse.Namespace) -> str:
    try:
        return resolve_user_id_or_nickname(
            db,
            user_id=getattr(args, "user_id", None),
            nickname=getattr(args, "nickname", None),
        )
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


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
        user_id = _resolve_target_user_id(db, args)
        rows = win_rate_by_bot_type(db, user_id)
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
        user_id = _resolve_target_user_id(db, args)
        rows = win_rate_by_game_count(db, user_id, bucket=bucket)
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
        user_id = _resolve_target_user_id(db, args)
        rows = recent_games(db, user_id, limit=limit)
        cols = [
            "game_id",
            "created_at",
            "result",
            "opponent_bots",
            "winner_id",
            "ordered_players",
            "my_seat",
            "my_rank",
            "winner_display_name",
            "my_vp",
            "benchmark_vp",
            "vp_gap",
            "score_data_available",
        ]
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            _print_table(rows, cols)
    finally:
        if close_after:
            db.close()


def handle_lineup_summary(args: argparse.Namespace, db=None) -> None:
    """lineup-summary 서브커맨드 핸들러."""
    close_after = db is None
    if db is None:
        db = _build_session()
    try:
        user_id = _resolve_target_user_id(db, args)
        rows = lineup_summary(db, user_id)
        cols = [
            "lineup",
            "my_seat",
            "games",
            "wins",
            "losses",
            "draws",
            "win_rate",
            "avg_vp_gap",
            "vp_gap_games",
            "last_played_at",
        ]
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            _print_table(rows, cols)
    finally:
        if close_after:
            db.close()


def handle_lineup_games(args: argparse.Namespace, db=None) -> None:
    """lineup-games 서브커맨드 핸들러."""
    close_after = db is None
    if db is None:
        db = _build_session()
    try:
        limit = getattr(args, "limit", 20) or 20
        user_id = _resolve_target_user_id(db, args)
        lineup_filter = getattr(args, "lineup", None)
        lineup = (
            [part.strip() for part in lineup_filter.split(",")]
            if lineup_filter
            else None
        )
        rows = lineup_games(db, user_id, limit=limit, lineup=lineup)
        cols = [
            "game_id",
            "created_at",
            "lineup",
            "winner_display_name",
            "first_place_vp",
            "second_place_vp",
            "first_second_vp_gap",
            "my_rank",
            "my_vp",
        ]
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            _print_table(rows, cols)
    finally:
        if close_after:
            db.close()


def handle_ppo_lineup_games(args: argparse.Namespace, db=None) -> None:
    """ppo-lineup-games 서브커맨드 핸들러."""
    close_after = db is None
    if db is None:
        db = _build_session()
    try:
        limit = getattr(args, "limit", 20) or 20
        lineup_filter = getattr(args, "lineup", None)
        lineup = (
            [part.strip().lower() for part in lineup_filter.split(",") if part.strip()]
            if lineup_filter
            else None
        )
        rows = ppo_lineup_games(db, limit=limit, lineup=lineup)
        cols = [
            "game_id",
            "created_at",
            "lineup",
            "lineup_signature",
            "ordered_players",
            "ppo_seats",
            "ppo_count",
            "ppo_result",
            "winner_display_name",
            "best_ppo_rank",
            "best_ppo_vp",
            "best_non_ppo_vp",
            "best_ppo_vp_gap",
            "score_data_available",
        ]
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            _print_table(rows, cols)
    finally:
        if close_after:
            db.close()


def handle_ppo_vs_humans(args: argparse.Namespace, db=None) -> None:
    """ppo-vs-humans 서브커맨드 핸들러."""
    close_after = db is None
    if db is None:
        db = _build_session()
    try:
        nicknames_str = getattr(args, "nicknames", "") or ""
        nicknames = [n.strip() for n in nicknames_str.split(",") if n.strip()]
        rows = ppo_vs_humans_summary(db, nicknames)
        cols = ["human_nickname", "total_games", "ppo_wins", "ppo_losses", "ppo_win_rate"]
        if getattr(args, "json", False):
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            _print_table(rows, cols)
    finally:
        if close_after:
            db.close()


def handle_ppo_human_winrate(args: argparse.Namespace, db=None) -> None:
    """ppo-human-winrate 서브커맨드 핸들러 — 매치업별 SVG 차트를 파일로 저장."""
    from scripts.visualize_ppo_human_winrate import (
        display_label,
        render_rank_bar_chart,
        summarize_requested_matchups,
        write_text,
    )

    close_after = db is None
    if db is None:
        db = _build_session()
    try:
        rows = ppo_lineup_games(db, limit=0)
        summary = summarize_requested_matchups(rows)
        output_paths = {
            "human + ppo + action_value": args.output_action_value,
            "human + ppo + ppo": args.output_ppo,
        }
        for stats in summary:
            label = str(stats["lineup_signature"])
            output_path = output_paths.get(label)
            if not output_path:
                continue
            chart_title = args.title if args.title else display_label(label)
            svg = render_rank_bar_chart(stats, title=chart_title)
            write_text(output_path, svg)
            print(
                f"wrote SVG: {output_path} "
                f"(rank_games={stats['rank_games']}, games={stats['games']})"
            )
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

    def add_user_lookup_args(target: argparse.ArgumentParser) -> None:
        group = target.add_mutually_exclusive_group(required=True)
        group.add_argument("--user-id", metavar="UUID", help="사용자 UUID")
        group.add_argument("--nickname", metavar="NICKNAME", help="고유 닉네임")

    # -- win-rate-by-bot --
    p_bot = sub.add_parser("win-rate-by-bot", help="봇 종류별 승률")
    add_user_lookup_args(p_bot)
    p_bot.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_bot.set_defaults(handler=handle_win_rate_by_bot)

    # -- win-rate-by-count --
    p_cnt = sub.add_parser("win-rate-by-count", help="판수 누적별 봇 대상 승률")
    add_user_lookup_args(p_cnt)
    p_cnt.add_argument("--bucket", type=int, default=5, metavar="N", help="버킷 크기 (기본 5)")
    p_cnt.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_cnt.set_defaults(handler=handle_win_rate_by_count)

    # -- recent-games --
    p_rg = sub.add_parser("recent-games", help="최근 게임 결과")
    add_user_lookup_args(p_rg)
    p_rg.add_argument("--limit", type=int, default=20, metavar="N", help="출력할 최대 게임 수 (기본 20)")
    p_rg.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_rg.set_defaults(handler=handle_recent_games)

    # -- lineup-summary --
    p_ls = sub.add_parser("lineup-summary", help="3인전 조합 기준 승률/VP 차이 요약")
    add_user_lookup_args(p_ls)
    p_ls.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_ls.set_defaults(handler=handle_lineup_summary)

    # -- lineup-games --
    p_lg = sub.add_parser("lineup-games", help="게임별 조합 상세 결과")
    add_user_lookup_args(p_lg)
    p_lg.add_argument("--limit", type=int, default=20, metavar="N", help="출력할 최대 게임 수 (기본 20)")
    p_lg.add_argument("--lineup", metavar="A,B,C", help="순서 포함 exact 조합 필터")
    p_lg.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_lg.set_defaults(handler=handle_lineup_games)

    # -- ppo-lineup-games --
    p_plg = sub.add_parser("ppo-lineup-games", help="PPO 포함 게임별 조합 상세 결과")
    p_plg.add_argument("--limit", type=int, default=20, metavar="N", help="출력할 최대 게임 수 (기본 20)")
    p_plg.add_argument("--lineup", metavar="A,B,C", help="타입 순서 exact 조합 필터 (예: human,ppo,random)")
    p_plg.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_plg.set_defaults(handler=handle_ppo_lineup_games)

    # -- ppo-human-winrate --
    p_phw = sub.add_parser(
        "ppo-human-winrate",
        help="사람 포함 PPO 매치업 순위 분포 SVG 차트 생성",
    )
    p_phw.add_argument(
        "--output-action-value",
        default="ppo_human_winrate_action_value.svg",
        metavar="PATH",
        help="사람 + PPO + action_value 조합 SVG 출력 경로",
    )
    p_phw.add_argument(
        "--output-ppo",
        default="ppo_human_winrate_ppo.svg",
        metavar="PATH",
        help="사람 + PPO + PPO 조합 SVG 출력 경로",
    )
    p_phw.add_argument(
        "--title",
        default=None,
        metavar="TITLE",
        help="공통 차트 제목 (지정 시 매치업 라벨 대신 사용)",
    )
    p_phw.set_defaults(handler=handle_ppo_human_winrate)

    # -- ppo-vs-humans --
    p_pvh = sub.add_parser("ppo-vs-humans", help="지정된 인간 플레이어 대비 PPO 승률")
    p_pvh.add_argument("--nicknames", required=True, metavar="N1,N2,...", help="콤마로 구분된 인간 플레이어 닉네임 목록")
    p_pvh.add_argument("--json", action="store_true", help="JSON 형식으로 출력")
    p_pvh.set_defaults(handler=handle_ppo_vs_humans)

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
