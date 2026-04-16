"""TDD: Bot turn delay respects game speed setting."""
import uuid
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.game_service import GameService


def _make_engine_mock(role_selection=False):
    """Create a mock engine with action mask."""
    engine = MagicMock()
    mask = [0] * 200
    if role_selection:
        mask[0] = 1  # role action valid
    else:
        mask[15] = 1  # non-role action valid
    engine.get_action_mask.return_value = mask
    engine.last_obs = {}
    engine.env.game.current_player_idx = 0
    engine.env.game.current_phase = None
    return engine


class TestBotDelayCalculation:
    """Verify that delay = base_delay / speed."""

    @pytest.mark.asyncio
    async def test_delay_at_speed_1(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 1)
        engine = _make_engine_mock(role_selection=False)

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(15, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(2.0)
        GameService._game_speed.pop(game_id, None)

    @pytest.mark.asyncio
    async def test_delay_at_speed_2(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 2)
        engine = _make_engine_mock(role_selection=False)

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(15, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(1.0)
        GameService._game_speed.pop(game_id, None)

    @pytest.mark.asyncio
    async def test_delay_at_speed_4(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 4)
        engine = _make_engine_mock(role_selection=False)

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(15, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(0.5)
        GameService._game_speed.pop(game_id, None)

    @pytest.mark.asyncio
    async def test_role_selection_delay_at_speed_4(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 4)
        engine = _make_engine_mock(role_selection=True)

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(0, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(0.75)
        GameService._game_speed.pop(game_id, None)


class TestPauseBlocksScheduling:
    @pytest.mark.asyncio
    async def test_pause_blocks_scheduling(self):
        """When paused=True, run_bot_turn should return without executing."""
        game_id = uuid.uuid4()
        GameService.set_game_paused(game_id, True)
        engine = _make_engine_mock()

        select_mock = MagicMock()
        with patch("app.services.bot_service.BotService._select_action_for_current_state", select_mock):
            from app.services.bot_service import BotService
            await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        select_mock.assert_not_called()
        GameService._game_paused.pop(game_id, None)

    @pytest.mark.asyncio
    async def test_resume_triggers_scheduling(self):
        """When paused=False (default), bot turn executes normally."""
        game_id = uuid.uuid4()
        GameService.set_game_paused(game_id, False)
        engine = _make_engine_mock()

        sleep_calls = []
        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(15, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1  # bot turn executed
        GameService._game_paused.pop(game_id, None)
