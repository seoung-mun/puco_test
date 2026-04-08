"""
RED Tests: map_human_to_strategy — 인간 배치를 AI 전략으로 매핑

이 테스트들은 map_human_to_strategy()가 아직 존재하지 않으므로 실패한다.

비즈니스 규칙:
1. WHARF/HARBOR 우선 배치 → CAPTAIN_FOCUS(S0)로 매핑
2. OFFICE/FACTORY 우선 배치 → TRADE_FACTORY_FOCUS(S1)로 매핑
3. UNIVERSITY/HOSPICE 우선 배치 → BUILDING_FOCUS(S2)로 매핑
4. 전략 시뮬레이션 결과와 유클리드 거리가 가장 가까운 전략 반환
5. 모든 전략과 거리가 임계값 초과 → None(noise)
6. 정확히 전략과 일치하면 거리 0 → 해당 전략 반환
"""
import os
import sys
import copy
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from env.engine import PuertoRicoGame
from env.player import Player
from configs.constants import (
    Phase, Role, Good, TileType, BuildingType,
    BUILDING_DATA, MayorStrategy,
    LARGE_VP_BUILDINGS, MAYOR_STRATEGY_BUILDINGS,
)


# ────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────

def _setup_rich_board(game, player_idx, colonists=8):
    """
    전략 차이가 드러나도록 다양한 건물/농장이 있는 보드를 구성한다.
    colonists를 충분히 주어 전략별 차이가 발생하도록 한다.
    보드가 비어있는 Player에 place_plantation/build_building으로 추가.
    """
    p = game.players[player_idx]

    # 기존 보드 초기화 (깔끔한 상태에서 시작)
    p.island_board.clear()
    p.city_board.clear()

    # Island board: 다양한 plantation
    p.place_plantation(TileType.COFFEE_PLANTATION)   # idx 0
    p.place_plantation(TileType.TOBACCO_PLANTATION)  # idx 1
    p.place_plantation(TileType.INDIGO_PLANTATION)   # idx 2
    p.place_plantation(TileType.CORN_PLANTATION)     # idx 3
    p.place_plantation(TileType.SUGAR_PLANTATION)    # idx 4
    for t in p.island_board:
        t.is_occupied = False

    # City board: 전략 구분이 가능한 건물들
    p.build_building(BuildingType.WHARF)              # idx 0: CAPTAIN_FOCUS
    p.build_building(BuildingType.HARBOR)             # idx 1: CAPTAIN_FOCUS
    p.build_building(BuildingType.OFFICE)             # idx 2: TRADE_FACTORY
    p.build_building(BuildingType.FACTORY)            # idx 3: TRADE_FACTORY
    p.build_building(BuildingType.UNIVERSITY)         # idx 4: BUILDING_FOCUS
    p.build_building(BuildingType.HOSPICE)            # idx 5: BUILDING_FOCUS
    p.build_building(BuildingType.COFFEE_ROASTER)     # idx 6: Production
    p.build_building(BuildingType.SMALL_INDIGO_PLANT) # idx 7: Production
    for b in p.city_board:
        b.colonists = 0

    p.unplaced_colonists = colonists
    return game


def _force_mayor_for_mapping(game, player_idx=0, colonists=8):
    """map_human_to_strategy 테스트를 위해 Mayor phase 진입 + 보드 구성."""
    game.current_phase = Phase.MAYOR
    game.current_player_idx = player_idx
    game.active_role = Role.MAYOR
    game.active_role_player = player_idx
    game.players_taken_action = 0
    game.mayor_placement_idx = 0
    _setup_rich_board(game, player_idx, colonists)
    game._skip_empty_mayor_slots(player_idx)
    return game


def _find_city_idx(player, building_type):
    """city_board에서 특정 building_type의 인덱스를 찾는다."""
    for i, b in enumerate(player.city_board):
        if b.building_type == building_type:
            return i
    raise ValueError(f"Building {building_type} not found in city_board")


