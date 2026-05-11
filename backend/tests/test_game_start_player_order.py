import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.game_service import GameService
from app.services.game_service_support import shuffle_start_player_order


def test_shuffle_start_player_order_is_reproducible_for_same_seed():
    players = ["HOST", "GUEST", "BOT_ppo"]

    order_a = shuffle_start_player_order(players, game_seed=17)
    order_b = shuffle_start_player_order(players, game_seed=17)

    assert order_a == order_b


def test_shuffle_start_player_order_preserves_members_for_targeted_room():
    players = ["HOST", "GUEST", "BOT_ppo"]

    shuffled = shuffle_start_player_order(players, game_seed=23)

    assert sorted(shuffled) == sorted(players)


def test_shuffle_start_player_order_uses_known_seed_to_move_host_out_of_seat_zero():
    players = ["HOST", "GUEST", "BOT_ppo"]

    shuffled = shuffle_start_player_order(players, game_seed=29)

    assert shuffled == ["GUEST", "HOST", "BOT_ppo"]
    assert shuffled[0] != "HOST"


def test_shuffle_start_player_order_keeps_bot_only_room_unchanged():
    players = ["BOT_random", "BOT_random", "BOT_random"]

    shuffled = shuffle_start_player_order(players, game_seed=29)

    assert shuffled == players


def test_shuffle_start_player_order_keeps_one_human_two_bot_room_unchanged():
    players = ["HOST", "BOT_random", "BOT_ppo"]

    shuffled = shuffle_start_player_order(players, game_seed=31)

    assert shuffled == players


def test_start_game_uses_shuffled_player_order_before_engine_and_snapshots():
    game_id = uuid4()
    room = MagicMock()
    room.id = game_id
    room.title = "Targeted room"
    room.status = "WAITING"
    room.players = ["HOST", "GUEST", "BOT_ppo"]
    room.model_versions = {}
    room.host_id = "HOST"

    engine = MagicMock()
    engine.get_action_mask.return_value = [0] * 200
    engine.get_state.return_value = {}
    engine.initial_governor_idx = 0

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = room

    service = GameService(db)

    with patch("app.services.game_service.secrets.randbits", return_value=29):
        with patch("app.services.game_service.create_game_engine", return_value=engine) as mock_create:
            with patch("app.services.game_service.build_model_versions_snapshot", return_value={}) as mock_versions:
                with patch("app.services.game_service.build_rich_state", return_value={"action_mask": [0] * 200}):
                    with patch.object(GameService, "_store_game_meta"):
                        with patch.object(GameService, "_sync_to_redis"):
                            with patch.object(GameService, "_schedule_next_bot_turn_if_needed"):
                                with patch(
                                    "app.services.game_service.resolve_player_names_and_bots",
                                    return_value=(["Guest", "Host", "Bot"], {2: "ppo"}),
                                ):
                                    with patch(
                                        "app.services.game_service.build_replay_players_snapshot",
                                        return_value=[],
                                    ) as mock_replay_players:
                                        with patch("app.services.game_service.ReplayLogger.initialize_game"):
                                            service.start_game(game_id)

    assert room.players == ["GUEST", "HOST", "BOT_ppo"]
    assert mock_create.call_args.kwargs["player_control_modes"] == [0, 0, 1]
    assert mock_versions.call_args.args[0].players == ["GUEST", "HOST", "BOT_ppo"]
    assert mock_replay_players.call_args.args[0].players == ["GUEST", "HOST", "BOT_ppo"]
    GameService.active_engines.pop(game_id, None)


def test_start_game_keeps_original_player_order_when_precommit_setup_fails():
    game_id = uuid4()
    room = MagicMock()
    room.id = game_id
    room.title = "Targeted room"
    room.status = "WAITING"
    room.players = ["HOST", "GUEST", "BOT_ppo"]
    room.model_versions = {}
    room.host_id = "HOST"

    engine = MagicMock()
    engine.initial_governor_idx = 0

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = room

    service = GameService(db)

    with patch("app.services.game_service.secrets.randbits", return_value=29):
        with patch("app.services.game_service.create_game_engine", return_value=engine):
            with patch(
                "app.services.game_service.build_model_versions_snapshot",
                side_effect=RuntimeError("snapshot failed"),
            ):
                with pytest.raises(RuntimeError, match="snapshot failed"):
                    service.start_game(game_id)

    assert room.players == ["HOST", "GUEST", "BOT_ppo"]
    assert game_id not in GameService.active_engines
    assert game_id not in GameService._engine_revision
    db.commit.assert_not_called()
    db.rollback.assert_called_once()
