"""
Legacy API — 공통 의존성, 인증, 내부 헬퍼 함수.
"""
import hmac
import os
import random
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../PuCo_RL")))

from typing import Any, Dict

from fastapi import Depends, Header, HTTPException

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


def require_internal_key(x_api_key: str = Header(...)):
    """INTERNAL_API_KEY 환경변수와 일치하는 X-API-Key 헤더가 없으면 403."""
    if not INTERNAL_API_KEY or not hmac.compare_digest(x_api_key, INTERNAL_API_KEY):
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
    return result


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

    elif action == 105:        # hacienda_draw
        return "use_hacienda", {"player": player_name}

    else:
        return "pass", {"player": player_name}


def _run_pending_bots():
    """Run bot turns until a human player's turn (or game over)."""
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
            break
