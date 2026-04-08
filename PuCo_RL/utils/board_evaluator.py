"""
BoardEvaluator — 보드 상태를 3차원 벡터 V = (V_prod, V_vp, V_eff)로 추출한다.

MLOps용 map_human_to_strategy()에서 인간 배치 결과와
전략 시뮬레이션 결과를 비교하기 위해 사용된다.

V_prod: 다음 생산 단계 기대 재화의 시장 가치 합
V_vp:   활성화된 대형 건물의 잠재 승점 합
V_eff:  활성화된 특수 기능 건물 수
"""
import math

from configs.constants import (
    Good, TileType, BuildingType, BUILDING_DATA, GOOD_PRICES,
    LARGE_VP_BUILDINGS,
)

# 특수 기능 건물 (생산 건물 제외)
SPECIAL_BUILDINGS = frozenset({
    BuildingType.FACTORY,
    BuildingType.HARBOR,
    BuildingType.WHARF,
    BuildingType.OFFICE,
    BuildingType.LARGE_MARKET,
    BuildingType.SMALL_MARKET,
    BuildingType.UNIVERSITY,
    BuildingType.HOSPICE,
    BuildingType.CONSTRUCTION_HUT,
    BuildingType.HACIENDA,
    BuildingType.SMALL_WAREHOUSE,
    BuildingType.LARGE_WAREHOUSE,
})

# TileType → Good 매핑 (Corn은 건물 불필요)
_PLANTATION_TO_GOOD = {
    TileType.COFFEE_PLANTATION: Good.COFFEE,
    TileType.TOBACCO_PLANTATION: Good.TOBACCO,
    TileType.SUGAR_PLANTATION: Good.SUGAR,
    TileType.INDIGO_PLANTATION: Good.INDIGO,
    TileType.CORN_PLANTATION: Good.CORN,
}

# Good → 대응 생산 건물 목록
_PRODUCTION_BUILDINGS = {
    Good.COFFEE: {BuildingType.COFFEE_ROASTER},
    Good.TOBACCO: {BuildingType.TOBACCO_STORAGE},
    Good.SUGAR: {BuildingType.SUGAR_MILL, BuildingType.SMALL_SUGAR_MILL},
    Good.INDIGO: {BuildingType.INDIGO_PLANT, BuildingType.SMALL_INDIGO_PLANT},
}


class BoardEvaluator:
    """보드 상태를 (V_prod, V_vp, V_eff) 벡터로 변환하는 정적 유틸리티."""

    @staticmethod
    def evaluate(player) -> tuple[float, float, float]:
        """Player 객체에서 3차원 상태 벡터를 추출한다.

        Args:
            player: env.player.Player 인스턴스

        Returns:
            (V_prod, V_vp, V_eff) — 각각 float
        """
        v_prod = BoardEvaluator._calc_production_value(player)
        v_vp = BoardEvaluator._calc_vp_potential(player)
        v_eff = BoardEvaluator._calc_efficiency_count(player)
        return (v_prod, v_vp, v_eff)

    @staticmethod
    def euclidean_distance(v1: tuple, v2: tuple) -> float:
        """두 3차원 벡터 간 유클리드 거리를 계산한다."""
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))

    # ── 내부 메서드 ──

    @staticmethod
    def _calc_production_value(player) -> float:
        """V_prod: 다음 생산 시 기대되는 재화의 시장 가치 합.

        생산량 = min(manned_plantations[g], manned_building_capacity[g])
        Corn은 건물 없이 manned plantation 수만큼 생산.
        """
        # 1. manned plantation 수 (good별)
        manned_plantations = {g: 0 for g in Good}
        for tile in player.island_board:
            if tile.is_occupied and tile.tile_type in _PLANTATION_TO_GOOD:
                good = _PLANTATION_TO_GOOD[tile.tile_type]
                manned_plantations[good] += 1

        # 2. manned building capacity (good별, Corn 제외)
        manned_building_cap = {g: 0 for g in Good}
        for bldg in player.city_board:
            if bldg.colonists <= 0:
                continue
            for good, btypes in _PRODUCTION_BUILDINGS.items():
                if bldg.building_type in btypes:
                    manned_building_cap[good] += bldg.colonists

        # 3. 생산량 = min(plantation, building) — Corn은 plantation만
        total_value = 0.0
        for good in Good:
            if good == Good.CORN:
                produced = manned_plantations[good]
            else:
                produced = min(manned_plantations[good], manned_building_cap[good])
            total_value += produced * GOOD_PRICES[good]

        return total_value

    @staticmethod
    def _calc_vp_potential(player) -> float:
        """V_vp: 활성화된(colonists > 0) 대형 건물의 VP 합."""
        total_vp = 0.0
        for bldg in player.city_board:
            if bldg.colonists > 0 and bldg.building_type in LARGE_VP_BUILDINGS:
                total_vp += BUILDING_DATA[bldg.building_type][1]  # VP at index 1
        return total_vp

    @staticmethod
    def _calc_efficiency_count(player) -> float:
        """V_eff: 활성화된(colonists > 0) 특수 기능 건물의 가중 합.

        전략별 차별화를 위해 건물 기능 카테고리별로 가중치를 부여:
        - Shipping (WHARF, HARBOR, SMALL_WAREHOUSE, LARGE_WAREHOUSE): weight 1.0
        - Trading  (OFFICE, LARGE_MARKET, SMALL_MARKET, FACTORY): weight 2.0
        - Building (UNIVERSITY, HOSPICE, CONSTRUCTION_HUT, HACIENDA): weight 3.0
        이렇게 하면 동일 개수의 건물이라도 종류에 따라 V_eff가 달라진다.
        """
        _CATEGORY_WEIGHTS = {
            BuildingType.WHARF: 1.0,
            BuildingType.HARBOR: 1.0,
            BuildingType.SMALL_WAREHOUSE: 1.0,
            BuildingType.LARGE_WAREHOUSE: 1.0,
            BuildingType.OFFICE: 2.0,
            BuildingType.LARGE_MARKET: 2.0,
            BuildingType.SMALL_MARKET: 2.0,
            BuildingType.FACTORY: 2.0,
            BuildingType.UNIVERSITY: 3.0,
            BuildingType.HOSPICE: 3.0,
            BuildingType.CONSTRUCTION_HUT: 3.0,
            BuildingType.HACIENDA: 3.0,
        }
        total = 0.0
        for bldg in player.city_board:
            if bldg.colonists > 0 and bldg.building_type in SPECIAL_BUILDINGS:
                total += _CATEGORY_WEIGHTS.get(bldg.building_type, 1.0)
        return total
