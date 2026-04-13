"""
State Serializer — converts PuertoRicoGame (engine.env.game) into the
rich GameState JSON format expected by the frontend.
"""
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from app.services.engine_gateway.constants import BUILDING_DATA, BuildingType, Phase, TileType
from app.services.state_serializer_support import (
    GOOD_TO_STR,
    PHASE_TO_STR,
    ROLE_TO_STR,
    TILE_TO_STR,
    building_name,
    compute_display_order,
    compute_score_breakdown,
    safe_int,
    serialize_common_board,
    serialize_player,
)

if TYPE_CHECKING:
    from app.engine_wrapper.wrapper import EngineWrapper
    from app.services.session_manager import SessionManager


def _build_mayor_meta(game: Any) -> Dict[str, Any]:
    """Build Mayor convenience fields when phase is MAYOR."""
    if game.current_phase != Phase.MAYOR:
        return {}
    player = game.players[game.current_player_idx]
    legal_island: List[int] = []
    legal_city: List[int] = []
    for i, t in enumerate(player.island_board):
        if t.tile_type != TileType.EMPTY and not t.is_occupied:
            legal_island.append(i)
    for i, b in enumerate(player.city_board):
        if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
            cap = BUILDING_DATA[b.building_type][2]
            if b.colonists < cap:
                legal_city.append(i)
    return {
        "mayor_phase_mode": "slot-direct",
        "mayor_remaining_colonists": player.unplaced_colonists,
        "mayor_legal_island_slots": legal_island,
        "mayor_legal_city_slots": legal_city,
    }


def serialize_game_state(session: "SessionManager") -> Dict[str, Any]:
    """Convert session + engine state into the full GameState dict."""
    game = session.game.env.game

    phase_str = "game_over" if session.game_over else PHASE_TO_STR.get(game.current_phase, "role_selection")

    player_key = f"player_{game.current_player_idx}"
    governor_key = f"player_{game.governor_idx}"
    player_order = [f"player_{i}" for i in range(game.num_players)]

    display_order = compute_display_order(game.governor_idx, game.num_players)
    players: Dict[str, Any] = {}
    for i, p in enumerate(game.players):
        name = session.player_names[i] if i < len(session.player_names) else f"Player {i}"
        players[f"player_{i}"] = serialize_player(p, game, name, i, display_order[i])

    meta = {
        "game_id": session.session_id,
        "round": session.game._round_count + 1,
        "step_count": getattr(session.game, "_step_count", 0),
        "num_players": game.num_players,
        "player_order": player_order,
        "governor": governor_key,
        "phase": phase_str,
        "phase_id": safe_int(game.current_phase, default=8),
        "active_role": ROLE_TO_STR.get(game.active_role) if game.active_role is not None else None,
        "active_player": player_key,
        "players_acted_this_phase": [],
        "end_game_triggered": session.game_over,
        "end_game_reason": None,
        "vp_supply_remaining": game.vp_chips,
        "captain_consecutive_passes": len(game._captain_passed_players),
        "bot_thinking": session.bot_thinking,
        "pass_action_index": 15,
        "hacienda_action_index": 105,
        **_build_mayor_meta(game),
    }

    decision = {
        "type": phase_str,
        "player": player_key,
        "note": "",
    }

    bot_players = {
        f"player_{idx}": bot_type
        for idx, bot_type in session.bot_players.items()
    }
    result_summary = compute_score_breakdown(game, session.player_names) if session.game_over else None

    return {
        "meta": meta,
        "common_board": serialize_common_board(game),
        "players": players,
        "decision": decision,
        "history": session.history,
        "bot_players": bot_players,
        "result_summary": result_summary,
    }