def _manually_place_captain_focus(player):
    """인간이 CAPTAIN_FOCUS와 유사하게 배치한 상태를 시뮬레이션.

    전략 시뮬레이션 결과 재현 (colonists=8):
    Step 2: WHARF(1) + HARBOR(1)
    Step 3: Coffee(plantation+roaster=2) + Indigo(plantation+plant=2) + Corn(1)
    Step 4: Remaining(1) → OFFICE(1) spillover
    Vector: V_prod=5.0, V_vp=0.0, V_eff=4.0 (WHARF=1 + HARBOR=1 + OFFICE=2)
    """
    player.city_board[_find_city_idx(player, BuildingType.WHARF)].colonists = 1
    player.city_board[_find_city_idx(player, BuildingType.HARBOR)].colonists = 1
    player.city_board[_find_city_idx(player, BuildingType.OFFICE)].colonists = 1   # Step 4 spillover
    player.island_board[0].is_occupied = True  # Coffee
    player.city_board[_find_city_idx(player, BuildingType.COFFEE_ROASTER)].colonists = 1
    player.island_board[2].is_occupied = True  # Indigo
    player.city_board[_find_city_idx(player, BuildingType.SMALL_INDIGO_PLANT)].colonists = 1
    player.island_board[3].is_occupied = True  # Corn
    player.unplaced_colonists = 0


def _manually_place_trade_factory_focus(player):
    """인간이 TRADE_FACTORY_FOCUS와 유사하게 배치.

    전략 시뮬레이션 결과 재현 (colonists=8):
    Step 2: OFFICE(1) + FACTORY(1)
    Step 3: Coffee(plantation+roaster=2) + Indigo(plantation+plant=2) + Corn(1)
    Step 4: Remaining(1) → WHARF(1) spillover
    Vector: V_prod=5.0, V_vp=0.0, V_eff=5.0 (WHARF=1 + OFFICE=2 + FACTORY=2)
    """
    player.city_board[_find_city_idx(player, BuildingType.OFFICE)].colonists = 1
    player.city_board[_find_city_idx(player, BuildingType.FACTORY)].colonists = 1
    player.city_board[_find_city_idx(player, BuildingType.WHARF)].colonists = 1   # Step 4 spillover
    player.island_board[0].is_occupied = True  # Coffee
    player.city_board[_find_city_idx(player, BuildingType.COFFEE_ROASTER)].colonists = 1
    player.island_board[2].is_occupied = True  # Indigo
    player.city_board[_find_city_idx(player, BuildingType.SMALL_INDIGO_PLANT)].colonists = 1
    player.island_board[3].is_occupied = True  # Corn
    player.unplaced_colonists = 0


def _manually_place_building_focus(player):
    """인간이 BUILDING_FOCUS와 유사하게 배치.

    전략 시뮬레이션 결과 재현 (colonists=8):
    Step 2: UNIVERSITY(1) + HOSPICE(1)
    Step 3: Coffee(plantation+roaster=2) + Indigo(plantation+plant=2) + Corn(1)
    Step 4: Remaining(1) → WHARF(1) spillover
    Vector: V_prod=5.0, V_vp=0.0, V_eff=7.0 (WHARF=1 + UNIVERSITY=3 + HOSPICE=3)
    """
    player.city_board[_find_city_idx(player, BuildingType.UNIVERSITY)].colonists = 1
    player.city_board[_find_city_idx(player, BuildingType.HOSPICE)].colonists = 1
    player.city_board[_find_city_idx(player, BuildingType.WHARF)].colonists = 1   # Step 4 spillover
    player.island_board[0].is_occupied = True  # Coffee
    player.city_board[_find_city_idx(player, BuildingType.COFFEE_ROASTER)].colonists = 1
    player.island_board[2].is_occupied = True  # Indigo
    player.city_board[_find_city_idx(player, BuildingType.SMALL_INDIGO_PLANT)].colonists = 1
    player.island_board[3].is_occupied = True  # Corn
    player.unplaced_colonists = 0


def _manually_place_random_noise(player):
    """어떤 전략과도 매치되지 않는 이상한 배치.
    건물은 비워두고 plantation만 다 채움."""
    for t in player.island_board:
        t.is_occupied = True
    # 건물은 모두 비워둠 (colonists=0)
    player.unplaced_colonists = 3  # 남은 colonist가 있지만 건물에 안 넣음


# ════════════════════════════════════════════════════
# Test Class 1: 전략별 정확한 매핑
# ════════════════════════════════════════════════════

