import logging
from sqlalchemy.orm import Session
from app.db.models import GameSession

logger = logging.getLogger(__name__)


def _is_human(player_id: str) -> bool:
    return not str(player_id).startswith("BOT_")


def cleanup_stale_rooms(db: Session) -> None:
    """
    서버 시작 시 WAITING 방 전체를 점검.
    방장이 WS 없이 남겨진 것으로 간주하여 handle_leave 동일 로직 적용:
      - 방장 제거 후 사람 플레이어 잔존 → 방장 이전, 방 유지
      - 방장 제거 후 사람 플레이어 없음  → 방 삭제
    """
    stale_rooms = db.query(GameSession).filter(GameSession.status == "WAITING").all()

    deleted = 0
    transferred = 0

    for room in stale_rooms:
        host_id = str(room.host_id) if room.host_id else None
        players = [str(p) for p in (room.players or [])]

        # host_id가 None이거나 방이 비어있으면 삭제
        if not host_id or not players:
            db.delete(room)
            deleted += 1
            continue

        # 방장을 제거한 나머지
        remaining = [p for p in players if p != host_id]
        other_humans = [p for p in remaining if _is_human(p)]

        if other_humans:
            # 다른 사람 플레이어 있음 → 방장 이전, 방 유지
            room.players = remaining
            room.host_id = other_humans[0]
            transferred += 1
        else:
            # 봇만 남거나 빈 방 → 삭제
            db.delete(room)
            deleted += 1

    db.commit()
    logger.info(
        "Startup room cleanup: deleted=%d, host_transferred=%d",
        deleted, transferred,
    )
