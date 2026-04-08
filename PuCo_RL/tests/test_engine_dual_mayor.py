"""
RED Tests: Engine Dual-Mode Mayor Phase

이 테스트들은 엔진이 아직 dual-mode를 지원하지 않으므로 모두 실패해야 한다.
실패 이유는 ImportError가 아니라 비즈니스 규칙 위반(AssertionError, ValueError, AttributeError)이다.

비즈니스 규칙:
1. Bot은 69-71(strategy)만, Human은 72-75(sequential)만 사용 가능
2. 잘못된 action type 사용 시 ValueError
3. Bot strategy는 1-step으로 Mayor 완료
4. Human sequential은 unplaced_colonists==0까지 phase 유지
5. Mixed game에서 각 player가 자기 mode에 맞는 mask만 받음
"""
import os
import sys
import copy
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from env.engine import PuertoRicoGame
from configs.constants import (
    Phase, Role, Good, TileType, BuildingType,
    BUILDING_DATA, MayorStrategy,
)


# ────────────────────────────────────────────────────
# Fixtures & Helpers
# ────────────────────────────────────────────────────

def _make_game_with_control_modes(modes=None):
    """
    ControlMode를 받아 게임을 생성한다.
    modes: list[int] — 0=HUMAN, 1=BOT (ControlMode enum 값)
    None이면 기본값(all HUMAN)
    """
    game = PuertoRicoGame(num_players=3, player_control_modes=modes)
    return game


def _force_mayor_phase(game, player_idx=0, colonists=3):
    """
    게임을 Mayor phase로 강제 진입시키고,
    지정된 플레이어에게 colonist를 배치할 수 있는 상태로 만든다.
    테스트 전용 — 실제 게임 흐름 무시.
    """
    game.current_phase = Phase.MAYOR
    game.current_player_idx = player_idx
    game.active_role = Role.MAYOR
    game.active_role_player = player_idx
    game.players_taken_action = 0

    p = game.players[player_idx]

    # 보드가 비어있으면 place_plantation/build_building으로 추가
    if len(p.island_board) == 0:
        p.place_plantation(TileType.CORN_PLANTATION)
        p.place_plantation(TileType.CORN_PLANTATION)
    if len(p.city_board) == 0:
        p.build_building(BuildingType.SMALL_INDIGO_PLANT)

    # 모든 tile/building을 비활성화 (recall 시뮬레이션)
    for t in p.island_board:
        t.is_occupied = False
    for b in p.city_board:
        b.colonists = 0

    # colonist 설정
    p.unplaced_colonists = colonists
    game.mayor_placement_idx = 0
    game._skip_empty_mayor_slots(player_idx)

    return game


# ════════════════════════════════════════════════════
# Test Class 1: ControlMode 기본 동작
# ════════════════════════════════════════════════════

class TestControlModeBasics:
    """player_control_modes가 엔진에 올바르게 통합되는지 검증."""

    def test_engine_accepts_player_control_modes_parameter(self):
        """엔진 생성자가 player_control_modes를 받을 수 있어야 한다."""
        # ControlMode.HUMAN=0, ControlMode.BOT=1
        game = _make_game_with_control_modes([0, 1, 1])
        assert hasattr(game, "player_control_modes")
        assert game.player_control_modes == [0, 1, 1]

    def test_default_control_mode_is_all_human(self):
        """modes를 지정하지 않으면 모든 플레이어가 HUMAN(0)이어야 한다."""
        game = PuertoRicoGame(num_players=3)
        assert hasattr(game, "player_control_modes")
        assert game.player_control_modes == [0, 0, 0]

    def test_invalid_control_mode_raises_value_error(self):
        """유효하지 않은 mode 값(예: 99)은 ValueError를 발생시켜야 한다."""
        with pytest.raises(ValueError, match="[Cc]ontrol.*mode|[Ii]nvalid"):
            _make_game_with_control_modes([0, 99, 1])

    def test_control_modes_length_must_match_num_players(self):
        """modes 길이가 num_players와 다르면 ValueError."""
        with pytest.raises(ValueError):
            PuertoRicoGame(num_players=3, player_control_modes=[0, 1])


# ════════════════════════════════════════════════════
# Test Class 2: Mayor Action Mask 분기
# ════════════════════════════════════════════════════

