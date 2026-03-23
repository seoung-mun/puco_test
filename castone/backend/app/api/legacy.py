"""
Legacy API — endpoints at /api/* that match the frontend's expected interface.
All game state is managed by the SessionManager singleton.
"""
import random
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../PuCo_RL")))
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.session_manager import session
from app.services.state_serializer import serialize_game_state, compute_score_breakdown, TILE_TO_STR
import app.services.action_translator as tr
from configs.constants import Role, Good, BuildingType

router = APIRouter()

# ------------------------------------------------------------------ #
#  Bot agent catalogue (defined in code; UI only selects from this)   #
# ------------------------------------------------------------------ #

BOT_AGENTS = [
    {"type": "random", "name": "Random Bot"},
    {"type": "ppo",    "name": "PPO Bot"},
]

_VALID_BOT_TYPES: set = {b["type"] for b in BOT_AGENTS}


# ------------------------------------------------------------------ #
#  Helpers                                                             #
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
    # Check game over
    if result["done"]:
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
    for _ in range(200):   # safety limit
        if session.game_over:
            break
        idx = game.current_player_idx
        if idx not in session.bot_players:
            break   # human's turn
        # Pick a random valid action
        mask = session.game.get_action_mask()
        valid = [i for i, v in enumerate(mask) if v]
        if not valid:
            break
        action = random.choice(valid)
        action_name, params = _action_to_history(action, game, session)
        result = session.game.step(action)
        session.add_history(action_name, params)
        if result["done"]:
            session.game_over = True
            break


# ------------------------------------------------------------------ #
#  Pydantic request bodies                                             #
# ------------------------------------------------------------------ #

class NewGameBody(BaseModel):
    num_players: int = 3
    player_names: List[str] = []

class BotSetBody(BaseModel):
    player: str          # "player_0", "player_1", …
    bot_type: str = "random"

class MultiplayerInitBody(BaseModel):
    host_name: str

class LobbyJoinBody(BaseModel):
    key: str
    name: str
    role: str = "player"

class LobbyAddBotBody(BaseModel):
    key: str
    host_name: str
    bot_name: str
    bot_type: str = "random"

class LobbyRemoveBotBody(BaseModel):
    key: str
    host_name: str
    bot_name: str

class LobbyStartBody(BaseModel):
    key: str
    name: str

class HeartbeatBody(BaseModel):
    key: str
    name: str

class SelectRoleBody(BaseModel):
    player: str
    role: str

class SettlePlantationBody(BaseModel):
    player: str
    plantation: str
    use_hospice: bool = False

class MayorColonistBody(BaseModel):
    player: str
    target_type: str   # "island" | "city"
    target_index: int

class MayorFinishBody(BaseModel):
    player: str

class SellBody(BaseModel):
    good: str

class CraftsmanPrivBody(BaseModel):
    good: str

class LoadShipBody(BaseModel):
    player: str
    good: str
    ship_index: int
    use_wharf: bool = False

class CaptainPassBody(BaseModel):
    player: str

class DiscardGoodsBody(BaseModel):
    player: str
    protected: List[str] = []
    single_extra: Optional[str] = None

class BuildBody(BaseModel):
    player: str
    building: str


# ------------------------------------------------------------------ #
#  Server / state endpoints                                            #
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
def heartbeat(body: HeartbeatBody):
    session.heartbeat(body.key, body.name)
    return {"ok": True}


# ------------------------------------------------------------------ #
#  Single-player setup                                                 #
# ------------------------------------------------------------------ #

@router.post("/set-mode/single")
def set_mode_single():
    session.reset()
    session.mode = "single"
    return {"ok": True}


@router.post("/new-game")
def new_game(body: NewGameBody):
    names = body.player_names
    if not names:
        names = [f"Player {i+1}" for i in range(body.num_players)]
    # Pad/trim to num_players
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
def bot_set(body: BotSetBody):
    _require_game()
    if body.bot_type not in _VALID_BOT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown bot type '{body.bot_type}'. Valid: {sorted(_VALID_BOT_TYPES)}")
    try:
        idx = int(body.player.split("_")[-1])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid player identifier")
    num_players = session.game.env.game.num_players
    if idx < 0 or idx >= num_players:
        raise HTTPException(status_code=400, detail=f"Player index {idx} out of range for {num_players}-player game")
    session.bot_players[idx] = body.bot_type
    return {"ok": True}


@router.post("/run-bots")
def run_bots():
    _require_game()
    _run_pending_bots()
    return serialize_game_state(session)


