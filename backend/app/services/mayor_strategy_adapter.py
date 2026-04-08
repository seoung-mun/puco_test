"""
MayorStrategyAdapter — 봇의 Mayor strategy 선택을 sequential placement action 시퀀스로 변환.

엔진(engine.py)의 Mayor는 sequential placement(action 69-72)를 유지한다.
이 adapter는 봇이 선택한 strategy(0/1/2)를 읽고,
upstream의 4단계 배치 알고리즘에 따라 각 슬롯에 배치할 식민자 수를 계산한 뒤,
sequential action 시퀀스(69+amount per slot)로 변환한다.

사용법:
    adapter = MayorStrategyAdapter()
    actions = adapter.expand(strategy=0, game=engine.env.game, player_idx=0)
    for action in actions:
        engine.step(action)
"""
import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL"))
)

from configs.constants import (
    BuildingType,
    Good,
    MayorStrategy,
    TileType,
    BUILDING_DATA,
    GOOD_VALUE_ORDER,
    LARGE_VP_BUILDINGS,
    MAYOR_STRATEGY_BUILDINGS,
    PLANTATION_TO_GOOD,
    PRODUCTION_BUILDINGS,
)


class MayorStrategyAdapter:
    """봇의 Mayor strategy 선택을 sequential placement action 시퀀스로 변환한다."""

    def expand(self, strategy: int, game, player_idx: int) -> list[int]:
        """strategy(0=CAPTAIN_FOCUS, 1=TRADE_FACTORY_FOCUS, 2=BUILDING_FOCUS)를
        sequential Mayor action 리스트로 변환한다.

        Args:
            strategy: 0, 1, 2 중 하나
            game: engine.env.game (PuertoRicoGame 인스턴스)
            player_idx: 현재 Mayor 턴인 플레이어 인덱스

        Returns:
            list[int]: 각 원소는 69-72. engine.step()에 순차 전달할 action 목록.
            빈 슬롯은 engine이 자동 skip하므로 여기서도 건너뛴다.
        """
        player = game.players[player_idx]
        available = player.unplaced_colonists

        # 슬롯 목록 생성 (engine cursor가 순회하는 것과 동일한 순서)
        slots = self._build_slots(player)

        # 4단계 알고리즘으로 배치 계획 생성
        allocation = self._compute_allocation(strategy, player, slots, available)

        # sequential action 시퀀스로 변환
        # 주의: engine은 unplaced_colonists가 0이 되면 cursor를 24로 점프하고
        # Mayor turn을 종료한다. 따라서 식민자 소진 후의 action은 생성하지 않는다.
        actions = []
        sim_remaining = available
        for slot in slots:
            if slot["capacity"] == 0:
                continue  # engine이 자동 skip하는 빈 슬롯
            if sim_remaining <= 0:
                break  # engine이 여기서 cursor를 24로 점프, turn 종료
            amount = allocation.get(slot["idx"], 0)
            actions.append(69 + amount)
            sim_remaining -= amount

        return actions

    def _build_slots(self, player) -> list[dict]:
        """engine의 mayor_placement_idx가 순회하는 24개 슬롯을 리스트로 반환.
        각 슬롯은 {"idx", "zone", "local_idx", "capacity", ...} dict.
        """
        slots = []

        # Island slots (0-11)
        for i in range(12):
            if i < len(player.island_board):
                tile = player.island_board[i]
                if tile.tile_type != TileType.EMPTY:
                    slots.append({
                        "idx": i,
                        "zone": "island",
                        "local_idx": i,
                        "capacity": 1,
                        "tile_type": tile.tile_type,
                        "building_type": None,
                    })
                    continue
            # empty or out of range
            slots.append({
                "idx": i, "zone": "island", "local_idx": i,
                "capacity": 0, "tile_type": None, "building_type": None,
            })

        # City slots (12-23)
        for i in range(12):
            global_idx = 12 + i
            if i < len(player.city_board):
                b = player.city_board[i]
                if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                    cap = BUILDING_DATA[b.building_type][2]
                    slots.append({
                        "idx": global_idx,
                        "zone": "city",
                        "local_idx": i,
                        "capacity": cap,
                        "tile_type": None,
                        "building_type": b.building_type,
                    })
                    continue
            slots.append({
                "idx": global_idx, "zone": "city", "local_idx": i,
                "capacity": 0, "tile_type": None, "building_type": None,
            })

        return slots

    def _compute_allocation(
        self, strategy: int, player, slots: list[dict], available: int
    ) -> dict[int, int]:
        """4단계 배치 알고리즘. slot idx → 배치할 amount 매핑을 반환."""
        allocation: dict[int, int] = {}
        remaining = available

        if remaining <= 0:
            return allocation

        # 편의용 인덱스: building_type → city slot dict
        city_slots_by_type: dict[BuildingType, list[dict]] = {}
        for s in slots:
            if s["zone"] == "city" and s["building_type"] is not None:
                city_slots_by_type.setdefault(s["building_type"], []).append(s)

        # island slots by tile_type
        island_slots_by_type: dict[TileType, list[dict]] = {}
        for s in slots:
            if s["zone"] == "island" and s["tile_type"] is not None:
                island_slots_by_type.setdefault(s["tile_type"], []).append(s)

        # ── Step 1: Large VP Buildings ──
        remaining = self._fill_buildings(
            LARGE_VP_BUILDINGS, city_slots_by_type, allocation, remaining
        )

        # ── Step 2: Strategy-Specific Buildings ──
        strategy_enum = MayorStrategy(strategy)
        remaining = self._fill_buildings(
            MAYOR_STRATEGY_BUILDINGS[strategy_enum], city_slots_by_type,
            allocation, remaining,
        )

        # ── Step 3: Production Pairs (by good value order) ──
        for good in GOOD_VALUE_ORDER:
            if remaining <= 0:
                break
            remaining = self._fill_production_pair(
                good, player, slots, island_slots_by_type, city_slots_by_type,
                allocation, remaining,
            )

        # ── Step 4: Remaining → other buildings → other farms/quarries ──
        # 4a: remaining city buildings not yet filled
        for s in slots:
            if remaining <= 0:
                break
            if s["zone"] == "city" and s["capacity"] > 0 and s["idx"] not in allocation:
                fill = min(s["capacity"], remaining)
                allocation[s["idx"]] = fill
                remaining -= fill

        # 4b: remaining island slots not yet filled
        for s in slots:
            if remaining <= 0:
                break
            if s["zone"] == "island" and s["capacity"] > 0 and s["idx"] not in allocation:
                allocation[s["idx"]] = 1
                remaining -= 1

        return allocation

    def _fill_buildings(
        self,
        building_types: list[BuildingType],
        city_slots_by_type: dict,
        allocation: dict[int, int],
        remaining: int,
    ) -> int:
        """건물 타입 리스트의 순서대로, 각 타입의 첫 번째 빈 슬롯에 용량만큼 배치."""
        for bt in building_types:
            if remaining <= 0:
                break
            slots_for_type = city_slots_by_type.get(bt, [])
            for s in slots_for_type:
                if s["idx"] in allocation:
                    continue  # 이미 배치됨
                fill = min(s["capacity"], remaining)
                allocation[s["idx"]] = fill
                remaining -= fill
                break  # 각 타입에서 첫 번째 빈 슬롯만
        return remaining

    def _fill_production_pair(
        self,
        good: Good,
        player,
        all_slots: list[dict],
        island_slots_by_type: dict,
        city_slots_by_type: dict,
        allocation: dict[int, int],
        remaining: int,
    ) -> int:
        """재화별 생산 쌍(농장+건물) 배치. upstream 알고리즘 재현."""
        if remaining <= 0:
            return remaining

        if good == Good.CORN:
            # Corn은 건물 불필요 — 빈 corn plantation에 1개씩
            corn_tile = TileType.CORN_PLANTATION
            for s in island_slots_by_type.get(corn_tile, []):
                if remaining <= 0:
                    break
                if s["idx"] not in allocation:
                    allocation[s["idx"]] = 1
                    remaining -= 1
            return remaining

        # 이 good에 대한 plantation tile type 찾기
        plantation_tiles = [
            tt for tt, g in PLANTATION_TO_GOOD.items() if g == good
        ]

        # 빈 농장 수
        unfilled_farms = []
        for tt in plantation_tiles:
            for s in island_slots_by_type.get(tt, []):
                if s["idx"] not in allocation:
                    unfilled_farms.append(s)

        # 빈 건물 용량
        prod_buildings = PRODUCTION_BUILDINGS.get(good, [])
        unfilled_building_slots = []
        for bt in prod_buildings:
            for s in city_slots_by_type.get(bt, []):
                if s["idx"] not in allocation:
                    unfilled_building_slots.append(s)

        building_capacity = sum(s["capacity"] for s in unfilled_building_slots)
        producible = min(len(unfilled_farms), building_capacity)

        if producible <= 0:
            return remaining

        # 농장 먼저 배치
        farms_filled = 0
        for s in unfilled_farms:
            if remaining <= 0 or farms_filled >= producible:
                break
            allocation[s["idx"]] = 1
            remaining -= 1
            farms_filled += 1

        # 건물 배치 (producible만큼)
        building_filled = 0
        for s in unfilled_building_slots:
            if remaining <= 0 or building_filled >= producible:
                break
            fill = min(s["capacity"], remaining, producible - building_filled)
            allocation[s["idx"]] = fill
            remaining -= fill
            building_filled += fill

        return remaining