def _make_env_with_mayor(control_modes, player_idx=0, colonists=2):
    """Mayor phase가 설정된 PuertoRicoEnv를 반환하는 헬퍼.
    env.reset()으로 AEC state를 초기화한 후 game state를 Mayor로 덮어쓴다."""
    from env.pr_env import PuertoRicoEnv
    env = PuertoRicoEnv(num_players=3, player_control_modes=control_modes)
    env.reset()
    # game state를 Mayor로 강제 전환
    _force_mayor_phase(env.game, player_idx=player_idx, colonists=colonists)
    env.agent_selection = f"player_{player_idx}"
    return env


class TestMayorActionMaskDualMode:
    """Mayor phase에서 control mode에 따라 올바른 action mask가 생성되는지 검증."""

    def test_human_mayor_mask_has_72_to_75_valid(self):
        """Human 플레이어의 Mayor mask에서 72-75 중 적어도 하나가 valid해야 한다."""
        env = _make_env_with_mayor([0, 1, 1], player_idx=0, colonists=2)
        mask = env.valid_action_mask()
        assert any(mask[72:76]), \
            f"Human player must have at least one valid action in 72-75, got mask[72:76]={mask[72:76]}"

    def test_human_mayor_mask_has_69_to_71_invalid(self):
        """Human 플레이어의 Mayor mask에서 69-71은 모두 invalid이어야 한다."""
        env = _make_env_with_mayor([0, 1, 1], player_idx=0, colonists=2)
        mask = env.valid_action_mask()
        assert not any(mask[69:72]), \
            f"Human player must NOT have strategy actions 69-71 valid, got mask[69:72]={mask[69:72]}"

    def test_bot_mayor_mask_has_69_to_71_all_valid(self):
        """Bot 플레이어의 Mayor mask에서 69-71은 모두 valid이어야 한다."""
        env = _make_env_with_mayor([1, 0, 0], player_idx=0, colonists=2)
        mask = env.valid_action_mask()
        assert mask[69] and mask[70] and mask[71], \
            f"Bot player must have ALL strategy actions 69-71 valid, got mask[69:72]={mask[69:72]}"

    def test_bot_mayor_mask_has_72_to_75_invalid(self):
        """Bot 플레이어의 Mayor mask에서 72-75는 모두 invalid이어야 한다."""
        env = _make_env_with_mayor([1, 0, 0], player_idx=0, colonists=2)
        mask = env.valid_action_mask()
        assert not any(mask[72:76]), \
            f"Bot player must NOT have sequential actions 72-75 valid, got mask[72:76]={mask[72:76]}"


# ════════════════════════════════════════════════════
# Test Class 3: Action Dispatch 강제 (Wrong Mode)
# ════════════════════════════════════════════════════

class TestMayorActionDispatchEnforcement:
    """잘못된 mode의 action 사용 시 엔진이 거부하는지 검증."""

    def test_human_using_strategy_action_raises_error(self):
        """Human 플레이어가 action 70(strategy)을 사용하면 거부되어야 한다.
        pr_env는 invalid action에 대해 termination + negative reward로 처리."""
        env = _make_env_with_mayor([0, 1, 1], player_idx=0, colonists=2)
        env.step(70)
        assert env.terminations["player_0"] or env.rewards["player_0"] < 0, \
            "Human using strategy action(70) must be rejected (termination or negative reward)"

    def test_bot_using_sequential_action_raises_error(self):
        """Bot 플레이어가 action 73(place 1)을 사용하면 거부."""
        env = _make_env_with_mayor([1, 0, 0], player_idx=0, colonists=2)
        env.step(73)
        assert env.terminations["player_0"] or env.rewards["player_0"] < 0, \
            "Bot using sequential action(73) must be rejected"


# ════════════════════════════════════════════════════
# Test Class 4: Phase Completion 규칙
# ════════════════════════════════════════════════════

