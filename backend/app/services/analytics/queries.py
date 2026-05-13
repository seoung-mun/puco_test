"""
Analytics query functions for PuCo RL.

All functions accept a SQLAlchemy Session as first argument so callers can
supply any session (test or production).  No session is created here.
"""
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import text, func, cast
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import GameSession, User
from app.services.agent_registry import resolve_bot_type_from_actor_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_bot(actor_id: str) -> bool:
    return actor_id.startswith("BOT_")


def _result_for_user(game: GameSession, user_id: str) -> str:
    """Return 'win', 'loss', or 'draw' for *user_id* in *game*."""
    if game.winner_id is None:
        return "draw"
    if game.winner_id == user_id:
        return "win"
    return "loss"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_user_games(db: Session, user_id: str) -> list[GameSession]:
    """Return all FINISHED games where *user_id* participated, ordered by created_at ASC."""
    return (
        db.query(GameSession)
        .filter(
            GameSession.status == "FINISHED",
            GameSession.players.contains([user_id]),
        )
        .order_by(GameSession.created_at.asc())
        .all()
    )


def win_rate_by_bot_type(db: Session, user_id: str) -> list[dict]:
    """Return per-bot-type win-rate stats for *user_id*.

    Each entry: {"bot_type": str, "games": int, "wins": int, "win_rate": float}
    Sorted by games DESC.

    Counting rule: within a single game the same bot_type is counted only once
    (even if multiple bots of that type were present).
    """
    games = get_user_games(db, user_id)

    # Accumulate: bot_type -> {games, wins}
    stats: dict[str, dict] = {}
    for game in games:
        players: list[str] = game.players or []
        bot_types_in_game: set[str] = {
            resolve_bot_type_from_actor_id(p)
            for p in players
            if _is_bot(p)
        }
        is_win = game.winner_id == user_id
        for bt in bot_types_in_game:
            if bt not in stats:
                stats[bt] = {"games": 0, "wins": 0}
            stats[bt]["games"] += 1
            if is_win:
                stats[bt]["wins"] += 1

    result = []
    for bt, s in stats.items():
        g = s["games"]
        w = s["wins"]
        result.append({
            "bot_type": bt,
            "games": g,
            "wins": w,
            "win_rate": round(w / g, 4) if g > 0 else 0.0,
        })

    result.sort(key=lambda x: x["games"], reverse=True)
    return result


def win_rate_by_game_count(
    db: Session,
    user_id: str,
    bucket: int = 5,
) -> list[dict]:
    """Return cumulative win-rate at each bucket boundary.

    Each entry: {"game_range": "1-5", "games": int, "cumulative_wins": int, "win_rate": float}
    The last game is always included even if it doesn't land on a bucket boundary.
    """
    games = get_user_games(db, user_id)
    if not games:
        return []

    total = len(games)
    cum_wins = 0
    result = []
    last_idx_added = -1

    for i, game in enumerate(games, start=1):
        if game.winner_id == user_id:
            cum_wins += 1

        # Emit at every bucket boundary
        if i % bucket == 0:
            start = i - bucket + 1
            result.append({
                "game_range": f"{start}-{i}",
                "games": i,
                "cumulative_wins": cum_wins,
                "win_rate": round(cum_wins / i, 4),
            })
            last_idx_added = i

    # Always include the last game if it wasn't already emitted
    if last_idx_added != total:
        start = (last_idx_added + 1) if last_idx_added >= 0 else 1
        result.append({
            "game_range": f"{start}-{total}",
            "games": total,
            "cumulative_wins": cum_wins,
            "win_rate": round(cum_wins / total, 4),
        })

    return result


def list_users(db: Session, limit: int = 20) -> list[dict]:
    """Return users sorted by number of finished games DESC (most active first).

    Columns: user_id, nickname, total_games, last_game_at.
    NOTE: users.total_games column is intentionally ignored; game count is
    derived from games.players JSONB aggregation.
    """
    sql = text(
        """
        SELECT
            u.id           AS user_id,
            u.nickname,
            COUNT(g.id)    AS total_games,
            MAX(g.created_at) AS last_game_at
        FROM users u
        LEFT JOIN games g
               ON g.status = 'FINISHED'
              AND g.players @> jsonb_build_array(u.id::text)
        GROUP BY u.id, u.nickname
        ORDER BY total_games DESC, last_game_at DESC NULLS LAST
        LIMIT :limit
        """
    )
    rows = db.execute(sql, {"limit": limit}).mappings().all()
    return [
        {
            "user_id": str(row["user_id"]),
            "nickname": row["nickname"],
            "total_games": row["total_games"],
            "last_game_at": row["last_game_at"],
        }
        for row in rows
    ]


def recent_games(db: Session, user_id: str, limit: int = 20) -> list[dict]:
    """Return the most recent finished games for *user_id*, newest first.

    Each entry:
        game_id, created_at, result ("win"/"loss"/"draw"),
        opponent_bots (list of bot_type strings), winner_id.
    """
    games = (
        db.query(GameSession)
        .filter(
            GameSession.status == "FINISHED",
            GameSession.players.contains([user_id]),
        )
        .order_by(GameSession.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for game in games:
        players: list[str] = game.players or []
        opponent_bots = list({
            resolve_bot_type_from_actor_id(p)
            for p in players
            if _is_bot(p)
        })
        result.append({
            "game_id": str(game.id),
            "created_at": game.created_at,
            "result": _result_for_user(game, user_id),
            "opponent_bots": opponent_bots,
            "winner_id": game.winner_id,
        })

    return result
