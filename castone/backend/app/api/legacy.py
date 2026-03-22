"""
Legacy API — endpoints at /api/* that match the frontend's expected interface.
All game state is managed by the SessionManager singleton.
"""
import random
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.session_manager import session
from app.services.state_serializer import serialize_game_state, compute_score_breakdown
import app.services.action_translator as tr

router = APIRouter()


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _require_game():
    if not session.game_exists or session.game is None:
        raise HTTPException(status_code=400, detail="No active game")


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
        result = session.game.step(action)
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
    try:
        idx = int(body.player.split("_")[-1])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid player identifier")
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
    action = tr.select_role(body.role)
    _step(action)
    session.add_history("select_role", {"player": body.player, "role": body.role})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/pass")
def action_pass():
    _require_game()
    _step(tr.pass_action())
    session.add_history("pass", {})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/use-hacienda")
def action_use_hacienda():
    _require_game()
    _step(tr.use_hacienda())
    session.add_history("use_hacienda", {})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/settle-plantation")
def action_settle_plantation(body: SettlePlantationBody):
    _require_game()
    game = session.game.env.game
    action = tr.settle_plantation(body.plantation, game.face_up_plantations)
    _step(action)
    session.add_history("settle_plantation", {"player": body.player, "plantation": body.plantation})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/mayor-place-colonist")
def action_mayor_place(body: MayorColonistBody):
    _require_game()
    action = tr.mayor_toggle(body.target_type, body.target_index)
    _step(action)
    session.add_history("mayor_place_colonist", {"player": body.player, "target": f"{body.target_type}_{body.target_index}"})
    return serialize_game_state(session)


@router.post("/action/mayor-pickup-colonist")
def action_mayor_pickup(body: MayorColonistBody):
    _require_game()
    action = tr.mayor_toggle(body.target_type, body.target_index)
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
    action = tr.sell(body.good)
    _step(action)
    session.add_history("sell", {"good": body.good})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/craftsman-privilege")
def action_craftsman_priv(body: CraftsmanPrivBody):
    _require_game()
    action = tr.craftsman_privilege(body.good)
    _step(action)
    session.add_history("craftsman_privilege", {"good": body.good})
    _run_pending_bots()
    return serialize_game_state(session)


@router.post("/action/load-ship")
def action_load_ship(body: LoadShipBody):
    _require_game()
    action = tr.load_ship(body.good, body.ship_index, body.use_wharf)
    _step(action)
    session.add_history("load_ship", {"player": body.player, "good": body.good})
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
    action = tr.build(body.building)
    _step(action)
    session.add_history("build", {"player": body.player, "building": body.building})
    _run_pending_bots()
    return serialize_game_state(session)