# ------------------------------------------------------------------ #
#  Multiplayer lobby                                                   #
# ------------------------------------------------------------------ #

@router.post("/multiplayer/init")
def multiplayer_init(body: MultiplayerInitBody):
    key = session.init_multiplayer(body.host_name)
    return {"key": key, **session.server_info}


@router.post("/lobby/join")
def lobby_join(body: LobbyJoinBody):
    ok = session.lobby_join(body.key, body.name)
    if not ok:
        raise HTTPException(status_code=403, detail="Invalid key")
    return session.server_info


@router.post("/lobby/add-bot")
def lobby_add_bot(body: LobbyAddBotBody):
    ok = session.lobby_add_bot(body.key, body.host_name, body.bot_name, body.bot_type)
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")
    return session.server_info


@router.post("/lobby/remove-bot")
def lobby_remove_bot(body: LobbyRemoveBotBody):
    ok = session.lobby_remove_bot(body.key, body.host_name, body.bot_name)
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")
    return session.server_info


@router.post("/lobby/start")
def lobby_start(body: LobbyStartBody):
    try:
        session.lobby_start(body.key, body.name)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return session.server_info


# ------------------------------------------------------------------ #
#  Game actions                                                        #
# ------------------------------------------------------------------ #

@router.post("/action/select-role")
def action_select_role(body: SelectRoleBody):
    _require_game()
    try:
        action = tr.select_role(body.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("select_role", {"player": body.player, "role": body.role})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/pass")
def action_pass():
    _require_game()
    game = session.game.env.game
    player_name = session.player_names[game.current_player_idx] if game.current_player_idx < len(session.player_names) else f"player_{game.current_player_idx}"
    _step(tr.pass_action())
    session.add_history("pass", {"player": player_name})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/use-hacienda")
def action_use_hacienda():
    _require_game()
    player_name = _current_player_name()
    _step(tr.use_hacienda())
    session.add_history("use_hacienda", {"player": player_name})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/settle-plantation")
def action_settle_plantation(body: SettlePlantationBody):
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


@router.post("/action/mayor-place-colonist")
def action_mayor_place(body: MayorColonistBody):
    _require_game()
    try:
        action = tr.mayor_toggle(body.target_type, body.target_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("mayor_place_colonist", {"player": body.player, "target": f"{body.target_type}_{body.target_index}"})
    return serialize_game_state(session)


@router.post("/action/mayor-pickup-colonist")
def action_mayor_pickup(body: MayorColonistBody):
    _require_game()
    try:
        action = tr.mayor_toggle(body.target_type, body.target_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("mayor_pickup_colonist", {"player": body.player, "target": f"{body.target_type}_{body.target_index}"})
    return serialize_game_state(session)


@router.post("/action/mayor-finish-placement")
def action_mayor_finish(body: MayorFinishBody):
    _require_game()
    _step(tr.pass_action())
    session.add_history("mayor_finish_placement", {"player": body.player})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/sell")
def action_sell(body: SellBody):
    _require_game()
    game = session.game.env.game
    player_name = session.player_names[game.current_player_idx] if game.current_player_idx < len(session.player_names) else f"player_{game.current_player_idx}"
    try:
        action = tr.sell(body.good)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("sell", {"player": player_name, "good": body.good})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/craftsman-privilege")
def action_craftsman_priv(body: CraftsmanPrivBody):
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


@router.post("/action/load-ship")
def action_load_ship(body: LoadShipBody):
    _require_game()
    game = session.game.env.game
    player = game.players[game.current_player_idx]
    good_enum = tr.GOOD_MAP.get(body.good.lower())
    if body.use_wharf:
        qty = player.goods.get(good_enum, 0) if good_enum else 0
        ship_cap = "wharf"
    else:
        ship = game.cargo_ships[body.ship_index]
        qty = min(player.goods.get(good_enum, 0) if good_enum else 0, ship.capacity - ship.current_load)
        ship_cap = str(ship.capacity)
    try:
        action = tr.load_ship(body.good, body.ship_index, body.use_wharf)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _step(action)
    session.add_history("load_ship", {
        "player": body.player,
        "good": body.good,
        "ship_capacity": ship_cap,
        "quantity": str(qty),
    })
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/captain-pass")
def action_captain_pass(body: CaptainPassBody):
    _require_game()
    _step(tr.pass_action())
    session.add_history("captain_pass", {"player": body.player})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/discard-goods")
def action_discard_goods(body: DiscardGoodsBody):
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


@router.post("/action/build")
def action_build(body: BuildBody):
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
