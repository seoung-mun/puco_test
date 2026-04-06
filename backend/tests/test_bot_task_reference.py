import asyncio
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4

from app.services.game_service import GameService

class TestBotTaskReference:
    """asyncio.create_task 반환값이 참조 보존되는지 검증."""

    @pytest.mark.asyncio
    async def test_bot_task_stored_in_class_set(self):
        """_schedule_next_bot_turn_if_needed 호출 후 GameService._bot_tasks에 태스크가 등록되어야 한다."""
        # Setup: 클래스 변수 초기화
        if hasattr(GameService, '_bot_tasks'):
            GameService._bot_tasks.clear()
        else:
            GameService._bot_tasks = set()

        room = MagicMock()
        room.players = ["user1", "BOT_ppo", "BOT_random"]

        engine = MagicMock()
        engine.env.game.current_player_idx = 1  # BOT_ppo 차례

        db = MagicMock()
        service = GameService(db)

        # BotService.run_bot_turn이 즉시 끝나지 않도록 지연 시뮬레이션
        async def slow_run(*args, **kwargs):
            await asyncio.sleep(0.1)

        with patch('app.services.bot_service.BotService.run_bot_turn', side_effect=slow_run):
            service._schedule_next_bot_turn_if_needed(uuid4(), room, engine)
            
            # 태스크가 생성될 시간을 아주 잠깐 부여
            await asyncio.sleep(0.01)

            # 검증: _bot_tasks에 태스크가 존재해야 함
            assert hasattr(GameService, '_bot_tasks')
            assert len(GameService._bot_tasks) > 0
            
            # 태스크가 완료될 때까지 대기
            await asyncio.sleep(0.15)
            
            # 검증: 태스크 완료 후 자동으로 제거되어야 함
            assert len(GameService._bot_tasks) == 0
