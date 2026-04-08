from __future__ import annotations

from typing import Dict, List, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import GameSession, User
from app.services.agent_registry import (
    require_valid_bot_type,
    resolve_bot_type_from_actor_id,
    resolve_model_artifact,
)
from app.services.engine_gateway import EngineWrapper
from app.services.model_registry import (
    build_artifact_fingerprint,
    build_human_snapshot,
    enrich_actor_snapshot,
)
from app.services.state_serializer import serialize_game_state_from_engine


def resolve_player_names_and_bots(db: Session, room: GameSession) -> Tuple[List[str], Dict[int, str]]:
    players = room.players or []
    player_names: List[str] = []
    bot_players: Dict[int, str] = {}
    for i, player_id in enumerate(players):
        pid = str(player_id)
        if pid.startswith("BOT_"):
            bot_type = require_valid_bot_type(resolve_bot_type_from_actor_id(pid))
            player_names.append(f"Bot ({bot_type})")
            bot_players[i] = bot_type
        else:
            user = db.query(User).filter(User.id == player_id).first()
            name = (user.nickname or user.email or f"Player {i}") if user else f"Player {i}"
            player_names.append(name)
    return player_names, bot_players


def build_player_control_modes(room: GameSession) -> List[int]:
    players = room.players or []
    return [1 if str(player_id).startswith("BOT_") else 0 for player_id in players]


def build_rich_state(db: Session, game_id: UUID, engine: EngineWrapper, room: GameSession) -> Dict:
    player_names, bot_players = resolve_player_names_and_bots(db, room)
    state = serialize_game_state_from_engine(
        engine=engine,
        player_names=player_names,
        game_id=str(game_id),
        bot_players=bot_players,
    )
    state["model_versions"] = dict(room.model_versions or {})
    return state


def build_replay_players_snapshot(room: GameSession, player_names: List[str]) -> List[Dict]:
    players_snapshot: List[Dict] = []
    model_versions = room.model_versions or {}
    for idx, actor_id in enumerate(room.players or []):
        actor_key = f"player_{idx}"
        model_info = model_versions.get(actor_key) or {}
        display_name = player_names[idx] if idx < len(player_names) else actor_key
        actor_id_str = str(actor_id)
        players_snapshot.append(
            {
                "player": idx,
                "actor_id": actor_id_str,
                "display_name": display_name,
                "actor_type": model_info.get("actor_type", "bot" if actor_id_str.startswith("BOT_") else "human"),
                "bot_type": model_info.get("bot_type"),
                "artifact_name": model_info.get("artifact_name"),
                "metadata_source": model_info.get("metadata_source"),
                "fingerprint": model_info.get("fingerprint"),
            }
        )
    return players_snapshot


def build_model_versions_snapshot(room: GameSession) -> Dict[str, Dict]:
    players = room.players or []
    snapshot: Dict[str, Dict] = {}
    for idx, player_id in enumerate(players):
        pid = str(player_id)
        key = f"player_{idx}"
        if pid.startswith("BOT_"):
            bot_type = require_valid_bot_type(resolve_bot_type_from_actor_id(pid))
            artifact = resolve_model_artifact(bot_type)
            if artifact is None:
                snapshot[key] = enrich_actor_snapshot(
                    {
                        "actor_type": "bot",
                        "bot_type": bot_type,
                        "family": bot_type,
                        "policy_tag": "champion",
                        "artifact_name": bot_type,
                        "checkpoint_filename": None,
                        "architecture": None,
                        "metadata_source": "builtin",
                        "fingerprint": build_artifact_fingerprint(),
                    }
                )
            else:
                snapshot[key] = artifact.to_snapshot(bot_type=bot_type)
        else:
            snapshot[key] = build_human_snapshot(pid)
    return snapshot


def resolve_actor_model_info(room: GameSession | None, actor_id: str) -> Dict | None:
    if room is None:
        return None
    for idx, player_id in enumerate(room.players or []):
        if str(player_id) == str(actor_id):
            return (room.model_versions or {}).get(f"player_{idx}")
    return None
