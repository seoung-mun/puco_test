import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.dependencies import get_db
from app.schemas.game import AddBotRequest, GameAction
from app.services.game_service import GameService, StaleRevisionError
from app.api.deps import get_current_user
from app.db.models import User, GameSession
from app.services.state_serializer import compute_score_breakdown
from app.services.lobby_manager import lobby_manager, _build_lobby_payload
from app.services.agent_registry import make_bot_player_id, require_valid_bot_type
from app.services.canonical_action import _describe_action
from app.services.replay_logger import load_replay_payload

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/{game_id}/start")
async def start_game(
    game_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Game not found")
    # Host can start even as spectator (e.g. bot-game); non-host must be a player
    is_host = str(current_user.id) == str(room.host_id)
    if not is_host:
        if str(current_user.id) not in (room.players or []):
            raise HTTPException(status_code=403, detail="You are not a player in this game")
        raise HTTPException(status_code=403, detail="Only the host can start the game")

    service = GameService(db)
    try:
        result = service.start_game(game_id)
        await lobby_manager.broadcast_game_started(str(game_id), result["state"])
        return {"status": "started", "state": result["state"], "action_mask": result["action_mask"]}
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)

@router.post("/{game_id}/action")
async def perform_action(
    game_id: UUID,
    action_data: GameAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # IDOR: verify caller is a player in this game
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Game not found")
    if str(current_user.id) not in (room.players or []):
        raise HTTPException(status_code=403, detail="You are not a player in this game")

    actor_id = str(current_user.id)
    service = GameService(db)
    try:
        load_result = await service.ensure_engine_loaded(game_id)
        if load_result.state == "blocked":
            raise HTTPException(
                status_code=409,
                detail={"error": "recovery_blocked", "reason": load_result.reason},
            )

        action_int = action_data.payload.action_index
        submitted_canonical = action_data.payload.canonical_id
        intent_id = action_data.payload.action_intent_id
        expected_revision = action_data.payload.expected_state_revision
        decoded = _describe_action(action_int, state={})
        decoded_canonical = decoded.get("canonical_id") if decoded else None

        if submitted_canonical is not None and decoded_canonical is not None and submitted_canonical != decoded_canonical:
            logger.warning(
                "[ACTION_TRACE] channel_action_canonical_mismatch game=%s actor=%s action=%s submitted=%s decoded=%s",
                game_id, actor_id, action_int, submitted_canonical, decoded_canonical,
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "canonical_id_mismatch",
                    "submitted_canonical_id": submitted_canonical,
                    "decoded_canonical_id": decoded_canonical,
                    "action_index": action_int,
                },
            )

        if submitted_canonical is None:
            match_status = "missing"
        elif submitted_canonical == decoded_canonical:
            match_status = "match"
        else:
            match_status = "mismatch"

        logger.warning(
            "[ACTION_TRACE] channel_action_request game=%s actor=%s action=%s "
            "submitted_canonical_id=%s decoded_canonical_id=%s match=%s payload_keys=%s schema=%s",
            game_id,
            actor_id,
            action_int,
            submitted_canonical,
            decoded_canonical,
            match_status,
            sorted(action_data.payload.model_dump().keys()),
            action_data.payload.schema_version,
        )

        result = service.process_action(
            game_id,
            actor_id,
            action_int,
            canonical_id=decoded_canonical,
            action_intent_id=intent_id,
            expected_state_revision=expected_revision,
        )
        response = {
            "status": "success",
            "state": result["state"],
            "action_mask": result["action_mask"],
        }
        if result.get("duplicate") is True:
            response["duplicate"] = True
        return response
    except StaleRevisionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "stale_state",
                "expected_state_revision": exc.expected,
                "current_state_revision": exc.current,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def perform_mayor_distribution(
    game_id: UUID,
):
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy Mayor distribution endpoint is removed. "
            "Use POST /api/puco/game/{game_id}/action with slot-direct "
            "action_index 120-131 (island) or 140-151 (city)."
        ),
    )


router.post("/{game_id}/mayor-distribute")(perform_mayor_distribution)


@router.post("/{game_id}/add-bot")
async def add_bot(
    game_id: UUID,
    body: AddBotRequest = AddBotRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Game not found")
    if str(current_user.id) not in (room.players or []):
        raise HTTPException(status_code=403, detail="You are not a player in this game")
    if str(current_user.id) != str(room.host_id):
        raise HTTPException(status_code=403, detail="Only the host can manage bots")
    if room.status != "WAITING":
        raise HTTPException(status_code=409, detail="Game has already started")
    players = list(room.players or [])
    if len(players) >= 3:
        raise HTTPException(status_code=409, detail="최대 3명까지 참가할 수 있습니다")

    try:
        bot_type = require_valid_bot_type(body.bot_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    slot_index = len(players)
    players.append(make_bot_player_id(bot_type))
    room.players = players
    db.commit()
    db.refresh(room)

    lobby_payload = _build_lobby_payload(room, db)
    await lobby_manager.broadcast(str(game_id), {"type": "LOBBY_UPDATE", **lobby_payload})

    return {"status": "ok", "slot_index": slot_index, "bot_type": bot_type}


@router.delete("/{game_id}/bots/{slot_index}")
async def remove_bot(
    game_id: UUID,
    slot_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Game not found")
    if str(current_user.id) not in (room.players or []):
        raise HTTPException(status_code=403, detail="You are not a player in this game")
    if str(current_user.id) != str(room.host_id):
        raise HTTPException(status_code=403, detail="Only the host can manage bots")
    if room.status != "WAITING":
        raise HTTPException(status_code=409, detail="Game has already started")

    players = list(room.players or [])
    if slot_index < 0 or slot_index >= len(players):
        raise HTTPException(status_code=404, detail="Bot slot not found")

    target_player = str(players[slot_index])
    if not target_player.startswith("BOT_"):
        raise HTTPException(status_code=400, detail="Selected slot is not a bot")

    players.pop(slot_index)
    room.players = players
    db.commit()
    db.refresh(room)

    lobby_payload = _build_lobby_payload(room, db)
    await lobby_manager.broadcast(str(game_id), {"type": "LOBBY_UPDATE", **lobby_payload})

    return {"status": "ok", "slot_index": slot_index, "bot_type": target_player[4:]}


@router.get("/{game_id}/final-score")
async def get_final_score(
    game_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Game not found")
    is_player = str(current_user.id) in (room.players or [])
    is_host = str(current_user.id) == str(room.host_id)
    if not (is_player or is_host):
        raise HTTPException(status_code=403, detail="You are not allowed to view this game's final score")

    engine = GameService.active_engines.get(game_id)
    service = GameService(db)
    if room.status == "PROGRESS":
        load_result = await service.ensure_engine_loaded(game_id)
        if load_result.state == "blocked":
            raise HTTPException(
                status_code=409,
                detail={"error": "recovery_blocked", "reason": load_result.reason},
            )
        engine = GameService.active_engines.get(game_id)

    player_names, _ = service._resolve_player_names_and_bots(room)
    if engine:
        return compute_score_breakdown(engine.env.game, player_names)

    replay_payload = load_replay_payload(game_id=game_id, db=db) or {}
    result_summary = replay_payload.get("result_summary")
    if isinstance(result_summary, dict):
        return result_summary
    raise HTTPException(status_code=404, detail="Game engine not found (game may not have started)")
