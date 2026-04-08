from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.game_service import GameService
from app.services.session_manager import SessionManager


def test_game_service_start_game_passes_bot_control_modes():
    game_id = uuid4()
    room = MagicMock()
    room.id = game_id
    room.title = "Control Mode Test"
    room.status = "WAITING"
    room.players = ["human-1", "BOT_ppo", "BOT_random"]
    room.model_versions = {}
    room.host_id = "human-1"

    engine = MagicMock()
    engine.get_action_mask.return_value = [0] * 200
    engine.env.game.governor_idx = 0
    engine.get_state.return_value = {}

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = room

    service = GameService(db)

    with patch("app.services.game_service.create_game_engine", return_value=engine) as mock_create:
        with patch.object(GameService, "_build_model_versions_snapshot", return_value={}):
            with patch.object(GameService, "_build_rich_state", return_value={"action_mask": [0] * 200}):
                with patch.object(GameService, "_store_game_meta"):
                    with patch.object(GameService, "_sync_to_redis"):
                        with patch.object(GameService, "_schedule_next_bot_turn_if_needed"):
                            with patch("app.services.game_service.ReplayLogger.initialize_game"):
                                service.start_game(game_id)

    assert mock_create.call_count == 1
    assert mock_create.call_args.kwargs["num_players"] == 3
    assert mock_create.call_args.kwargs["player_control_modes"] == [0, 1, 1]
    GameService.active_engines.pop(game_id, None)


def test_session_manager_start_game_passes_bot_control_modes():
    session = SessionManager()
    session.reset()
    session.mode = "single"
    session.player_names = ["Human", "Bot (ppo)", "Bot (random)"]
    session.bot_players = {1: "ppo", 2: "random"}

    engine = MagicMock()

    with patch("app.services.engine_gateway.create_game_engine", return_value=engine) as mock_create:
        session.start_game()

    assert mock_create.call_count == 1
    assert mock_create.call_args.kwargs["num_players"] == 3
    assert mock_create.call_args.kwargs["player_control_modes"] == [0, 1, 1]
