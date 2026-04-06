"""
WAITING 상태인 모든 방(GameSession)을 DB에서 삭제하는 일회성 정리 스크립트.

사용법:
    # 삭제 대상 확인 (실제 삭제 안 함)
    python scripts/cleanup_all_waiting_rooms.py

    # 실제 삭제 실행
    python scripts/cleanup_all_waiting_rooms.py --execute

환경변수:
    DATABASE_URL  (필수) — PostgreSQL 연결 문자열
"""
import argparse
import os
import sys

# castone/backend를 sys.path에 추가해 app 모듈을 import할 수 있게 함
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    parser = argparse.ArgumentParser(description="WAITING 방 전체 삭제 스크립트")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="실제 삭제를 수행합니다. 없으면 dry-run(목록만 출력).",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("오류: DATABASE_URL 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        print("예시: export DATABASE_URL=postgresql://user:pass@localhost:5432/dbname", file=sys.stderr)
        sys.exit(1)

    # 이 시점에서 import해야 DATABASE_URL 체크 이후 engine이 생성됨
    from sqlalchemy import create_engine, delete
    from sqlalchemy.orm import sessionmaker
    from app.db.models import GameSession, GameLog

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        rooms = db.query(GameSession).filter(GameSession.status == "WAITING").all()

        if not rooms:
            print("WAITING 상태인 방이 없습니다.")
            return

        prefix = "[DRY RUN]" if not args.execute else "[EXECUTE]"
        print(f"{prefix} 삭제 대상 WAITING 방:")
        for r in rooms:
            print(
                f"  - id={r.id}"
                f"  title={r.title!r}"
                f"  host_id={r.host_id}"
                f"  created_at={r.created_at}"
            )
        print(f"총 {len(rooms)}개.")

        if not args.execute:
            print("\n실제 삭제하려면 --execute 옵션으로 실행하세요.")
            return

        room_ids = [r.id for r in rooms]

        # GameLog FK 먼저 삭제 (cascade 미설정)
        deleted_logs = db.execute(
            delete(GameLog).where(GameLog.game_id.in_(room_ids))
        ).rowcount

        # GameSession 삭제
        for r in rooms:
            db.delete(r)

        db.commit()
        print(f"\n삭제 완료: 방 {len(rooms)}개, GameLog {deleted_logs}개 삭제됨.")


if __name__ == "__main__":
    main()
