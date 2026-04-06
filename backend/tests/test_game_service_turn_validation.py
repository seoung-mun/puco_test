from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.game_service import GameService


def test_process_action_rejects_wrong_bot_actor_for_bot_turn():
    game_id = uuid4()
    engine = MagicMock()
    engine.env.game.current_player_idx = 1
    GameService.active_engines[game_id] = engine

    room = MagicMock()
    room.players = ["HUMAN", "BOT_ppo", "BOT_random"]

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = room

    service = GameService(db)

    try:
        with pytest.raises(ValueError, match="Not your turn"):
            service.process_action(game_id, "BOT_random", 15)
    finally:
        GameService.active_engines.pop(game_id, None)


def test_process_action_rejects_human_actor_during_bot_turn():
    game_id = uuid4()
    engine = MagicMock()
    engine.env.game.current_player_idx = 2
    GameService.active_engines[game_id] = engine

    room = MagicMock()
    room.players = ["HUMAN", "BOT_ppo", "BOT_random"]

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = room

    service = GameService(db)

    try:
        with pytest.raises(ValueError, match="Not your turn"):
            service.process_action(game_id, "HUMAN", 15)
    finally:
        GameService.active_engines.pop(game_id, None)
