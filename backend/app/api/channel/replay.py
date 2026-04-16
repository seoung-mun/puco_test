from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app.dependencies import get_db, get_current_user
from app.db.models import GameSession, User
from app.schemas.game import RoomPlayerInfo
from app.schemas.replay import (
    ReplayDetailResponse,
    ReplayFrame,
    ReplayListItem,
    ReplayListResponse,
    ReplayPlayerInfo,
)
from app.services.agent_registry import resolve_bot_type_from_actor_id
from app.services.replay_logger import get_replay_file_path


router = APIRouter()


def _resolve_player_infos(room: GameSession, db: Session) -> list[ReplayPlayerInfo]:
    result: list[ReplayPlayerInfo] = []
    for pid in (room.players or []):
        pid_str = str(pid)
        if pid_str.startswith("BOT_"):
            bot_type = resolve_bot_type_from_actor_id(pid_str).capitalize()
            result.append(ReplayPlayerInfo(display_name=bot_type, is_bot=True))
        else:
            user = db.query(User).filter(User.id == pid_str).first()
            name = (user.nickname or user.email or "Player") if user else "Player"
            result.append(ReplayPlayerInfo(display_name=name, is_bot=False))
    return result


def _date_key(room: GameSession) -> str:
    return room.created_at.strftime("%Y-%m-%d") if room.created_at else ""


def _month_day(room: GameSession) -> str:
    return room.created_at.strftime("%m_%d") if room.created_at else "00_00"


def _build_nn_map(
    games: list[GameSession],
    resolved: dict[str, list[ReplayPlayerInfo]],
) -> dict[str, int]:
    asc = sorted(games, key=lambda g: g.created_at)
    counts: dict[tuple[str, tuple[str, ...]], int] = {}
    nn_map: dict[str, int] = {}
    for g in asc:
        infos = resolved[str(g.id)]
        key = (_date_key(g), tuple(p.display_name for p in infos))
        counts[key] = counts.get(key, 0) + 1
        nn_map[str(g.id)] = counts[key]
    return nn_map


def _build_display_label(
    room: GameSession,
    infos: list[ReplayPlayerInfo],
    nn: int,
) -> str:
    md = _month_day(room)
    parts = [p.display_name for p in infos]
    return f"{md}_{'_'.join(parts)}_{nn:02d}"


def _resolve_winner(room: GameSession, infos: list[ReplayPlayerInfo]) -> str | None:
    if not room.winner_id:
        return None
    wid = str(room.winner_id)
    for pid, info in zip(room.players or [], infos):
        if str(pid) == wid:
            return info.display_name
    return None


@router.get("/", response_model=ReplayListResponse)
async def list_replays(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    player: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    games = (
        db.query(GameSession)
        .filter(GameSession.status == "FINISHED")
        .order_by(GameSession.created_at.desc())
        .all()
    )

    games = [g for g in games if os.path.exists(get_replay_file_path(g.id))]

    resolved: dict[str, list[ReplayPlayerInfo]] = {
        str(g.id): _resolve_player_infos(g, db) for g in games
    }
    nn_map = _build_nn_map(games, resolved)

    if player is not None:
        q = player.strip().lower()
        if q:
            games = [
                g
                for g in games
                if any(p.display_name.lower() == q for p in resolved[str(g.id)])
            ]

    total_items = len(games)
    total_pages = (total_items + size - 1) // size if total_items else 0

    start = (page - 1) * size
    end = start + size
    page_slice = games[start:end]

    items: list[ReplayListItem] = []
    for offset, g in enumerate(page_slice):
        infos = resolved[str(g.id)]
        human_names = sorted([p.display_name for p in infos if not p.is_bot])
        items.append(
            ReplayListItem(
                index=start + offset + 1,
                game_id=g.id,
                display_label=_build_display_label(g, infos, nn_map[str(g.id)]),
                human_player_names=human_names,
                played_date=_date_key(g),
                created_at=g.created_at,
                num_players=len(infos),
                winner=_resolve_winner(g, infos),
                players=infos,
            )
        )

    return ReplayListResponse(
        replays=items,
        page=page,
        size=size,
        total_items=total_items,
        total_pages=total_pages,
    )


@router.get("/{game_id}", response_model=ReplayDetailResponse)
async def get_replay_detail(
    game_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room or room.status != "FINISHED":
        raise HTTPException(status_code=404, detail="replay_not_found")

    path = get_replay_file_path(game_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="replay_file_not_found")

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload: dict[str, Any] = json.load(handle)
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="replay_file_not_found")

    infos = _resolve_player_infos(room, db)

    all_finished = (
        db.query(GameSession)
        .filter(GameSession.status == "FINISHED")
        .order_by(GameSession.created_at.desc())
        .all()
    )
    all_finished = [g for g in all_finished if os.path.exists(get_replay_file_path(g.id))]
    resolved: dict[str, list[ReplayPlayerInfo]] = {str(room.id): infos}
    for g in all_finished:
        if str(g.id) not in resolved:
            resolved[str(g.id)] = _resolve_player_infos(g, db)
    nn_map = _build_nn_map(all_finished, resolved)
    nn = nn_map.get(str(room.id), 1)

    entries = payload.get("entries") or []
    frames: list[ReplayFrame] = []
    for entry in entries:
        rich = entry.get("rich_state")
        if not isinstance(rich, dict):
            continue
        frames.append(
            ReplayFrame(
                frame_index=len(frames),
                step=entry.get("step"),
                action=entry.get("action"),
                commentary=entry.get("commentary"),
                rich_state=rich,
            )
        )

    return ReplayDetailResponse(
        game_id=room.id,
        display_label=_build_display_label(room, infos, nn),
        players=infos,
        replay_frames=frames,
        total_frames=len(frames),
        final_scores=payload.get("final_scores") or [],
    )
