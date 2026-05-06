"""
오래 방치된 PROGRESS 게임을 RECOVERY_BLOCKED로 마킹해 좀비 봇 루프를 끊는 스크립트.

배경:
    백엔드 재기동 시 스케줄러가 PROGRESS 상태의 게임을 다시 잡아 봇 추론을 재개합니다.
    플레이어가 떠난 뒤 정리되지 않은 PROGRESS 게임이 누적되면, 인스턴스가 작은 환경
    (Render 무료/Starter 등)에서는 CPU/메모리 부족으로 OOM 또는 throttling이 발생합니다.

동작:
    updated_at이 임계값(기본 6시간) 이전인 PROGRESS 게임을 RECOVERY_BLOCKED로 변경하고
    recovery_blocked_reason='zombie_cleanup'을 기록합니다. _mark_blocked_in_db와 동일한
    상태로 만들어 스케줄러가 무시하게 합니다. Redis 메타도 best-effort로 동기화합니다.

사용법 (도커 컨테이너 안에서):
    # 대상 미리보기 (dry-run)
    docker exec puco_backend python scripts/cleanup_zombie_progress_games.py

    # 임계값 조정 후 미리보기 (예: 24시간)
    docker exec puco_backend python scripts/cleanup_zombie_progress_games.py --threshold-hours 24

    # 실제 실행
    docker exec puco_backend python scripts/cleanup_zombie_progress_games.py --execute

환경변수:
    DATABASE_URL  (필수) — PostgreSQL 연결 문자열. 컨테이너에서 자동 주입됨.
    REDIS_URL     (선택) — 있으면 Redis 메타도 동기화 시도.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    parser = argparse.ArgumentParser(description="좀비 PROGRESS 게임 정리")
    parser.add_argument(
        "--threshold-hours",
        type=float,
        default=6.0,
        help="updated_at이 이 시간(시간 단위) 이전인 PROGRESS 게임을 대상으로 합니다 (기본: 6)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="실제 마킹을 수행합니다. 없으면 dry-run(목록만 출력).",
    )
    args = parser.parse_args()

    if not os.getenv("DATABASE_URL"):
        print("오류: DATABASE_URL 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.models import GameSession

    engine = create_engine(os.environ["DATABASE_URL"])
    Session = sessionmaker(bind=engine)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.threshold_hours)

    with Session() as db:
        targets = (
            db.query(GameSession)
            .filter(GameSession.status == "PROGRESS")
            .filter(GameSession.updated_at < cutoff)
            .order_by(GameSession.updated_at.asc())
            .all()
        )

        if not targets:
            print(f"임계값 {args.threshold_hours}시간 이전 PROGRESS 게임이 없습니다.")
            return

        prefix = "[DRY RUN]" if not args.execute else "[EXECUTE]"
        print(f"{prefix} 좀비 PROGRESS 정리 대상 (updated_at < {cutoff.isoformat()}):")
        for g in targets:
            age_h = (datetime.now(timezone.utc) - g.updated_at).total_seconds() / 3600
            print(
                f"  - id={g.id}"
                f"  host_id={g.host_id}"
                f"  updated_at={g.updated_at.isoformat()}"
                f"  age={age_h:.1f}h"
            )
        print(f"총 {len(targets)}개.")

        if not args.execute:
            print("\n실제 마킹하려면 --execute 옵션으로 실행하세요.")
            return

        for g in targets:
            g.status = "RECOVERY_BLOCKED"
            g.recovery_blocked_reason = "zombie_cleanup"
        db.commit()
        print(f"\nDB 업데이트 완료: {len(targets)}개 게임을 RECOVERY_BLOCKED로 마킹.")

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            print("REDIS_URL 미설정 — Redis 메타 동기화는 건너뜀.")
            return

        try:
            import redis
            r = redis.Redis.from_url(redis_url)
            synced = 0
            for g in targets:
                key = f"game:{g.id}:meta"
                if r.exists(key):
                    r.hset(key, mapping={"status": "RECOVERY_BLOCKED"})
                    r.expire(key, 900)
                    synced += 1
            print(f"Redis 메타 동기화: {synced}/{len(targets)}개.")
        except Exception as exc:
            print(f"Redis 동기화 실패 (무시 가능): {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
