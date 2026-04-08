"""
MayorStrategyAdapter 단위 테스트.

봇의 Mayor strategy 선택(0/1/2)을 sequential placement action 시퀀스(69-72)로
변환하는 adapter를 검증한다.

TDD RED 단계: adapter 구현 전에 작성. 모든 테스트가 실패해야 정상.
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_mayor_strategy_adapter.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

import copy
import pytest

from app.engine_wrapper.wrapper import create_game_engine
from app.services.mayor_strategy_adapter import MayorStrategyAdapter
from configs.constants import (
    BuildingType,
    Good,
    MayorStrategy,
    Phase,
    TileType,
    BUILDING_DATA,
    LARGE_VP_BUILDINGS,
)


# ─── Helpers ───


def _prepare_engine_at_mayor(
    num_colonists: int = 5,
    island_tiles=None,
    city_buildings=None,
):
    """Mayor phase에 진입한 상태의 엔진을 반환한다.

    Args:
        num_colonists: 배치할 미배치 식민자 수
        island_tiles: 섬 보드에 놓을 TileType 리스트 (기본: corn, indigo, sugar)
        city_buildings: 도시 보드에 지을 BuildingType 리스트 (기본: SMALL_INDIGO_PLANT, GUILDHALL)
    """
    engine = create_game_engine(num_players=3)
    game = engine.env.game

    # force Mayor phase
    game.current_phase = Phase.MAYOR
    game.current_player_idx = 0
    game.active_role_player = 0
    game.players_taken_action = 0

    player = game.players[0]

    # clear boards
    player.island_board = []
    player.city_board = []

    # set up island
    if island_tiles is None:
        island_tiles = [
            TileType.CORN_PLANTATION,
            TileType.INDIGO_PLANTATION,
            TileType.SUGAR_PLANTATION,
        ]
    for tile in island_tiles:
        player.place_plantation(tile)

    # set up city
    if city_buildings is None:
        city_buildings = [
            BuildingType.SMALL_INDIGO_PLANT,
            BuildingType.GUILDHALL,
        ]
    for btype in city_buildings:
        player.build_building(btype)

    # set colonists
    player.unplaced_colonists = num_colonists

    # 다른 플레이어들도 최소한의 보드를 갖게 하여 Mayor turn이 정상 진행되도록 한다.
    # (보드가 비어 있으면 _init_mayor_placement에서 즉시 skip → _advance_phase_turn 연쇄)
    for p_idx in range(1, game.num_players):
        p = game.players[p_idx]
        p.island_board = []
        p.city_board = []
        p.place_plantation(TileType.CORN_PLANTATION)
        p.unplaced_colonists = 1

    # init sequential cursor
    game._init_mayor_placement(0)

    # PettingZoo AEC 상태 동기화
    env = engine.env
    env.agent_selection = f"player_{game.current_player_idx}"
    for agent in env.agents:
        env.terminations[agent] = False
        env.truncations[agent] = False
        env.rewards[agent] = 0.0
        env._cumulative_rewards[agent] = 0.0

    engine._refresh_cached_view()
    return engine


def _apply_actions(engine, actions: list[int]):
    """action 리스트를 engine에 순차 적용한다."""
    result = None
    for action in actions:
        result = engine.step(action)
    return result


# ─── Tests ───


class TestExpandReturnType:
    def test_expand_returns_list_of_ints(self):
        """expand()는 int 리스트를 반환하고 모든 원소가 69-72 범위여야 한다."""
        engine = _prepare_engine_at_mayor(num_colonists=3)
        adapter = MayorStrategyAdapter()

        actions = adapter.expand(
            strategy=0, game=engine.env.game, player_idx=0
        )

        assert isinstance(actions, list)
        assert len(actions) > 0
        for a in actions:
            assert isinstance(a, int), f"action {a} is not int"
            assert 69 <= a <= 72, f"action {a} out of range 69-72"


class TestCaptainFocusPriority:
    def test_expand_captain_focus_fills_large_vp_first(self):
        """CAPTAIN_FOCUS(0)에서 Large VP building에 colonist가 우선 배치된다."""
        engine = _prepare_engine_at_mayor(
            num_colonists=4,
            island_tiles=[TileType.CORN_PLANTATION, TileType.INDIGO_PLANTATION],
            city_buildings=[
                BuildingType.SMALL_INDIGO_PLANT,  # capacity 1
                BuildingType.GUILDHALL,            # capacity 1 (Large VP)
            ],
        )
        adapter = MayorStrategyAdapter()
        actions = adapter.expand(strategy=0, game=engine.env.game, player_idx=0)
        _apply_actions(engine, actions)

        player = engine.env.game.players[0]

        # GUILDHALL은 Large VP → 우선 배치
        guildhall_filled = False
        for b in player.city_board:
            if b.building_type == BuildingType.GUILDHALL:
                guildhall_filled = b.colonists > 0
                break
        assert guildhall_filled, "GUILDHALL (Large VP) should be filled with colonists"


class TestAllColonistsPlaced:
    def test_expand_all_colonists_placed(self):
        """어떤 전략이든 expand 후 순차 적용하면 unplaced_colonists == 0."""
        for strategy in [0, 1, 2]:
            engine = _prepare_engine_at_mayor(num_colonists=4)
            adapter = MayorStrategyAdapter()
            actions = adapter.expand(
                strategy=strategy, game=engine.env.game, player_idx=0
            )
            _apply_actions(engine, actions)

            player = engine.env.game.players[0]
            assert player.unplaced_colonists == 0, (
                f"Strategy {strategy}: unplaced_colonists={player.unplaced_colonists}, "
                f"expected 0"
            )


class TestMayorPhaseCompletion:
    def test_expand_actions_complete_mayor_phase(self):
        """expand 결과를 적용하면 Mayor phase가 정상 종료된다.

        정상 종료 = 다음 플레이어의 Mayor turn으로 넘어가거나 phase 전환.
        즉 current_player_idx가 0이 아니거나, current_phase가 MAYOR가 아닌 상태.
        """
        engine = _prepare_engine_at_mayor(num_colonists=3)
        adapter = MayorStrategyAdapter()
        actions = adapter.expand(strategy=0, game=engine.env.game, player_idx=0)
        _apply_actions(engine, actions)

        game = engine.env.game
        # Mayor phase에서 player 0의 턴이 끝났으므로:
        # - 다음 플레이어로 넘어갔거나 (current_player_idx != 0)
        # - phase가 전환됐거나 (current_phase != MAYOR)
        phase_advanced = (
            game.current_player_idx != 0 or game.current_phase != Phase.MAYOR
        )
        assert phase_advanced, (
            f"Mayor phase not advanced: player_idx={game.current_player_idx}, "
            f"phase={game.current_phase}"
        )


class TestStrategyDifferences:
    def test_expand_three_strategies_produce_different_results(self):
        """동일 보드 상태에서 3가지 전략 중 최소 1개는 다른 배치를 생성한다.

        전략 차이가 드러나려면 식민자가 충분하지 않아 모든 슬롯을 채울 수 없어야 한다.
        그래야 Step 2에서 어떤 건물을 우선 채우느냐에 따라 결과가 갈린다.
        """
        # 각 전략의 우선 건물을 하나씩 배치 + 공통 Large VP 하나
        buildings = [
            BuildingType.WHARF,           # CAPTAIN_FOCUS priority (cap 1)
            BuildingType.OFFICE,          # TRADE_FACTORY_FOCUS priority (cap 1)
            BuildingType.UNIVERSITY,      # BUILDING_FOCUS priority (cap 1)
        ]
        tiles = [
            TileType.COFFEE_PLANTATION,
            TileType.TOBACCO_PLANTATION,
            TileType.CORN_PLANTATION,
            TileType.INDIGO_PLANTATION,
        ]
        # 식민자 2명만 → Step 1에 Large VP 없으므로 Step 2에서 전략별 건물 1개 +
        # 나머지 1개는 다른 곳으로 가서 전략별 차이가 발생
        num_colonists = 2

        board_states = []
        for strategy in [0, 1, 2]:
            engine = _prepare_engine_at_mayor(
                num_colonists=num_colonists,
                island_tiles=tiles,
                city_buildings=buildings,
            )
            adapter = MayorStrategyAdapter()
            actions = adapter.expand(
                strategy=strategy, game=engine.env.game, player_idx=0
            )
            _apply_actions(engine, actions)

            # 최종 배치 상태를 캡처 (어느 건물에 colonist가 있는지)
            player = engine.env.game.players[0]
            city_state = [
                (b.building_type.name, b.colonists)
                for b in player.city_board
                if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
            ]
            board_states.append(city_state)

        # 최소 하나의 전략이 다른 배치를 생성해야 함
        all_same = board_states[0] == board_states[1] == board_states[2]
        assert not all_same, (
            f"All three strategies produced identical city states: {board_states[0]}"
        )


class TestZeroColonists:
    def test_expand_with_zero_colonists(self):
        """unplaced_colonists가 0이면 모든 action이 69(place 0)이어야 한다."""
        engine = _prepare_engine_at_mayor(num_colonists=0)
        adapter = MayorStrategyAdapter()
        actions = adapter.expand(strategy=0, game=engine.env.game, player_idx=0)

        for a in actions:
            assert a == 69, f"With 0 colonists, action should be 69 (place 0), got {a}"
