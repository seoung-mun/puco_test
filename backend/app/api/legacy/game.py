"""
Legacy API — 게임 상태 조회 + 단일 플레이어 설정 엔드포인트.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.services.session_manager import session
from app.services.state_serializer import serialize_game_state, compute_score_breakdown

from .deps import (
    BOT_AGENTS,
    _VALID_BOT_TYPES,
    require_internal_key,
    _require_game,
    _run_pending_bots,
)
from .schemas import NewGameBody, BotSetBody, HeartbeatBody

router = APIRouter()


# ------------------------------------------------------------------ #
#  Read-only state endpoints                                           #
# ------------------------------------------------------------------ #

@router.get("/bot-types")
def get_bot_types():
    return BOT_AGENTS


@router.get("/server-info")
def get_server_info():
    return session.server_info


@router.get("/game-state")
def get_game_state():
    _require_game()
    return serialize_game_state(session)


@router.get("/final-score")
def get_final_score():
    _require_game()
    game = session.game.env.game
    return compute_score_breakdown(game, session.player_names)


@router.post("/heartbeat")
def heartbeat(body: HeartbeatBody, _=Depends(require_internal_key)):
    session.heartbeat(body.key, body.name)
    return {"ok": True}


# ------------------------------------------------------------------ #
#  Single-player setup                                                 #
# ------------------------------------------------------------------ #

@router.post("/set-mode/single")
def set_mode_single(_=Depends(require_internal_key)):
    session.reset()
    session.mode = "single"
    return {"ok": True}


@router.post("/new-game")
def new_game(body: NewGameBody, _=Depends(require_internal_key)):
    names = body.player_names
    if not names:
        names = [f"Player {i+1}" for i in range(body.num_players)]
    while len(names) < body.num_players:
        names.append(f"Player {len(names)+1}")
    names = names[:body.num_players]

    session.player_names = names
    session.bot_players = {}
    session.game_over = False
    session.history = []
    session.round = 1
    session.start_game()
    return serialize_game_state(session)


@router.post("/bot/set")
def bot_set(body: BotSetBody, _=Depends(require_internal_key)):
    _require_game()
    if body.bot_type not in _VALID_BOT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown bot type '{body.bot_type}'. Valid: {sorted(_VALID_BOT_TYPES)}",
        )
    try:
        idx = int(body.player.split("_")[-1])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid player identifier")
    num_players = session.game.env.game.num_players
    if idx < 0 or idx >= num_players:
        raise HTTPException(
            status_code=400,
            detail=f"Player index {idx} out of range for {num_players}-player game",
        )
    session.bot_players[idx] = body.bot_type
    return {"ok": True}


@router.post("/run-bots")
def run_bots(_=Depends(require_internal_key)):
    _require_game()
    _run_pending_bots()
    return serialize_game_state(session)
