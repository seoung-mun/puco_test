"""
Legacy API — 게임 액션 엔드포인트.
"""
import logging
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../PuCo_RL")))

from fastapi import APIRouter, Depends, HTTPException

from app.services.session_manager import session
from app.services.state_serializer import serialize_game_state
import app.services.action_translator as tr

logger = logging.getLogger(__name__)

from .deps import require_internal_key, _require_game, _current_player_name, _step, _run_pending_bots
from .schemas import (
    SelectRoleBody,
    SettlePlantationBody,
    MayorColonistBody,
    MayorFinishBody,
    MayorPlaceAmountBody,
    MayorDistributeBody,
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
    """Mayor 배치 종료 — 남은 슬롯을 모두 0으로 자동 스킵한다.
    Mayor 페이즈에서 pass(15)는 금지됨. 대신 action 69(현재 슬롯에 0 배치)를
    반복하여 자연스럽게 페이즈를 종료시킨다.
    """
    _require_game()
    from configs.constants import Phase

    original_player_idx = session.game.env.game.current_player_idx
    MAX_ITER = 30  # 슬롯 최대 24개 + 여유
    for _ in range(MAX_ITER):
        if session.game_over:
            break
        game = session.game.env.game
        if game.current_phase != Phase.MAYOR:
            break  # Mayor 페이즈 종료
        if game.current_player_idx != original_player_idx:
            break  # 다음 플레이어 차례 — 봇이 처리
        mask = session.game.get_action_mask()
        if not mask[69]:
            # min_place > 0: 반드시 이주민을 배치해야 하는 슬롯
            raise HTTPException(
                status_code=400,
                detail="현재 슬롯에 이주민을 배치해야 합니다. 배치 없이 종료할 수 없습니다."
            )
        result = session.game.step(69)  # 현재 슬롯에 0 배치 → 다음 슬롯으로
        if result.get("terminated", result["done"]):
            session.game_over = True
            break

    session.add_history("mayor_finish_placement", {"player": body.player})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/mayor-place")
def action_mayor_place_amount(body: MayorPlaceAmountBody, _=Depends(require_internal_key)):
    """Mayor 순차 배치 — 현재 슬롯에 N개 이주민을 배치한다 (amount: 0-3).
    amount=0: 현재 슬롯 스킵, amount=1: 1명 배치, etc.
    """
    _require_game()
    player_name = _current_player_name()
    if not (0 <= body.amount <= 3):
        raise HTTPException(status_code=400, detail="amount must be 0-3")
    action = 69 + body.amount
    _step(action)
    session.add_history("mayor_place", {"player": player_name, "amount": body.amount})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/mayor-distribute")
def action_mayor_distribute(body: MayorDistributeBody, _=Depends(require_internal_key)):
    """인간 플레이어 Mayor 토글 UI — 24슬롯 배치 확정.
    distribution[i]: 슬롯 i에 배치할 이주민 수 (0-3).
    인덱스 0-11=island, 12-23=city(index-12).
    """
    _require_game()
    from configs.constants import Phase

    if len(body.distribution) != 24:
        raise HTTPException(status_code=400, detail="distribution 길이는 정확히 24여야 합니다.")
    if any(v < 0 or v > 3 for v in body.distribution):
        raise HTTPException(status_code=400, detail="각 슬롯 값은 0-3 범위여야 합니다.")

    game = session.game.env.game
    if game.current_phase != Phase.MAYOR:
        raise HTTPException(status_code=400, detail="Mayor 페이즈가 아닙니다.")

    original_player_idx = game.current_player_idx
    player_name = (
        session.player_names[original_player_idx]
        if original_player_idx < len(session.player_names)
        else f"player_{original_player_idx}"
    )

    # 이전 호출에서 일부 슬롯이 처리된 경우(에러 후 재시도), 엔진의 현재 위치에서 재개
    start_idx = game.mayor_placement_idx

    for slot_i in range(start_idx, len(body.distribution)):
        if session.game_over:
            break
        game = session.game.env.game
        if game.current_phase != Phase.MAYOR:
            break
        if game.current_player_idx != original_player_idx:
            break
        amount = body.distribution[slot_i]
        mask = session.game.get_action_mask()
        action = 69 + amount
        if action >= len(mask) or not mask[action]:
            valid_amounts = [a - 69 for a in range(69, 73) if a < len(mask) and mask[a]]

            # 진단: 현재 슬롯의 capacity와 내용물 파악
            from configs.constants import TileType, BuildingType, BUILDING_DATA
            _idx = game.mayor_placement_idx
            _is_island = _idx < 12
            _slot_idx = _idx if _is_island else _idx - 12
            _p = game.players[original_player_idx]
            _capacity = 0
            _slot_info = "none"
            if _is_island:
                if _slot_idx < len(_p.island_board):
                    _tile = _p.island_board[_slot_idx]
                    _capacity = 0 if _tile.tile_type == TileType.EMPTY else 1
                    _slot_info = f"island:{_tile.tile_type.name.lower()}"
                else:
                    _slot_info = "island:out_of_range"
            else:
                if _slot_idx < len(_p.city_board):
                    _b = _p.city_board[_slot_idx]
                    _capacity = BUILDING_DATA.get(_b.building_type, (0, 0, 0))[2]
                    _slot_info = f"city:{_b.building_type.name.lower()}"
                else:
                    _slot_info = "city:out_of_range"

            logger.warning(
                "mayor-distribute 슬롯 검증 실패 | player=%s slot=%d attempted=%d "
                "valid=%s slot_capacity=%d slot_info=%s unplaced=%d dist=%s",
                player_name, slot_i, amount, valid_amounts,
                _capacity, _slot_info, _p.unplaced_colonists, body.distribution,
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"슬롯 {slot_i}: {amount}명 배치 불가",
                    "slot": slot_i,
                    "attempted": amount,
                    "valid_amounts": valid_amounts,
                    "slot_capacity": _capacity,
                    "slot_info": _slot_info,
                    "unplaced_colonists": _p.unplaced_colonists,
                    "distribution_received": body.distribution,
                },
            )
        result = session.game.step(action)
        if result.get("terminated", result["done"]):
            session.game_over = True
            break

    session.add_history("mayor_distribute", {"player": player_name, "distribution": body.distribution})
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
