import asyncio
import pytest
import numpy as np
import torch
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.bot_service import BotService, _extract_phase_id
from configs.constants import Phase

class TestBotServiceSafety:
    def test_extract_phase_id_edge_cases(self):
        # 1. 정상 케이스
        assert _extract_phase_id({"global_state": {"current_phase": 3}}) == 3
        # 2. Numpy scalar 케이스
        assert _extract_phase_id({"global_state": {"current_phase": np.int64(5)}}) == 5
        # 3. 누락된 키
        assert _extract_phase_id({"global_state": {}}) == 8
        # 4. None 값
        assert _extract_phase_id({"global_state": {"current_phase": None}}) == 8
        # 5. 범위 초과 클램핑
        assert _extract_phase_id({"global_state": {"current_phase": 15}}) == 9

    def test_build_input_snapshot_applies_backend_settler_guard(self):
        engine = MagicMock()
        raw_mask = [0] * 200
        raw_mask[8] = 1
        raw_mask[15] = 1
        engine.get_action_mask.return_value = raw_mask
        engine.last_obs = {"global_state": {"current_phase": int(Phase.SETTLER)}}

        player = MagicMock()
        player.empty_island_spaces = 1
        game = MagicMock()
        game.current_phase = Phase.SETTLER
        game.current_player_idx = 0
        game.players = [player]
        game.face_up_plantations = [1]
        game.quarry_stack = 8
        engine.env.game = game

        snapshot = BotService.build_input_snapshot(engine, "BOT_factory_rule")

        assert snapshot.action_mask[8] == 1
        assert snapshot.action_mask[15] == 0

    @pytest.mark.asyncio
    async def test_run_bot_turn_recovery_on_callback_failure(self):
        """콜백이 실패하더라도 랜덤 액션으로 재시도하여 흐름을 유지해야 한다."""
        engine = MagicMock()
        # mask[15]=1 (Pass), mask[69]=1 (Mayor)
        mask = [0]*200
        mask[15] = 1
        mask[69] = 1
        engine.get_action_mask.return_value = mask
        engine.last_obs = {"global_state": {"current_phase": 1}} # Mayor

        call_results = []
        async def failing_callback(gid, aid, action):
            call_results.append(action)
            if action == 15: # 봇이 Pass를 선택했다고 가정
                raise ValueError("Action 15 is invalid in Mayor phase")
            # 재시도 시 성공

        # BotService.get_action이 15를 반환하도록 조작
        with patch.object(BotService, 'get_action', return_value=15):
            with patch('asyncio.sleep', return_value=None): # 딜레이 스킵
                await BotService.run_bot_turn(
                    game_id="00000000-0000-0000-0000-000000000000",
                    engine=engine,
                    actor_id="BOT_ppo",
                    process_action_callback=failing_callback
                )

        # 첫 번째 15 실패 후, 69(또는 다른 유효한 수)로 재시도되었는지 확인
        assert len(call_results) >= 2
        assert call_results[0] == 15
        assert call_results[1] == 69
        assert mask[call_results[1]] == 1

    @pytest.mark.asyncio
    async def test_run_bot_turn_retry_uses_guarded_settler_mask(self):
        engine = MagicMock()
        raw_mask = [0] * 200
        raw_mask[8] = 1
        raw_mask[15] = 1
        engine.get_action_mask.return_value = raw_mask
        engine.last_obs = {"global_state": {"current_phase": int(Phase.SETTLER)}}

        player = MagicMock()
        player.empty_island_spaces = 1
        game = MagicMock()
        game.current_phase = Phase.SETTLER
        game.current_player_idx = 0
        game.players = [player]
        game.face_up_plantations = [1]
        game.quarry_stack = 8
        engine.env.game = game

        call_results = []

        async def failing_callback(_gid, _aid, action):
            call_results.append(action)
            if action == 0:
                raise ValueError("Action 0 is invalid in Settler phase")

        with patch.object(BotService, "get_action", return_value=0):
            with patch("asyncio.sleep", return_value=None):
                await BotService.run_bot_turn(
                    game_id="00000000-0000-0000-0000-000000000000",
                    engine=engine,
                    actor_id="BOT_factory_rule",
                    process_action_callback=failing_callback,
                )

        assert call_results == [0, 8]

class TestRunBotTurnTopLevelSafety:
    """run_bot_turn 최상위에서 예외가 발생해도 crash하지 않아야 한다."""

    @pytest.mark.asyncio
    async def test_engine_get_action_mask_error_caught(self):
        """engine.get_action_mask() 실패해도 코루틴이 예외 없이 종료."""
        engine = MagicMock()
        engine.get_action_mask.side_effect = RuntimeError("Engine corrupt")
        callback = MagicMock()

        # 예외가 외부로 전파되지 않아야 함 (Task 소멸 방지)
        await BotService.run_bot_turn(
            game_id="00000000-0000-0000-0000-000000000000",
            engine=engine,
            actor_id="BOT_random",
            process_action_callback=callback,
        )
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_engine_last_obs_none_caught(self):
        """engine.last_obs가 None이어도 코루틴이 예외 없이 종료."""
        engine = MagicMock()
        engine.get_action_mask.return_value = [0]*200
        engine.last_obs = None
        callback = MagicMock()

        await BotService.run_bot_turn(
            game_id="00000000-0000-0000-0000-000000000000",
            engine=engine,
            actor_id="BOT_ppo",
            process_action_callback=callback,
        )
        # Crash 없이 종료되면 성공