def serialize_game_state_from_engine(
    engine: "EngineWrapper",
    player_names: List[str],
    game_id: str = "",
    bot_players: Optional[Dict[int, str]] = None,
    history: Optional[List] = None,
) -> Dict[str, Any]:
    """
    EngineWrapper에서 직접 rich GameState JSON을 생성한다.
    SessionManager 없이 channel WebSocket / 테스트에서 사용한다.
    """
    game = engine.env.game
    if bot_players is None:
        bot_players = {}
    if history is None:
        history = []

    game_over = any(engine.env.terminations.values()) or any(engine.env.truncations.values())

    phase_str = "game_over" if game_over else PHASE_TO_STR.get(game.current_phase, "role_selection")

    player_key = f"player_{game.current_player_idx}"
    governor_key = f"player_{game.governor_idx}"
    player_order = [f"player_{i}" for i in range(game.num_players)]

    display_order = compute_display_order(game.governor_idx, game.num_players)
    players: Dict[str, Any] = {}
    for i, p in enumerate(game.players):
        name = player_names[i] if i < len(player_names) else f"Player {i}"
        players[f"player_{i}"] = serialize_player(p, game, name, i, display_order[i])

    action_mask = engine.get_action_mask()

    meta = {
        "game_id": game_id,
        "round": engine._round_count + 1,
        "step_count": engine._step_count,
        "num_players": game.num_players,
        "player_order": player_order,
        "governor": governor_key,
        "phase": phase_str,
        "phase_id": safe_int(game.current_phase, default=8),
        "active_role": ROLE_TO_STR.get(game.active_role) if game.active_role is not None else None,
        "active_player": player_key,
        "players_acted_this_phase": [],
        "end_game_triggered": game_over,
        "end_game_reason": None,
        "vp_supply_remaining": game.vp_chips,
        "captain_consecutive_passes": len(game._captain_passed_players),
        "bot_thinking": False,
        "pass_action_index": 15,
        "hacienda_action_index": 105,
        **_build_mayor_meta(game),
    }

    decision = {
        "type": phase_str,
        "player": player_key,
        "note": "",
    }

    bot_players_out = {
        f"player_{idx}": bot_type
        for idx, bot_type in bot_players.items()
    }
    result_summary = compute_score_breakdown(game, player_names) if game_over else None

    return {
        "meta": meta,
        "common_board": serialize_common_board(game),
        "players": players,
        "decision": decision,
        "history": history,
        "bot_players": bot_players_out,
        "result_summary": result_summary,
        "action_mask": action_mask,
    }


def serialize_compact_summary(engine: "EngineWrapper") -> Dict[str, Any]:
    """
    EngineWrapper에서 핵심 게임 지표만 추출하여 Adminer에서 읽기 쉬운
    compact JSON을 반환한다. GameLog.state_summary 컬럼에 저장된다.
    """
    game = engine.env.game

    phase_name = PHASE_TO_STR.get(game.current_phase, "unknown")
    active_role_name = ROLE_TO_STR.get(game.active_role) if game.active_role else None

    players_summary = {}
    for i, p in enumerate(game.players):
        goods = {GOOD_TO_STR[g]: v for g, v in p.goods.items() if v > 0}
        buildings = [
            building_name(b.building_type)
            for b in p.city_board
            if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
        ]
        plantations: dict[str, int] = {}
        for t in p.island_board:
            tname = TILE_TO_STR.get(t.tile_type, "empty")
            if tname == "empty":
                continue
            plantations[tname] = plantations.get(tname, 0) + 1

        players_summary[f"p{i}"] = {
            "doubloons": p.doubloons,
            "vp": p.vp_chips,
            "goods": goods,
            "buildings": buildings,
            "plantations": plantations,
            "colonists": p.total_colonists_owned,
            "empty_city": p.empty_city_spaces,
        }

    return {
        "phase": phase_name,
        "role": active_role_name,
        "current_player": game.current_player_idx,
        "governor": game.governor_idx,
        "vp_supply": game.vp_chips,
        "colonist_supply": game.colonists_supply,
        "colonist_ship": game.colonists_ship,
        "players": players_summary,
    }


__all__ = [
    "PHASE_TO_STR",
    "compute_display_order",
    "compute_score_breakdown",
    "serialize_compact_summary",
    "serialize_game_state",
    "serialize_game_state_from_engine",
]