class TestMayorPhaseCompletion:
    """Mayor phase가 control mode에 따라 올바르게 완료되는지 검증."""

    def test_bot_strategy_completes_mayor_in_one_step(self):
        """Bot이 strategy action(69) 한 번으로 Mayor가 완료되어야 한다.
        완료 = 해당 플레이어의 unplaced_colonists == 0 이고 다음 플레이어로 넘어감."""
        game = _make_game_with_control_modes([1, 0, 0])
        _force_mayor_phase(game, player_idx=0, colonists=2)

        pre_player = game.current_player_idx
        assert pre_player == 0

        # action_mayor_strategy 호출 (직접 엔진 메서드 테스트)
        game.action_mayor_strategy(0, MayorStrategy.CAPTAIN_FOCUS)

        # 배치 완료 확인
        assert game.players[0].unplaced_colonists == 0, \
            f"After strategy action, unplaced_colonists must be 0, got {game.players[0].unplaced_colonists}"

        # phase 전환 확인: 다음 플레이어로 넘어갔거나, phase가 바뀌었어야 함
        phase_advanced = (
            game.current_player_idx != 0  # 다음 플레이어
            or game.current_phase != Phase.MAYOR  # phase 종료
        )
        assert phase_advanced, \
            "After bot strategy, Mayor must advance to next player or end phase"

    def test_human_sequential_preserves_phase_until_all_placed(self):
        """Human이 1개씩 배치할 때, unplaced_colonists > 0이면 Mayor phase가 유지되어야 한다."""
        game = _make_game_with_control_modes([0, 1, 1])
        _force_mayor_phase(game, player_idx=0, colonists=3)

        # 첫 번째 슬롯에 1개 배치 (action_mayor_place는 amount를 받음)
        game.action_mayor_place(0, 1)

        # colonist가 남아있으면 Mayor phase 유지
        if game.players[0].unplaced_colonists > 0:
            assert game.current_phase == Phase.MAYOR, \
                "Mayor phase must persist while human has unplaced colonists"
            assert game.current_player_idx == 0, \
                "Current player must stay the same during sequential placement"

    def test_human_zero_colonists_completes_immediately(self):
        """Human이 unplaced_colonists==0이면 배치할 것이 없어 Mayor가 즉시 완료되어야 한다."""
        game = _make_game_with_control_modes([0, 1, 1])
        _force_mayor_phase(game, player_idx=0, colonists=0)

        # colonists=0이면 _skip_empty_mayor_slots가 idx를 24로 보내거나 auto-complete
        # 어느 쪽이든 phase가 진행되어야 함
        phase_done = (
            game.mayor_placement_idx >= 24
            or game.current_player_idx != 0
            or game.current_phase != Phase.MAYOR
        )
        assert phase_done, \
            "Human with 0 colonists should auto-complete Mayor placement"


# ════════════════════════════════════════════════════
# Test Class 5: Mixed Game (Human + Bot 혼합)
# ════════════════════════════════════════════════════

class TestMixedGameMayor:
    """한 게임에서 Human과 Bot이 섞여 있을 때 Mayor가 정상 작동하는지 검증."""

    def test_mixed_game_bot_then_human_transitions(self):
        """[Bot, Human, Bot] 게임에서 Bot→Human→Bot 순서로 Mayor 진행.
        각 플레이어가 자기 mode에 맞게 처리되어야 한다."""
        modes = [1, 0, 1]  # Bot, Human, Bot
        game = _make_game_with_control_modes(modes)

        # 모든 플레이어에게 최소 보드 + colonist 설정
        for i in range(3):
            p = game.players[i]
            if len(p.island_board) == 0:
                p.place_plantation(TileType.CORN_PLANTATION)
            if len(p.city_board) == 0:
                p.build_building(BuildingType.SMALL_INDIGO_PLANT)
            for t in p.island_board:
                t.is_occupied = False
            for b in p.city_board:
                b.colonists = 0
            p.unplaced_colonists = 2

        game.current_phase = Phase.MAYOR
        game.current_player_idx = 0
        game.active_role = Role.MAYOR
        game.active_role_player = 0
        game.players_taken_action = 0
        game.mayor_placement_idx = 0
        game._skip_empty_mayor_slots(0)

        # Player 0 (Bot): strategy로 1-step 완료
        game.action_mayor_strategy(0, MayorStrategy.CAPTAIN_FOCUS)
        assert game.players[0].unplaced_colonists == 0

        # Player 1 (Human): sequential로 진행 — phase가 MAYOR이고 player가 1이어야 함
        if game.current_phase == Phase.MAYOR:
            assert game.current_player_idx == 1, \
                f"After bot 0 completes, current player should be 1 (human), got {game.current_player_idx}"
            # Human은 sequential로 배치해야 함
            assert game.player_control_modes[1] == 0, \
                "Player 1 must be HUMAN mode"

    def test_non_mayor_phase_unaffected_by_control_mode(self):
        """Mayor가 아닌 phase(Builder, Trader 등)에서는 control mode가 mask에 영향을 주지 않아야 한다."""
        from env.pr_env import PuertoRicoEnv
        env = PuertoRicoEnv(num_players=3, player_control_modes=[0, 1, 1])
        env.reset()
        # Builder phase로 전환
        env.game.current_phase = Phase.BUILDER
        env.game.current_player_idx = 0
        env.game.active_role = Role.BUILDER
        env.game.active_role_player = 0
        env.agent_selection = "player_0"

        mask = env.valid_action_mask()
        # Builder phase에서는 69-75가 모두 invalid (Mayor 전용)
        assert not any(mask[69:76]), \
            "Mayor actions (69-75) must be invalid outside Mayor phase"