class TestStrategyMapping:
    """인간의 배치 결과가 올바른 전략으로 매핑되는지 검증."""

    def test_captain_focus_placement_maps_to_s0(self):
        """WHARF/HARBOR 우선 배치 → CAPTAIN_FOCUS(0)로 매핑되어야 한다."""
        game = PuertoRicoGame(num_players=3)
        _force_mayor_for_mapping(game, player_idx=0, colonists=8)
        _manually_place_captain_focus(game.players[0])

        result = game.map_human_to_strategy(0)
        assert result == MayorStrategy.CAPTAIN_FOCUS.value, \
            f"Captain-focus placement must map to S0(0), got {result}"

    def test_trade_factory_placement_maps_to_s1(self):
        """OFFICE/FACTORY 우선 배치 → TRADE_FACTORY_FOCUS(1)로 매핑되어야 한다."""
        game = PuertoRicoGame(num_players=3)
        _force_mayor_for_mapping(game, player_idx=0, colonists=8)
        _manually_place_trade_factory_focus(game.players[0])

        result = game.map_human_to_strategy(0)
        assert result == MayorStrategy.TRADE_FACTORY_FOCUS.value, \
            f"Trade-factory placement must map to S1(1), got {result}"

    def test_building_focus_placement_maps_to_s2(self):
        """UNIVERSITY/HOSPICE 우선 배치 → BUILDING_FOCUS(2)로 매핑되어야 한다."""
        game = PuertoRicoGame(num_players=3)
        _force_mayor_for_mapping(game, player_idx=0, colonists=8)
        _manually_place_building_focus(game.players[0])

        result = game.map_human_to_strategy(0)
        assert result == MayorStrategy.BUILDING_FOCUS.value, \
            f"Building-focus placement must map to S2(2), got {result}"


# ════════════════════════════════════════════════════
# Test Class 2: Noise / Edge Cases
# ════════════════════════════════════════════════════

class TestStrategyMappingEdgeCases:
    """매핑 불가능한 상황과 엣지 케이스 검증."""

    def test_noise_placement_returns_none(self):
        """어떤 전략과도 거리가 임계값을 초과하면 None(분류 불가) 반환."""
        game = PuertoRicoGame(num_players=3)
        _force_mayor_for_mapping(game, player_idx=0, colonists=8)
        _manually_place_random_noise(game.players[0])

        result = game.map_human_to_strategy(0)
        assert result is None, \
            f"Noise placement (random/no-strategy) must return None, got {result}"

    def test_zero_colonists_returns_valid_or_none(self):
        """unplaced_colonists==0 (빈 배치)에서는 유효한 전략 또는 None을 반환해야 한다.
        어떤 전략이든 colonist 0이면 동일한 결과이므로 매핑이 의미 없을 수 있다."""
        game = PuertoRicoGame(num_players=3)
        _force_mayor_for_mapping(game, player_idx=0, colonists=0)

        result = game.map_human_to_strategy(0)
        # None이거나 0/1/2 중 하나여야 함
        assert result is None or result in (0, 1, 2), \
            f"Zero colonists mapping must be None or valid strategy, got {result}"

    def test_exact_strategy_match_returns_that_strategy(self):
        """인간이 정확히 전략 시뮬레이션과 동일하게 배치하면 해당 전략을 반환해야 한다.
        (거리 == 0)"""
        game = PuertoRicoGame(num_players=3)
        _force_mayor_for_mapping(game, player_idx=0, colonists=8)

        # 전략 S0을 직접 시뮬레이션하여 결과를 인간 배치로 복사
        sim_game = copy.deepcopy(game)
        sim_game.action_mayor_strategy(0, MayorStrategy.CAPTAIN_FOCUS)

        # 시뮬레이션 결과를 원본 game의 player에 복사
        p = game.players[0]
        sim_p = sim_game.players[0]
        for i in range(len(p.island_board)):
            p.island_board[i].is_occupied = sim_p.island_board[i].is_occupied
        for i in range(len(p.city_board)):
            p.city_board[i].colonists = sim_p.city_board[i].colonists
        p.unplaced_colonists = 0

        result = game.map_human_to_strategy(0)
        assert result == MayorStrategy.CAPTAIN_FOCUS.value, \
            f"Exact S0 match must return 0 (CAPTAIN_FOCUS), got {result}"


# ════════════════════════════════════════════════════
# Test Class 3: 반환값 계약
# ════════════════════════════════════════════════════

