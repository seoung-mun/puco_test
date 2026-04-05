"""
Legacy API — 공통 의존성, 인증, 내부 헬퍼 함수.
"""
import hmac
import os
import random
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../PuCo_RL")))

from typing import Any, Dict

from fastapi import Header, HTTPException

from app.services.session_manager import session
from app.services.state_serializer import TILE_TO_STR
from app.services.bot_service import BotService
from app.services.agent_registry import bot_agents_list, valid_bot_types
from configs.constants import Role, Good, BuildingType

# ------------------------------------------------------------------ #
#  Internal API key                                                    #
# ------------------------------------------------------------------ #

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

BOT_AGENTS = bot_agents_list()         # [{"type": "ppo", "name": "PPO Bot"}, ...]
_VALID_BOT_TYPES: set = valid_bot_types()  # {"ppo", "hppo", "random", ...}


def require_internal_key(x_api_key: str | None = Header(default=None)):
    """INTERNAL_API_KEY 환경변수가 설정된 경우에만 X-API-Key 헤더를 검증한다.
    키가 설정되지 않은 경우(개발 환경)에는 모든 요청을 허용한다."""
    if not INTERNAL_API_KEY:
        return  # 키 미설정 시 인증 생략
    if not x_api_key or not hmac.compare_digest(x_api_key, INTERNAL_API_KEY):
        raise HTTPException(status_code=403, detail="Forbidden")


# ------------------------------------------------------------------ #
#  Common game helpers                                                 #
# ------------------------------------------------------------------ #

def _require_game():
    if not session.game_exists or session.game is None:
        raise HTTPException(status_code=400, detail="No active game")


def _current_player_name() -> str:
    """현재 턴 플레이어의 표시 이름을 반환한다."""
    idx = session.game.env.game.current_player_idx
    return session.player_names[idx] if idx < len(session.player_names) else f"player_{idx}"


def _step(action: int) -> Dict[str, Any]:
    """Execute one engine step and return updated game state."""
    mask = session.game.get_action_mask()
    if not (0 <= action < len(mask)) or not mask[action]:
        raise HTTPException(status_code=400, detail=f"Invalid action {action} for current state")
    result = session.game.step(action)
    # 자연 종료(terminated)만 game_over로 처리, truncation은 무시
    if result.get("terminated", result["done"]):
        session.game_over = True
    # 주의: publish는 호출자가 add_history() 이후에 직접 호출해야 history가 포함됨
    return result


def _publish_state_update():
    """액션 완료 후 WebSocket 클라이언트에 상태를 push한다."""
    try:
        from app.services.state_serializer import serialize_game_state
        from app.core.redis import sync_redis_client as redis_client
        from app.services.ws_manager import manager
        import json
        import asyncio

        state = serialize_game_state(session)
        mask = session.game.get_action_mask() if session.game else []
        payload = json.dumps({"type": "STATE_UPDATE", "data": state, "action_mask": mask})
        channel = f"game:{session.session_id}:events"
        redis_published = False

        try:
            redis_client.publish(channel, payload)
            redis_published = True
        except Exception:
            redis_published = False

        if not redis_published:
            # 동일 프로세스 WS 브로드캐스트 (Redis publish 실패 시 fallback)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(manager.broadcast_to_game(session.session_id, json.loads(payload)))
            except RuntimeError:
                pass  # 동기 컨텍스트에서는 무시
    except Exception:
        pass  # 브로드캐스트 실패는 게임 진행에 영향 없음


