"""
RED Tests: BoardEvaluator — 보드 상태 벡터 추출

이 테스트들은 BoardEvaluator가 아직 존재하지 않으므로 ImportError로 실패한다.
하지만 각 테스트의 본문은 비즈니스 규칙(지표 계산 정확성)을 검증한다.

벡터 V = (V_prod, V_vp, V_eff):
- V_prod: 생산 가능 재화의 시장 가치 합
- V_vp: 활성화된 대형 건물의 잠재 승점
- V_eff: 활성화된 특수 기능 건물 수
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from env.engine import PuertoRicoGame
from env.player import Player
from configs.constants import (
    Phase, Good, TileType, BuildingType, BUILDING_DATA, GOOD_PRICES,
)
from utils.board_evaluator import BoardEvaluator  # NEW MODULE — will fail


# ────────────────────────────────────────────────────
# Helpers — Player 보드는 동적 리스트이므로 place_plantation/build_building 사용
# ────────────────────────────────────────────────────

def _make_empty_player() -> Player:
    """기본 빈 보드의 Player 객체."""
    return Player(0)


def _make_coffee_production_player() -> Player:
    """Coffee 생산 체인이 완성된 Player:
    - island: coffee plantation 1개 (occupied)
    - city: coffee roaster 1개 (colonists=1)
    """
    p = Player(0)
    p.place_plantation(TileType.COFFEE_PLANTATION)
    p.island_board[0].is_occupied = True
    p.build_building(BuildingType.COFFEE_ROASTER)
    p.city_board[0].colonists = 1
    return p


def _make_large_building_player() -> Player:
    """대형 건물(Guildhall, Fortress)이 있는 Player:
    - Guildhall: colonists=1 (활성화)
    - Fortress: colonists=0 (비활성화)
    """
    p = Player(0)
    p.build_building(BuildingType.GUILDHALL)   # large → takes 2 spaces
    p.city_board[0].colonists = 1  # 활성화
    p.build_building(BuildingType.FORTRESS)    # large → takes 2 spaces
    # Fortress는 city_board[2] (index 0=guildhall, 1=occupied_space, 2=fortress)
    p.city_board[2].colonists = 0  # 비활성화
    return p


def _make_special_buildings_player() -> Player:
    """특수 기능 건물이 있는 Player:
    - Factory: colonists=1 (활성화)
    - Harbor: colonists=1 (활성화)
    - Wharf: colonists=0 (비활성화)
    """
    p = Player(0)
    p.build_building(BuildingType.FACTORY)
    p.city_board[0].colonists = 1
    p.build_building(BuildingType.HARBOR)
    p.city_board[1].colonists = 1
    p.build_building(BuildingType.WHARF)
    p.city_board[2].colonists = 0
    return p


# ════════════════════════════════════════════════════
# Test Class 1: V_prod (Production Value)
# ════════════════════════════════════════════════════

class TestProductionValue:
    """V_prod: 다음 생산 단계 기대 재화의 시장 가치 합."""

    def test_empty_board_production_is_zero(self):
        """빈 보드에서는 생산 가능한 재화가 없으므로 V_prod == 0."""
        p = _make_empty_player()
        v_prod, _, _ = BoardEvaluator.evaluate(p)
        assert v_prod == 0.0, f"Empty board V_prod must be 0, got {v_prod}"

    def test_coffee_chain_production_value(self):
        """Coffee plantation(occupied) + Coffee roaster(colonists=1)
        → V_prod = 1 * GOOD_PRICES[COFFEE] = 4.0"""
        p = _make_coffee_production_player()
        v_prod, _, _ = BoardEvaluator.evaluate(p)
        expected = 1 * GOOD_PRICES[Good.COFFEE]  # 4.0
        assert v_prod == expected, \
            f"Coffee chain V_prod must be {expected}, got {v_prod}"

    def test_unmanned_building_produces_nothing(self):
        """Building에 colonist가 없으면 생산 불가 → V_prod에 기여하지 않는다."""
        p = Player(0)
        p.place_plantation(TileType.COFFEE_PLANTATION)
        p.island_board[0].is_occupied = True
        p.build_building(BuildingType.COFFEE_ROASTER)
        p.city_board[0].colonists = 0
        v_prod, _, _ = BoardEvaluator.evaluate(p)
        assert v_prod == 0.0, \
            f"Unmanned building should not contribute to V_prod, got {v_prod}"

    def test_corn_produces_without_building(self):
        """Corn은 건물 없이 농장만으로 생산 가능.
        Corn plantation(occupied) 2개 → V_prod += 2 * GOOD_PRICES[CORN] = 0
        (Corn 가격은 0이므로 V_prod 기여는 0이지만 생산 자체는 발생)."""
        p = Player(0)
        p.place_plantation(TileType.CORN_PLANTATION)
        p.island_board[0].is_occupied = True
        p.place_plantation(TileType.CORN_PLANTATION)
        p.island_board[1].is_occupied = True
        v_prod, _, _ = BoardEvaluator.evaluate(p)
        # Corn price = 0, so V_prod contribution is 0
        assert v_prod == 0.0, \
            f"Corn V_prod should be 0 (price=0), got {v_prod}"

    def test_multi_good_production_sums_correctly(self):
        """여러 재화 생산 체인이 있으면 각각의 가치를 합산해야 한다.
        Coffee(4) + Indigo(1) = 5.0"""
        p = Player(0)
        # Coffee chain
        p.place_plantation(TileType.COFFEE_PLANTATION)
        p.island_board[0].is_occupied = True
        p.build_building(BuildingType.COFFEE_ROASTER)
        p.city_board[0].colonists = 1
        # Indigo chain
        p.place_plantation(TileType.INDIGO_PLANTATION)
        p.island_board[1].is_occupied = True
        p.build_building(BuildingType.SMALL_INDIGO_PLANT)
        p.city_board[1].colonists = 1

        v_prod, _, _ = BoardEvaluator.evaluate(p)
        expected = GOOD_PRICES[Good.COFFEE] + GOOD_PRICES[Good.INDIGO]  # 4 + 1 = 5
        assert v_prod == expected, \
            f"Multi-good V_prod must be {expected}, got {v_prod}"

    def test_production_limited_by_min_plantation_building(self):
        """생산량 = min(manned_plantations, manned_building_capacity).
        Indigo plantation 1개 + Indigo plant(capacity=3, colonists=2) → 생산 1개 (min(1,2))."""
        p = Player(0)
        p.place_plantation(TileType.INDIGO_PLANTATION)
        p.island_board[0].is_occupied = True
        p.build_building(BuildingType.INDIGO_PLANT)
        p.city_board[0].colonists = 2  # capacity 3 중 2명
        v_prod, _, _ = BoardEvaluator.evaluate(p)
        # min(1 plantation, 2 building workers) = 1 indigo * price 1 = 1.0
        assert v_prod == 1.0, \
            f"Production limited by min(plantation, building), expected 1.0, got {v_prod}"


# ════════════════════════════════════════════════════
# Test Class 2: V_vp (VP Potential)
# ════════════════════════════════════════════════════

class TestVPPotential:
    """V_vp: 활성화된 대형 건물(LARGE_VP_BUILDINGS)의 잠재 승점 합."""

    def test_no_large_buildings_vp_is_zero(self):
        """대형 건물이 없으면 V_vp == 0."""
        p = _make_empty_player()
        _, v_vp, _ = BoardEvaluator.evaluate(p)
        assert v_vp == 0.0, f"No large buildings: V_vp must be 0, got {v_vp}"

    def test_manned_guildhall_contributes_vp(self):
        """Guildhall(colonists=1) → V_vp += 4 (BUILDING_DATA VP)."""
        p = _make_large_building_player()
        _, v_vp, _ = BoardEvaluator.evaluate(p)
        guildhall_vp = BUILDING_DATA[BuildingType.GUILDHALL][1]  # 4
        assert v_vp >= guildhall_vp, \
            f"Manned Guildhall V_vp must be >= {guildhall_vp}, got {v_vp}"

    def test_unmanned_large_building_contributes_zero(self):
        """대형 건물이 있지만 colonists==0이면 V_vp에 기여하지 않는다."""
        p = Player(0)
        p.build_building(BuildingType.FORTRESS)  # large → 2 spaces
        p.city_board[0].colonists = 0  # unmanned
        _, v_vp, _ = BoardEvaluator.evaluate(p)
        assert v_vp == 0.0, \
            f"Unmanned Fortress: V_vp must be 0, got {v_vp}"

    def test_multiple_manned_large_buildings_sum(self):
        """여러 대형 건물이 활성화되면 VP를 합산해야 한다.
        Guildhall(4) + City Hall(4) = 8."""
        p = Player(0)
        p.build_building(BuildingType.GUILDHALL)   # idx 0, 1(occupied_space)
        p.city_board[0].colonists = 1
        p.build_building(BuildingType.CITY_HALL)   # idx 2, 3(occupied_space)
        p.city_board[2].colonists = 1
        _, v_vp, _ = BoardEvaluator.evaluate(p)
        expected = BUILDING_DATA[BuildingType.GUILDHALL][1] + BUILDING_DATA[BuildingType.CITY_HALL][1]
        assert v_vp == expected, \
            f"Two manned large buildings V_vp must be {expected}, got {v_vp}"


# ════════════════════════════════════════════════════
# Test Class 3: V_eff (Efficiency Count)
# ════════════════════════════════════════════════════

class TestEfficiencyCount:
    """V_eff: 활성화된 특수 기능 건물 수."""

    def test_no_special_buildings_eff_is_zero(self):
        """특수 건물이 없으면 V_eff == 0."""
        p = _make_empty_player()
        _, _, v_eff = BoardEvaluator.evaluate(p)
        assert v_eff == 0.0, f"No special buildings: V_eff must be 0, got {v_eff}"

    def test_two_active_specials_weighted_sum(self):
        """Factory(Trading=2.0) + Harbor(Shipping=1.0) → V_eff == 3.0.

        V_eff는 카테고리 가중치 합이다:
        - Shipping(WHARF, HARBOR, ...): 1.0
        - Trading(OFFICE, LARGE_MARKET, SMALL_MARKET, FACTORY): 2.0
        - Building(UNIVERSITY, HOSPICE, CONSTRUCTION_HUT, HACIENDA): 3.0
        """
        p = _make_special_buildings_player()
        _, _, v_eff = BoardEvaluator.evaluate(p)
        assert v_eff == 3.0, \
            f"Factory(2.0)+Harbor(1.0): V_eff must be 3.0, got {v_eff}"

    def test_inactive_special_not_counted(self):
        """Wharf(colonists=0) → V_eff에 기여하지 않는다."""
        p = Player(0)
        p.build_building(BuildingType.WHARF)
        p.city_board[0].colonists = 0
        _, _, v_eff = BoardEvaluator.evaluate(p)
        assert v_eff == 0.0, \
            f"Inactive Wharf: V_eff must be 0, got {v_eff}"

    def test_production_building_not_counted_as_special(self):
        """생산 건물(Coffee Roaster 등)은 특수 기능 건물이 아니므로 V_eff에 포함되지 않는다."""
        p = Player(0)
        p.build_building(BuildingType.COFFEE_ROASTER)
        p.city_board[0].colonists = 1
        _, _, v_eff = BoardEvaluator.evaluate(p)
        assert v_eff == 0.0, \
            f"Production building should not count as special, V_eff must be 0, got {v_eff}"


# ════════════════════════════════════════════════════
# Test Class 4: Vector Shape & Type
# ════════════════════════════════════════════════════

class TestVectorShape:
    """evaluate()의 반환값 형태와 타입 검증."""

    def test_returns_tuple_of_three_floats(self):
        """반환값은 3개의 float로 구성된 tuple이어야 한다."""
        p = _make_empty_player()
        result = BoardEvaluator.evaluate(p)
        assert isinstance(result, tuple), f"Must return tuple, got {type(result)}"
        assert len(result) == 3, f"Must have 3 components, got {len(result)}"
        for i, v in enumerate(result):
            assert isinstance(v, (int, float)), \
                f"Component {i} must be numeric, got {type(v)}"

    def test_different_boards_produce_different_vectors(self):
        """다른 보드 상태는 다른 벡터를 생성해야 한다."""
        empty = BoardEvaluator.evaluate(_make_empty_player())
        coffee = BoardEvaluator.evaluate(_make_coffee_production_player())
        assert empty != coffee, \
            "Empty board and coffee production board must have different vectors"


# ════════════════════════════════════════════════════
# Test Class 5: Euclidean Distance
# ════════════════════════════════════════════════════

class TestEuclideanDistance:
    """BoardEvaluator.euclidean_distance() 검증."""

    def test_same_vector_distance_is_zero(self):
        """동일 벡터 간 거리는 0이어야 한다."""
        v = (3.0, 4.0, 5.0)
        assert BoardEvaluator.euclidean_distance(v, v) == 0.0

    def test_known_distance_calculation(self):
        """(0,0,0) ↔ (3,4,0) → distance = 5.0."""
        v1 = (0.0, 0.0, 0.0)
        v2 = (3.0, 4.0, 0.0)
        d = BoardEvaluator.euclidean_distance(v1, v2)
        assert abs(d - 5.0) < 1e-6, f"Expected 5.0, got {d}"

    def test_distance_is_symmetric(self):
        """d(a, b) == d(b, a)."""
        v1 = (1.0, 2.0, 3.0)
        v2 = (4.0, 5.0, 6.0)
        assert abs(
            BoardEvaluator.euclidean_distance(v1, v2) -
            BoardEvaluator.euclidean_distance(v2, v1)
        ) < 1e-9