class TestMappingContract:
    """map_human_to_strategy()의 반환값 계약 검증."""

    def test_return_type_is_int_or_none(self):
        """반환값은 int(0/1/2) 또는 None이어야 한다."""
        game = PuertoRicoGame(num_players=3)
        _force_mayor_for_mapping(game, player_idx=0, colonists=5)
        _manually_place_captain_focus(game.players[0])

        result = game.map_human_to_strategy(0)
        assert result is None or isinstance(result, int), \
            f"Return type must be int or None, got {type(result)}"

    def test_valid_return_range(self):
        """int 반환 시 0, 1, 2 중 하나여야 한다."""
        game = PuertoRicoGame(num_players=3)
        _force_mayor_for_mapping(game, player_idx=0, colonists=5)
        _manually_place_captain_focus(game.players[0])

        result = game.map_human_to_strategy(0)
        if result is not None:
            assert result in (0, 1, 2), \
                f"Return value must be 0, 1, or 2, got {result}"

    def test_method_does_not_modify_game_state(self):
        """map_human_to_strategy()는 읽기 전용이어야 한다.
        호출 전후로 game state가 변하면 안 된다."""
        game = PuertoRicoGame(num_players=3)
        _force_mayor_for_mapping(game, player_idx=0, colonists=5)
        _manually_place_captain_focus(game.players[0])

        # 호출 전 상태 스냅샷
        phase_before = game.current_phase
        player_before = game.current_player_idx
        colonists_before = game.players[0].unplaced_colonists
        island_before = [t.is_occupied for t in game.players[0].island_board]
        city_before = [b.colonists for b in game.players[0].city_board]

        game.map_human_to_strategy(0)

        # 호출 후 상태 검증
        assert game.current_phase == phase_before, "Phase must not change"
        assert game.current_player_idx == player_before, "Current player must not change"
        assert game.players[0].unplaced_colonists == colonists_before, "Colonists must not change"
        assert [t.is_occupied for t in game.players[0].island_board] == island_before, \
            "Island board must not change"
        assert [b.colonists for b in game.players[0].city_board] == city_before, \
            "City board must not change"


# ════════════════════════════════════════════════════
# Test Class 4: 전략 시뮬레이션 벡터 차이
# ════════════════════════════════════════════════════

class TestStrategyVectorDifferences:
    """3가지 전략이 서로 다른 벡터를 생성하는지 검증.
    이는 매핑이 의미 있으려면 전략 간 차이가 있어야 하기 때문."""

    def test_strategies_produce_different_vectors_on_rich_board(self):
        """다양한 건물이 있는 보드에서 3가지 전략은 서로 다른 V 벡터를 생성해야 한다."""
        from utils.board_evaluator import BoardEvaluator

        vectors = {}
        for strategy in MayorStrategy:
            game = PuertoRicoGame(num_players=3)
            _force_mayor_for_mapping(game, player_idx=0, colonists=8)
            game.action_mayor_strategy(0, strategy)
            vectors[strategy] = BoardEvaluator.evaluate(game.players[0])

        # 최소 2쌍은 달라야 함
        v_list = list(vectors.values())
        different_pairs = 0
        for i in range(len(v_list)):
            for j in range(i + 1, len(v_list)):
                if v_list[i] != v_list[j]:
                    different_pairs += 1

        assert different_pairs >= 2, \
            f"At least 2 pairs of strategies must have different vectors, got {different_pairs} different pairs"

    def test_captain_focus_has_highest_production_value(self):
        """CAPTAIN_FOCUS는 생산 체인을 우선하므로 V_prod가 가장 높아야 한다.
        (또는 최소한 다른 전략 이상)"""
        from utils.board_evaluator import BoardEvaluator

        vectors = {}
        for strategy in MayorStrategy:
            game = PuertoRicoGame(num_players=3)
            _force_mayor_for_mapping(game, player_idx=0, colonists=8)
            game.action_mayor_strategy(0, strategy)
            vectors[strategy] = BoardEvaluator.evaluate(game.players[0])

        v_prod_captain = vectors[MayorStrategy.CAPTAIN_FOCUS][0]
        v_prod_trade = vectors[MayorStrategy.TRADE_FACTORY_FOCUS][0]
        v_prod_building = vectors[MayorStrategy.BUILDING_FOCUS][0]

        # CAPTAIN_FOCUS는 shipping 위주이므로 생산을 우선
        assert v_prod_captain >= v_prod_building, \
            f"CAPTAIN_FOCUS V_prod({v_prod_captain}) should >= BUILDING_FOCUS V_prod({v_prod_building})"

    def test_building_focus_has_highest_efficiency(self):
        """BUILDING_FOCUS는 기능 건물을 우선하므로 V_eff가 가장 높아야 한다."""
        from utils.board_evaluator import BoardEvaluator

        vectors = {}
        for strategy in MayorStrategy:
            game = PuertoRicoGame(num_players=3)
            _force_mayor_for_mapping(game, player_idx=0, colonists=8)
            game.action_mayor_strategy(0, strategy)
            vectors[strategy] = BoardEvaluator.evaluate(game.players[0])

        v_eff_building = vectors[MayorStrategy.BUILDING_FOCUS][2]
        v_eff_captain = vectors[MayorStrategy.CAPTAIN_FOCUS][2]

        assert v_eff_building >= v_eff_captain, \
            f"BUILDING_FOCUS V_eff({v_eff_building}) should >= CAPTAIN_FOCUS V_eff({v_eff_captain})"
