"""
Legacy API — 게임 액션 엔드포인트.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.services.session_manager import session
from app.services.state_serializer import serialize_game_state
import app.services.action_translator as tr

from .deps import require_internal_key, _require_game, _current_player_name, _step, _run_pending_bots
from .schemas import (
    SelectRoleBody,
    SettlePlantationBody,
    MayorColonistBody,
    MayorFinishBody,
    SellBody,
    CraftsmanPrivBody,
    LoadShipBody,
    CaptainPassBody,
    DiscardGoodsBody,
    BuildBody,
)

router = APIRouter(prefix="/action")


@router.post("/select-role")
def action_select_role(body: SelectRoleBody, _=Depends(require_internal_key)):
    _require_game()
    try:
        action = tr.select_role(body.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("select_role", {"player": body.player, "role": body.role})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/pass")
def action_pass(_=Depends(require_internal_key)):
    _require_game()
    game = session.game.env.game
    player_name = (
        session.player_names[game.current_player_idx]
        if game.current_player_idx < len(session.player_names)
        else f"player_{game.current_player_idx}"
    )
    _step(tr.pass_action())
    session.add_history("pass", {"player": player_name})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/use-hacienda")
def action_use_hacienda(_=Depends(require_internal_key)):
    _require_game()
    player_name = _current_player_name()
    _step(tr.use_hacienda())
    session.add_history("use_hacienda", {"player": player_name})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/settle-plantation")
def action_settle_plantation(body: SettlePlantationBody, _=Depends(require_internal_key)):
    _require_game()
    player_name = _current_player_name()
    game = session.game.env.game
    try:
        action = tr.settle_plantation(body.plantation, game.face_up_plantations)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("settle_plantation", {"player": player_name, "plantation": body.plantation})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/mayor-place-colonist")
def action_mayor_place(body: MayorColonistBody, _=Depends(require_internal_key)):
    _require_game()
    try:
        action = tr.mayor_toggle(body.target_type, body.target_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history(
        "mayor_place_colonist",
        {"player": body.player, "target": f"{body.target_type}_{body.target_index}"},
    )
    return serialize_game_state(session)


@router.post("/mayor-pickup-colonist")
def action_mayor_pickup(body: MayorColonistBody, _=Depends(require_internal_key)):
    _require_game()
    try:
        action = tr.mayor_toggle(body.target_type, body.target_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history(
        "mayor_pickup_colonist",
        {"player": body.player, "target": f"{body.target_type}_{body.target_index}"},
    )
    return serialize_game_state(session)


@router.post("/mayor-finish-placement")
def action_mayor_finish(body: MayorFinishBody, _=Depends(require_internal_key)):
    _require_game()
    _step(tr.pass_action())
    session.add_history("mayor_finish_placement", {"player": body.player})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/sell")
def action_sell(body: SellBody, _=Depends(require_internal_key)):
    _require_game()
    game = session.game.env.game
    player_name = (
        session.player_names[game.current_player_idx]
        if game.current_player_idx < len(session.player_names)
        else f"player_{game.current_player_idx}"
    )
    try:
        action = tr.sell(body.good)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("sell", {"player": player_name, "good": body.good})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/craftsman-privilege")
def action_craftsman_priv(body: CraftsmanPrivBody, _=Depends(require_internal_key)):
    _require_game()
    player_name = _current_player_name()
    try:
        action = tr.craftsman_privilege(body.good)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("craftsman_privilege", {"player": player_name, "good": body.good})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/load-ship")
def action_load_ship(body: LoadShipBody, _=Depends(require_internal_key)):
    _require_game()
    game = session.game.env.game
    player = game.players[game.current_player_idx]
    good_enum = tr.GOOD_MAP.get(body.good.lower())
    if body.use_wharf:
        qty = player.goods.get(good_enum, 0) if good_enum else 0
        ship_cap = "wharf"
    else:
        ship = game.cargo_ships[body.ship_index]
        qty = min(
            player.goods.get(good_enum, 0) if good_enum else 0,
            ship.capacity - ship.current_load,
        )
        ship_cap = str(ship.capacity)
    try:
        action = tr.load_ship(body.good, body.ship_index, body.use_wharf)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history(
        "load_ship",
        {"player": body.player, "good": body.good, "ship_capacity": ship_cap, "quantity": str(qty)},
    )
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/captain-pass")
def action_captain_pass(body: CaptainPassBody, _=Depends(require_internal_key)):
    _require_game()
    _step(tr.pass_action())
    session.add_history("captain_pass", {"player": body.player})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/discard-goods")
def action_discard_goods(body: DiscardGoodsBody, _=Depends(require_internal_key)):
    _require_game()
    mask = session.game.get_action_mask()
    actions = tr.discard_sequence(body.protected, body.single_extra, mask)
    for action in actions:
        if session.game_over:
            break
        result = _step(action)
        if result["done"]:
            session.game_over = True
    session.add_history("discard_goods", {"player": body.player})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/build")
def action_build(body: BuildBody, _=Depends(require_internal_key)):
    _require_game()
    player_name = _current_player_name()
    try:
        action = tr.build(body.building)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("build", {"player": player_name, "building": body.building})
    _run_pending_bots()
    return serialize_game_state(session)