def _action_to_history(action: int, game, sess) -> tuple:
    """액션 인덱스를 히스토리 (action_name, params) 로 변환한다."""
    player_idx = game.current_player_idx
    player_name = sess.player_names[player_idx] if player_idx < len(sess.player_names) else f"player_{player_idx}"

    if action <= 7:            # select_role
        role_name = Role(action).name.lower()
        return "select_role", {"player": player_name, "role": role_name}

    elif action <= 13:         # settle_plantation (face-up index 0-5)
        idx = action - 8
        tile = game.face_up_plantations[idx]
        plantation = TILE_TO_STR.get(tile, "unknown")
        return "settle_plantation", {"player": player_name, "plantation": plantation}

    elif action == 14:         # settle_quarry
        return "settle_plantation", {"player": player_name, "plantation": "quarry"}

    elif action == 15:         # pass
        return "pass", {"player": player_name}

    elif action <= 38:         # build
        bt = BuildingType(action - 16)
        return "build", {"player": player_name, "building": bt.name.lower()}

    elif action <= 43:         # sell
        good = Good(action - 39)
        return "sell", {"player": player_name, "good": good.name.lower()}

    elif action <= 58:         # load_ship (ship_idx * 5 + good_value)
        offset = action - 44
        ship_idx = offset // 5
        good = Good(offset % 5)
        ship = game.cargo_ships[ship_idx]
        player = game.players[player_idx]
        qty = min(player.goods.get(good, 0), ship.capacity - ship.current_load)
        return "load_ship", {
            "player": player_name,
            "good": good.name.lower(),
            "ship_capacity": str(ship.capacity),
            "quantity": str(qty),
        }

    elif action <= 63:         # load_wharf
        good = Good(action - 59)
        player = game.players[player_idx]
        qty = player.goods.get(good, 0)
        return "load_ship", {
            "player": player_name,
            "good": good.name.lower(),
            "ship_capacity": "wharf",
            "quantity": str(qty),
        }

    elif action <= 68:         # store_windrose (64-68)
        good = Good(action - 64)
        return "store_windrose", {"player": player_name, "good": good.name.lower()}

    elif action <= 80:         # mayor_island (69-80, slot 0-11)
        slot_idx = action - 69
        return "mayor_toggle_island", {"player": player_name, "slot": str(slot_idx)}

    elif action <= 92:         # mayor_city (81-92, slot 0-11)
        slot_idx = action - 81
        return "mayor_toggle_city", {"player": player_name, "slot": str(slot_idx)}

    elif action <= 97:         # craftsman_privilege (93-97)
        good = Good(action - 93)
        return "craftsman_privilege", {"player": player_name, "good": good.name.lower()}

    elif action == 105:        # hacienda_draw
        return "use_hacienda", {"player": player_name}

    elif action <= 110:        # store_warehouse (106-110)
        good = Good(action - 106)
        return "store_warehouse", {"player": player_name, "good": good.name.lower()}

    else:
        return "pass", {"player": player_name}


def _run_pending_bots():
    """Run bot turns until a human player's turn (or game over)."""
    # 사람 액션 완료 후 현재 상태(history 포함) 즉시 push
    _publish_state_update()

    if session.game_over:
        return
    game = session.game.env.game
    engine = session.game  # EngineWrapper

    # Mayor phase toggle 카운터: 봇이 무한 toggle에 빠지는 것을 방지
    mayor_toggle_count: Dict[int, int] = {}
    MAX_MAYOR_TOGGLES = 30

    from configs.constants import Phase

    for _ in range(5000):   # safety limit
        if session.game_over:
            break
        idx = game.current_player_idx
        if idx not in session.bot_players:
            break   # human's turn
        bot_type = session.bot_players[idx]
        mask = engine.get_action_mask()
        if not any(mask):
            break

        is_mayor = (game.current_phase == Phase.MAYOR)
        if is_mayor:
            mayor_toggle_count.setdefault(idx, 0)
            if mayor_toggle_count[idx] >= MAX_MAYOR_TOGGLES and mask[15]:
                action = 15  # 강제 pass
                mayor_toggle_count[idx] = 0
            else:
                phase_id = engine.last_info.get("current_phase_id", 9) if engine.last_info else 9
                game_context = {
                    "vector_obs": engine.last_obs,
                    "engine_instance": game,
                    "action_mask": mask,
                    "phase_id": phase_id,
                }
                try:
                    action = BotService.get_action(bot_type, game_context)
                except Exception:
                    valid = [i for i, v in enumerate(mask) if v]
                    action = random.choice(valid) if valid else 15
                if 69 <= action <= 92:
                    mayor_toggle_count[idx] += 1
                else:
                    mayor_toggle_count[idx] = 0
        else:
            mayor_toggle_count.clear()
            phase_id = engine.last_info.get("current_phase_id", 9) if engine.last_info else 9
            game_context = {
                "vector_obs": engine.last_obs,
                "engine_instance": game,
                "action_mask": mask,
                "phase_id": phase_id,
            }
            try:
                action = BotService.get_action(bot_type, game_context)
            except Exception:
                valid = [i for i, v in enumerate(mask) if v]
                action = random.choice(valid) if valid else 15

        action_name, params = _action_to_history(action, game, session)
        result = engine.step(action)
        session.add_history(action_name, params)
        if result.get("terminated", result["done"]):
            session.game_over = True
            _publish_state_update()
            break
        _publish_state_update()
