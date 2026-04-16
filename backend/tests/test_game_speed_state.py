"""Unit tests for GameService speed/pause in-memory state."""
import uuid
from app.services.game_service import GameService


class TestGameSpeedState:
    def test_default_speed_is_1(self):
        game_id = uuid.uuid4()
        assert GameService.get_game_speed(game_id) == 1

    def test_set_speed(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 4)
        assert GameService.get_game_speed(game_id) == 4
        GameService._game_speed.pop(game_id, None)  # cleanup

    def test_default_paused_is_false(self):
        game_id = uuid.uuid4()
        assert GameService.get_game_paused(game_id) is False

    def test_set_paused(self):
        game_id = uuid.uuid4()
        GameService.set_game_paused(game_id, True)
        assert GameService.get_game_paused(game_id) is True
        GameService._game_paused.pop(game_id, None)  # cleanup

    def test_cleanup_on_delete(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 2)
        GameService.set_game_paused(game_id, True)
        GameService.clear_playback_state(game_id)
        assert GameService.get_game_speed(game_id) == 1
        assert GameService.get_game_paused(game_id) is False
