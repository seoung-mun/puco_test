"""
Analytics query functions for PuCo RL.

All functions accept a SQLAlchemy Session as first argument so callers can
supply any session (test or production).  No session is created here.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.models import GameSession, Replay, User
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


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _load_human_names(db: Session, actor_ids: set[str]) -> dict[str, str]:
    uuids = [parsed for actor_id in actor_ids if not _is_bot(actor_id) for parsed in [_parse_uuid(actor_id)] if parsed]
    if not uuids:
        return {}

    users = db.query(User).filter(User.id.in_(uuids)).all()
    return {
        str(user.id): user.nickname or user.email or str(user.id)
        for user in users
    }


def _display_name_for_actor(
    actor_id: str,
    human_names: dict[str, str],
    score_names: dict[str, str] | None = None,
) -> str:
    if score_names and actor_id in score_names:
        return score_names[actor_id]
    if _is_bot(actor_id):
        return resolve_bot_type_from_actor_id(actor_id)
    return human_names.get(actor_id, actor_id)


def _canonical_ordered_players(
    actor_ids: list[str],
    human_names: dict[str, str],
) -> list[str]:
    return [
        _display_name_for_actor(actor_id, human_names)
        for actor_id in actor_ids
    ]


def _lineup_signature_for_actor_ids(actor_ids: list[str]) -> list[str]:
    return [
        resolve_bot_type_from_actor_id(actor_id) if _is_bot(actor_id) else "human"
        for actor_id in actor_ids
    ]


def _is_ppo_actor(actor_id: str | None) -> bool:
    return _is_bot(str(actor_id or "")) and resolve_bot_type_from_actor_id(str(actor_id)) == "ppo"


def _load_replay_payloads(db: Session, games: list[GameSession]) -> dict[str, dict[str, Any]]:
    if not games:
        return {}

    replays = (
        db.query(Replay)
        .filter(Replay.game_id.in_([game.id for game in games]))
        .all()
    )
    return {
        str(replay.game_id): replay.payload if isinstance(replay.payload, dict) else {}
        for replay in replays
    }


def _normalize_final_scores(
    game: GameSession,
    final_scores: list[dict[str, Any]] | None,
    human_names: dict[str, str],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for index, row in enumerate(final_scores or []):
        actor_id = row.get("actor_id")
        player_index = row.get("player")
        if actor_id is None:
            if isinstance(player_index, int) and 0 <= player_index < len(game.players or []):
                actor_id = str((game.players or [])[player_index])
        if actor_id is None:
            continue

        normalized_player_index = (
            player_index
            if isinstance(player_index, int) and 0 <= player_index < len(game.players or [])
            else None
        )
        actor_id = str(actor_id)
        normalized.append(
            {
                "actor_id": actor_id,
                "player": normalized_player_index,
                "seat": normalized_player_index + 1 if normalized_player_index is not None else None,
                "display_name": row.get("display_name") or _display_name_for_actor(actor_id, human_names),
                "vp": int(row.get("vp", 0) or 0),
                "tiebreaker": int(row.get("tiebreaker", 0) or 0),
                "winner": bool(row.get("winner")),
                "_index": index,
            }
        )

    normalized.sort(key=lambda item: (-item["vp"], -item["tiebreaker"], item["_index"]))
    return normalized


def _score_details_for_user(
    game: GameSession,
    user_id: str,
    human_names: dict[str, str],
    replay_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    score_name_map = {
        row["actor_id"]: row["display_name"]
        for row in _normalize_final_scores(
            game=game,
            final_scores=(replay_payload or {}).get("final_scores"),
            human_names=human_names,
        )
    }
    score_rows = _normalize_final_scores(
        game=game,
        final_scores=(replay_payload or {}).get("final_scores"),
        human_names=human_names,
    )
    if not score_rows:
        return {
            "score_data_available": False,
            "my_rank": None,
            "winner_display_name": (
                _display_name_for_actor(
                    str(game.winner_id),
                    human_names,
                    score_name_map,
                )
                if game.winner_id is not None
                else None
            ),
            "my_vp": None,
            "benchmark_vp": None,
            "vp_gap": None,
            "score_rows": [],
        }

    winner_display_name = (
        _display_name_for_actor(str(game.winner_id), human_names, score_name_map)
        if game.winner_id is not None
        else None
    )
    my_index = next(
        (index for index, row in enumerate(score_rows) if row["actor_id"] == user_id),
        None,
    )
    if my_index is None:
        return {
            "score_data_available": True,
            "my_rank": None,
            "winner_display_name": winner_display_name,
            "my_vp": None,
            "benchmark_vp": None,
            "vp_gap": None,
            "score_rows": score_rows,
        }

    my_row = score_rows[my_index]
    my_rank = my_index + 1
    my_vp = my_row["vp"]
    benchmark_vp = None
    vp_gap = None

    if my_rank == 1:
        if len(score_rows) > 1:
            benchmark_vp = score_rows[1]["vp"]
            vp_gap = my_vp - benchmark_vp
    else:
        benchmark_vp = score_rows[0]["vp"]
        vp_gap = benchmark_vp - my_vp

    return {
        "score_data_available": True,
        "my_rank": my_rank,
        "winner_display_name": winner_display_name,
        "my_vp": my_vp,
        "benchmark_vp": benchmark_vp,
        "vp_gap": vp_gap,
        "score_rows": score_rows,
    }


def _build_recent_game_row(
    game: GameSession,
    user_id: str,
    human_names: dict[str, str],
    replay_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    players: list[str] = [str(player) for player in (game.players or [])]
    opponent_bots = sorted(
        {
            resolve_bot_type_from_actor_id(actor_id)
            for actor_id in players
            if _is_bot(actor_id)
        }
    )
    base_row = {
        "game_id": str(game.id),
        "created_at": game.created_at,
        "result": _result_for_user(game, user_id),
        "opponent_bots": opponent_bots,
        "winner_id": game.winner_id,
    }
    if game.num_players != 3:
        return base_row

    score_details = _score_details_for_user(
        game=game,
        user_id=user_id,
        human_names=human_names,
        replay_payload=replay_payload,
    )
    score_name_map = {
        row["actor_id"]: row["display_name"]
        for row in score_details.pop("score_rows", [])
    }
    ordered_players = [
        _display_name_for_actor(actor_id, human_names, score_name_map)
        for actor_id in players
    ]
    my_seat = (players.index(user_id) + 1) if user_id in players else None

    return {
        **base_row,
        "ordered_players": ordered_players,
        "my_seat": my_seat,
        **score_details,
    }


def _is_ordered_lineup_game(game: GameSession, user_id: str) -> bool:
    players = [str(player) for player in (game.players or [])]
    return (
        game.status == "FINISHED"
        and game.num_players == 3
        and len(players) == 3
        and user_id in players
    )


def _build_lineup_game_row(
    game: GameSession,
    user_id: str,
    human_names: dict[str, str],
    replay_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    players = [str(player) for player in (game.players or [])]
    score_details = _score_details_for_user(
        game=game,
        user_id=user_id,
        human_names=human_names,
        replay_payload=replay_payload,
    )
    score_rows = score_details.pop("score_rows", [])
    score_name_map = {
        row["actor_id"]: row["display_name"]
        for row in score_rows
    }
    ordered_players = [
        _display_name_for_actor(actor_id, human_names, score_name_map)
        for actor_id in players
    ]
    first_row = score_rows[0] if len(score_rows) > 0 else None
    second_row = score_rows[1] if len(score_rows) > 1 else None

    return {
        "game_id": str(game.id),
        "created_at": game.created_at,
        "lineup": " > ".join(ordered_players),
        "ordered_players": ordered_players,
        "winner_display_name": score_details["winner_display_name"],
        "first_place_vp": first_row["vp"] if first_row else None,
        "second_place_vp": second_row["vp"] if second_row else None,
        "first_second_vp_gap": (
            first_row["vp"] - second_row["vp"]
            if first_row and second_row
            else None
        ),
        "my_rank": score_details["my_rank"],
        "my_vp": score_details["my_vp"],
    }


def _is_ppo_lineup_game(game: GameSession) -> bool:
    players = [str(player) for player in (game.players or [])]
    return (
        game.status == "FINISHED"
        and game.num_players == 3
        and len(players) == 3
        and any(_is_ppo_actor(player) for player in players)
    )


def _build_ppo_lineup_game_row(
    game: GameSession,
    human_names: dict[str, str],
    replay_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    players = [str(player) for player in (game.players or [])]
    ppo_seats = [
        index + 1
        for index, actor_id in enumerate(players)
        if _is_ppo_actor(actor_id)
    ]
    signature_parts = _lineup_signature_for_actor_ids(players)
    score_rows = _normalize_final_scores(
        game=game,
        final_scores=(replay_payload or {}).get("final_scores"),
        human_names=human_names,
    )
    seat_name_map = {
        row["seat"]: row["display_name"]
        for row in score_rows
        if row.get("seat") is not None
    }
    score_name_map = {
        row["actor_id"]: row["display_name"]
        for row in score_rows
    }
    ordered_players = [
        seat_name_map.get(index + 1)
        or _display_name_for_actor(actor_id, human_names, score_name_map)
        for index, actor_id in enumerate(players)
    ]

    ranked_rows = [
        {**row, "rank": rank}
        for rank, row in enumerate(score_rows, start=1)
    ]
    ppo_score_rows = [
        row
        for row in ranked_rows
        if (
            row.get("seat") in ppo_seats
            if row.get("seat") is not None
            else _is_ppo_actor(row.get("actor_id"))
        )
    ]
    non_ppo_score_rows = [
        row
        for row in ranked_rows
        if not (
            row.get("seat") in ppo_seats
            if row.get("seat") is not None
            else _is_ppo_actor(row.get("actor_id"))
        )
    ]
    best_ppo_row = ppo_score_rows[0] if ppo_score_rows else None
    best_non_ppo_row = non_ppo_score_rows[0] if non_ppo_score_rows else None
    best_ppo_vp = best_ppo_row["vp"] if best_ppo_row else None
    best_non_ppo_vp = best_non_ppo_row["vp"] if best_non_ppo_row else None
    winner_id = str(game.winner_id) if game.winner_id is not None else None

    return {
        "game_id": str(game.id),
        "created_at": game.created_at,
        "lineup": " > ".join(ordered_players),
        "lineup_signature": " > ".join(signature_parts),
        "ordered_players": ordered_players,
        "ppo_seats": ppo_seats,
        "ppo_count": len(ppo_seats),
        "ppo_result": (
            "draw"
            if winner_id is None
            else "win" if _is_ppo_actor(winner_id) else "loss"
        ),
        "winner_display_name": (
            _display_name_for_actor(winner_id, human_names, score_name_map)
            if winner_id is not None
            else None
        ),
        "best_ppo_rank": best_ppo_row["rank"] if best_ppo_row else None,
        "best_ppo_vp": best_ppo_vp,
        "best_non_ppo_vp": best_non_ppo_vp,
        "best_ppo_vp_gap": (
            best_ppo_vp - best_non_ppo_vp
            if best_ppo_vp is not None and best_non_ppo_vp is not None
            else None
        ),
        "score_data_available": bool(score_rows),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_user_id_or_nickname(
    db: Session,
    *,
    user_id: str | None = None,
    nickname: str | None = None,
) -> str:
    if bool(user_id) == bool(nickname):
        raise ValueError("Provide exactly one of user_id or nickname")

    if nickname is not None:
        user = db.query(User).filter(User.nickname == nickname).first()
        if user is None:
            raise ValueError(f"User not found for nickname={nickname!r}")
        return str(user.id)

    parsed = _parse_uuid(user_id)
    if parsed is None:
        raise ValueError(f"Invalid user_id: {user_id!r}")
    return str(parsed)


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
    if bucket <= 0:
        raise ValueError(f"bucket must be a positive integer, got {bucket!r}")

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


def lineup_summary(db: Session, user_id: str) -> list[dict]:
    games = (
        db.query(GameSession)
        .filter(
            GameSession.status == "FINISHED",
            GameSession.num_players == 3,
            GameSession.players.contains([user_id]),
        )
        .order_by(GameSession.created_at.desc())
        .all()
    )
    if not games:
        return []

    actor_ids = {
        str(actor_id)
        for game in games
        for actor_id in (game.players or [])
    }
    human_names = _load_human_names(db, actor_ids)
    replay_payloads = _load_replay_payloads(db, games)

    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    vp_gap_totals: defaultdict[tuple[str, ...], float] = defaultdict(float)

    for game in games:
        players = [str(player) for player in (game.players or [])]
        row = _build_recent_game_row(
            game=game,
            user_id=user_id,
            human_names=human_names,
            replay_payload=replay_payloads.get(str(game.id)),
        )
        ordered_players = _canonical_ordered_players(players, human_names)
        lineup_key = tuple(players)
        stats = grouped.setdefault(
            lineup_key,
            {
                "lineup": " > ".join(ordered_players),
                "ordered_players": ordered_players,
                "my_seat": row["my_seat"],
                "games": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "win_rate": 0.0,
                "avg_vp_gap": None,
                "vp_gap_games": 0,
                "last_played_at": game.created_at,
            },
        )
        stats["games"] += 1
        if row["result"] == "win":
            stats["wins"] += 1
        elif row["result"] == "loss":
            stats["losses"] += 1
        else:
            stats["draws"] += 1

        if game.created_at and (
            stats["last_played_at"] is None or game.created_at > stats["last_played_at"]
        ):
            stats["last_played_at"] = game.created_at

        if row["vp_gap"] is not None:
            stats["vp_gap_games"] += 1
            vp_gap_totals[lineup_key] += row["vp_gap"]

    result = []
    for key, stats in grouped.items():
        games_played = stats["games"]
        stats["win_rate"] = round(stats["wins"] / games_played, 4) if games_played > 0 else 0.0
        if stats["vp_gap_games"] > 0:
            stats["avg_vp_gap"] = round(vp_gap_totals[key] / stats["vp_gap_games"], 4)
        result.append(stats)

    result.sort(
        key=lambda row: (
            -row["games"],
            -(row["last_played_at"].timestamp() if row["last_played_at"] else 0),
            row["lineup"],
        )
    )
    return result


def lineup_games(
    db: Session,
    user_id: str,
    limit: int = 20,
    lineup: list[str] | None = None,
) -> list[dict[str, Any]]:
    games = (
        db.query(GameSession)
        .filter(
            GameSession.status == "FINISHED",
            GameSession.players.contains([user_id]),
        )
        .order_by(GameSession.created_at.desc())
        .all()
    )
    if not games:
        return []

    actor_ids = {
        str(actor_id)
        for game in games
        for actor_id in (game.players or [])
    }
    human_names = _load_human_names(db, actor_ids)
    replay_payloads = _load_replay_payloads(db, games)
    normalized_lineup = [part.strip() for part in (lineup or [])]

    rows: list[dict[str, Any]] = []
    for game in games:
        row = _build_lineup_game_row(
            game=game,
            user_id=user_id,
            human_names=human_names,
            replay_payload=replay_payloads.get(str(game.id)),
        )
        if normalized_lineup and row["ordered_players"] != normalized_lineup:
            continue
        rows.append(row)

    if limit <= 0:
        return rows
    return rows[:limit]


def ppo_lineup_games(
    db: Session,
    limit: int = 20,
    lineup: list[str] | None = None,
) -> list[dict[str, Any]]:
    games = (
        db.query(GameSession)
        .filter(
            GameSession.status == "FINISHED",
            GameSession.num_players == 3,
        )
        .order_by(GameSession.created_at.desc())
        .all()
    )
    games = [game for game in games if _is_ppo_lineup_game(game)]
    if not games:
        return []

    actor_ids = {
        str(actor_id)
        for game in games
        for actor_id in (game.players or [])
    }
    human_names = _load_human_names(db, actor_ids)
    replay_payloads = _load_replay_payloads(db, games)
    normalized_lineup = [
        part.strip().lower()
        for part in (lineup or [])
        if part.strip()
    ]

    rows: list[dict[str, Any]] = []
    for game in games:
        row = _build_ppo_lineup_game_row(
            game=game,
            human_names=human_names,
            replay_payload=replay_payloads.get(str(game.id)),
        )
        if normalized_lineup and row["lineup_signature"].split(" > ") != normalized_lineup:
            continue
        rows.append(row)

    if limit <= 0:
        return rows
    return rows[:limit]


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
    if not games:
        return []

    actor_ids = {
        str(actor_id)
        for game in games
        for actor_id in (game.players or [])
    }
    human_names = _load_human_names(db, actor_ids)
    replay_payloads = _load_replay_payloads(db, games)

    rows: list[dict[str, Any]] = []
    for game in games:
        players: list[str] = [str(player) for player in (game.players or [])]
        base_row = {
            "game_id": str(game.id),
            "created_at": game.created_at,
            "result": _result_for_user(game, user_id),
            "opponent_bots": sorted(
                {
                    resolve_bot_type_from_actor_id(actor_id)
                    for actor_id in players
                    if _is_bot(actor_id)
                }
            ),
            "winner_id": game.winner_id,
        }
        if _is_ordered_lineup_game(game, user_id):
            base_row.update(
                _build_recent_game_row(
                    game=game,
                    user_id=user_id,
                    human_names=human_names,
                    replay_payload=replay_payloads.get(str(game.id)),
                )
            )
        rows.append(base_row)

    return rows