# ════════════════════════════════════════════════════
# Test Class 6: action_mayor_strategy 존재 및 기본 검증
# ════════════════════════════════════════════════════

class TestActionMayorStrategyExists:
    """upstream에서 가져온 action_mayor_strategy가 엔진에 존재하고 올바르게 동작하는지."""

    def test_engine_has_action_mayor_strategy_method(self):
        """PuertoRicoGame에 action_mayor_strategy 메서드가 있어야 한다."""
        game = PuertoRicoGame(num_players=3)
        assert hasattr(game, "action_mayor_strategy"), \
            "PuertoRicoGame must have action_mayor_strategy method"
        assert callable(game.action_mayor_strategy)

    def test_strategy_places_all_colonists(self):
        """어떤 전략이든 실행 후 unplaced_colonists == 0이어야 한다."""
        for strategy in MayorStrategy:
            game = PuertoRicoGame(num_players=3)
            _force_mayor_phase(game, player_idx=0, colonists=2)

            game.action_mayor_strategy(0, strategy)
            assert game.players[0].unplaced_colonists == 0, \
                f"Strategy {strategy.name}: unplaced_colonists must be 0 after strategy execution"

    def test_three_strategies_produce_different_placements(self):
        """동일 보드에서 3가지 전략이 서로 다른 배치를 만들어야 한다 (최소 1쌍 차이)."""
        results = {}
        for strategy in MayorStrategy:
            game = PuertoRicoGame(num_players=3)
            p = game.players[0]

            # 전략 차이가 드러나는 충분한 보드 구성
            p.place_plantation(TileType.COFFEE_PLANTATION)
            p.place_plantation(TileType.INDIGO_PLANTATION)
            p.place_plantation(TileType.CORN_PLANTATION)
            p.build_building(BuildingType.WHARF)          # CAPTAIN_FOCUS
            p.build_building(BuildingType.OFFICE)         # TRADE_FACTORY_FOCUS
            p.build_building(BuildingType.UNIVERSITY)     # BUILDING_FOCUS
            p.build_building(BuildingType.COFFEE_ROASTER) # Production

            for t in p.island_board:
                t.is_occupied = False
            for b in p.city_board:
                b.colonists = 0

            # Mayor phase 설정
            game.current_phase = Phase.MAYOR
            game.current_player_idx = 0
            game.active_role = Role.MAYOR
            game.active_role_player = 0
            game.players_taken_action = 0
            p.unplaced_colonists = 5
            game.mayor_placement_idx = 0

            game.action_mayor_strategy(0, strategy)

            island_snapshot = [t.is_occupied for t in p.island_board]
            city_snapshot = [b.colonists for b in p.city_board]
            results[strategy] = (island_snapshot, city_snapshot)

        # 최소 1쌍은 달라야 함
        strategies = list(results.keys())
        any_different = False
        for i in range(len(strategies)):
            for j in range(i + 1, len(strategies)):
                if results[strategies[i]] != results[strategies[j]]:
                    any_different = True
                    break
        assert any_different, \
            "At least two strategies must produce different placements on the same board"
