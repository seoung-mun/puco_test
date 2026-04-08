import torch
import torch.nn as nn
import numpy as np
import copy
from typing import Optional

from configs.constants import (
    Phase, Role, Good, TileType, BuildingType, 
    BUILDING_DATA, VP_CHIPS_SETUP, COLONIST_SUPPLY_SETUP
)


class ActionValueAgent(nn.Module):
    """
    Action-Value Heuristic Agent for Puerto Rico.
    
    For each legal action, computes base state heuristic plus action-specific
    bonus using one-step lookahead evaluation. Designed as a strong baseline 
    for PPO agent evaluation.
    
    Strategy: Evaluates all legal actions by simulating them and computing
    the resulting state value using a comprehensive heuristic function.
    """
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 핵심 환산 상수
    # ═══════════════════════════════════════════════════════════════════════════
    
    # 더블론 → VP 환산 비율 (4더블론 = 1VP, 푸에르토리코 통계 기준)
    _DOUBLOON_TO_VP = 0.25
    
    # 상품 판매 가격 (더블론)
    _GOOD_TRADE_PRICES = {
        Good.COFFEE: 4,
        Good.TOBACCO: 3,
        Good.CORN: 0,
        Good.SUGAR: 2,
        Good.INDIGO: 1
    }
    
    # 상품 단위 가치 (VP 환산)
    # 선적 시 1VP, 판매 시 price × _DOUBLOON_TO_VP
    # ** 수정: 비싼 상품이 초반에 더 높은 가치를 갖도록 판매 가치 반영 **
    # V_goods = Σ qty(g) × unit_value(g) × P_ship × weak_decay
    # 여기서 unit_value = max(1.0, trade_value)로 판매 옵션의 가치도 반영
    _GOOD_UNIT_VALUES = {
        Good.COFFEE: 1.0,   # max(1.0, 4*0.25) = 1.0 (선적=판매 동등)
        Good.TOBACCO: 1.0,  # max(1.0, 3*0.25) = 1.0
        Good.SUGAR: 1.0,    # max(1.0, 2*0.25) = 1.0
        Good.INDIGO: 1.0,   # max(1.0, 1*0.25) = 1.0
        Good.CORN: 1.0,     # max(1.0, 0*0.25) = 1.0
    }
    
    # 상품 추가 가치 (판매 옵션의 유연성)
    # 비싼 상품은 판매 시 더블론 획득 → 건물 구매 가능 → 추가 가치
    # 이 값은 게임 초반에 의미 있고, 후반에는 선적 VP가 더 중요
    _GOOD_TRADE_BONUS = {
        Good.COFFEE: 0.5,   # 4더블론 판매 가능 → 유연성 높음
        Good.TOBACCO: 0.4,  # 3더블론
        Good.SUGAR: 0.2,    # 2더블론
        Good.INDIGO: 0.1,   # 1더블론
        Good.CORN: 0.0,     # 판매 불가
    }
    
    # 농장 타입 → 상품 타입 매핑
    _PLANTATION_TO_GOOD = {
        TileType.COFFEE_PLANTATION: Good.COFFEE,
        TileType.TOBACCO_PLANTATION: Good.TOBACCO,
        TileType.CORN_PLANTATION: Good.CORN,
        TileType.SUGAR_PLANTATION: Good.SUGAR,
        TileType.INDIGO_PLANTATION: Good.INDIGO,
    }
    
    # 생산 건물 → 상품 타입 매핑
    _PRODUCTION_BUILDING_TO_GOOD = {
        BuildingType.SMALL_INDIGO_PLANT: Good.INDIGO,
        BuildingType.INDIGO_PLANT: Good.INDIGO,
        BuildingType.SMALL_SUGAR_MILL: Good.SUGAR,
        BuildingType.SUGAR_MILL: Good.SUGAR,
        BuildingType.TOBACCO_STORAGE: Good.TOBACCO,
        BuildingType.COFFEE_ROASTER: Good.COFFEE,
    }
    
    # 상업 건물의 1회 사용 VP 기대값 (수정됨)
    _COMMERCIAL_ABILITY_VALUES = {
        BuildingType.SMALL_MARKET: 0.25,   # 1 doubloon = 0.25 VP
        BuildingType.LARGE_MARKET: 0.50,   # 2 doubloons = 0.5 VP
        BuildingType.OFFICE: 0.20,         # 중복 판매 가치
        BuildingType.HARBOR: 1.0,          # 평균 선적량 기준 추가 VP
        BuildingType.WHARF: 1.5,           # 자유 선적 유연성
        BuildingType.SMALL_WAREHOUSE: 0.3, # 상품 보존 가치
        BuildingType.LARGE_WAREHOUSE: 0.5, # 상품 보존 가치
        BuildingType.FACTORY: 0.5,         # 동적 계산 (기본값)
        BuildingType.HACIENDA: 0.15,       # 무료 농장
        BuildingType.CONSTRUCTION_HUT: 0.15, # 채석장 접근
        BuildingType.HOSPICE: 0.20,        # 무료 colonist
        BuildingType.UNIVERSITY: 0.20,     # 건물에 colonist
    }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 게임 파라미터 (3인 기준)
    # ═══════════════════════════════════════════════════════════════════════════
    
    # 총 역할 선택 횟수: 17라운드 × 3명 = 51회
    # 균등 분포 가정: 각 역할 51/6 ≈ 8.5회
    _TOTAL_ROLE_SELECTIONS = 51.0
    _NUM_ROLES = 6.0
    _EXPECTED_ROLE_USES_BASE = _TOTAL_ROLE_SELECTIONS / _NUM_ROLES  # ≈ 8.5
    
    # 상품 선적 성공 확률 (보수적 추정)
    # 리스크: 배 공간 부족, 경쟁, 강제 폐기
    _SHIPPING_SUCCESS_PROB = 0.7
    
    # 건물 → 관련 역할 매핑
    _BUILDING_TO_ROLE = {
        BuildingType.HARBOR: 'captain',
        BuildingType.WHARF: 'captain',
        BuildingType.SMALL_WAREHOUSE: 'captain',
        BuildingType.LARGE_WAREHOUSE: 'captain',
        BuildingType.SMALL_MARKET: 'trader',
        BuildingType.LARGE_MARKET: 'trader',
        BuildingType.OFFICE: 'trader',
        BuildingType.FACTORY: 'craftsman',
        BuildingType.HACIENDA: 'settler',
        BuildingType.CONSTRUCTION_HUT: 'settler',
        BuildingType.HOSPICE: 'settler',
        BuildingType.UNIVERSITY: 'builder',
    }
    
    def __init__(self, action_dim: int = 200):
        super().__init__()
        self.action_dim = action_dim
        self._env = None  # Will be set externally
        
    def set_env(self, env):
        """Set the environment reference for state access."""
        self._env = env
        
    def get_action_and_value(self, obs_t, mask_t, phase_ids=None, action=None):
        """
        Select action using one-step lookahead heuristic evaluation.
        
        Args:
            obs_t: Observation tensor (not used - we access env directly)
            mask_t: Action mask tensor (1 = valid, 0 = invalid)
            phase_ids: Phase IDs (optional)
            action: Pre-specified action (optional)
            
        Returns:
            chosen_act: Selected action
            logp: Log probability (dummy, always 0)
            entropy: Entropy (dummy, always 0)
            value: Value estimate (dummy, always 0)
        """
        if self._env is None:
            raise RuntimeError("Environment not set. Call set_env() first.")
        
        # Get valid actions from mask
        mask_np = mask_t.cpu().numpy().flatten()
        valid_actions = np.where(mask_np == 1)[0]
        
        if len(valid_actions) == 0:
            # No valid actions - return pass (action 15) or first action
            chosen = torch.tensor([15], dtype=torch.long)
            return chosen, torch.zeros(1), torch.zeros(1), torch.zeros(1)
        
        if len(valid_actions) == 1:
            # Only one valid action - no need to evaluate
            chosen = torch.tensor([valid_actions[0]], dtype=torch.long)
            return chosen, torch.zeros(1), torch.zeros(1), torch.zeros(1)
        
        # Evaluate each valid action using heuristic
        game = self._env.game
        current_player_idx = game.current_player_idx
        
        best_action = valid_actions[0]
        best_value = float('-inf')
        
        # Current state heuristic (for comparison)
        current_heuristic = self._compute_heuristic(game, current_player_idx)
        
        for action_idx in valid_actions:
            # Estimate the heuristic value after taking this action
            # We use action-specific heuristic bonuses instead of full simulation
            action_value = self._estimate_action_value(
                game, current_player_idx, action_idx, current_heuristic
            )
            
            if action_value > best_value:
                best_value = action_value
                best_action = action_idx
        
        chosen = torch.tensor([best_action], dtype=torch.long)
        return chosen, torch.zeros(1), torch.zeros(1), torch.zeros(1)
    
    def _estimate_action_value(self, game, player_idx: int, action_idx: int, 
                                base_heuristic: float) -> float:
        """
        Estimate the heuristic value after taking an action.
        
        Instead of full simulation, we compute incremental changes based on
        action semantics. This is faster and avoids state modification issues.
        """
        p = game.players[player_idx]
        progress = self._game_progress(game)
        decay = max(0.0, 1.0 - progress)
        
        bonus = 0.0
        
        # ═══ Role Selection (0-7) ═══
        if action_idx < 8:
            role = Role(action_idx)
            bonus = self._role_selection_bonus(game, player_idx, role, decay)
        
        # ═══ Settler Phase: Plantation Selection (8-14) ═══
        elif 8 <= action_idx < 15:
            tile_idx = action_idx - 8
            tile_types = [
                TileType.COFFEE_PLANTATION,
                TileType.TOBACCO_PLANTATION,
                TileType.CORN_PLANTATION,
                TileType.SUGAR_PLANTATION,
                TileType.INDIGO_PLANTATION,
                TileType.QUARRY,
            ]
            if tile_idx < len(tile_types):
                bonus = self._plantation_bonus(game, player_idx, tile_types[tile_idx], decay)
        
        # ═══ Pass Action (15) ═══
        elif action_idx == 15:
            bonus = -0.1  # Small penalty for passing (when other options exist)
        
        # ═══ Builder Phase: Building Selection (16-38) ═══
        elif 16 <= action_idx < 39:
            building_idx = action_idx - 16
            building_types = list(BuildingType)[:23]  # Exclude EMPTY and OCCUPIED_SPACE
            if building_idx < len(building_types):
                bonus = self._building_bonus(game, player_idx, building_types[building_idx], decay)
        
        # ═══ Mayor Phase (39-43) ═══
        elif 39 <= action_idx < 44:
            # Mayor actions are complex - use neutral bonus
            bonus = 0.0
        
        # ═══ Captain Phase: Ship Selection (44-63) ═══
        elif 44 <= action_idx < 64:
            ship_good_idx = action_idx - 44
            ship_idx = ship_good_idx // 5
            good_idx = ship_good_idx % 5
            good = Good(good_idx)
            bonus = self._shipping_bonus(game, player_idx, ship_idx, good, decay)
        
        # ═══ Captain Store Phase: Good Selection (64-68) ═══
        elif 64 <= action_idx < 69:
            good_idx = action_idx - 64
            good = Good(good_idx)
            bonus = self._store_bonus(game, player_idx, good, decay)
        
        # ═══ Trader Phase: Good Selection (69-73) ═══
        elif 69 <= action_idx < 74:
            good_idx = action_idx - 69
            good = Good(good_idx)
            bonus = self._trade_bonus(game, player_idx, good, decay)
        
        # ═══ Wharf Phase (74-78) ═══
        elif 74 <= action_idx < 79:
            good_idx = action_idx - 74
            good = Good(good_idx)
            qty = p.goods[good]
            bonus = qty * 1.0  # Direct VP from wharf shipping
        
        return base_heuristic + bonus
    
    def _role_selection_bonus(self, game, player_idx: int, role: Role, decay: float) -> float:
        """Estimate value of selecting a role."""
        p = game.players[player_idx]
        bonus = 0.0
        
        # Role-specific bonuses based on current state
        if role == Role.SETTLER:
            # Value depends on available plantations and island space
            if p.empty_island_spaces > 0:
                bonus = 0.3 * decay
        
        elif role == Role.MAYOR:
            # Value depends on unplaced colonists and empty slots
            empty_slots = self._count_empty_slots(game, player_idx)
            bonus = min(empty_slots, game.colonists_supply) * 0.15 * decay
        
        elif role == Role.BUILDER:
            # Value depends on doubloons and available buildings
            if p.doubloons >= 1:
                bonus = 0.5 * decay
        
        elif role == Role.CRAFTSMAN:
            # Value depends on production capacity
            total_capacity = sum(
                self._production_capacity(game, player_idx, g) for g in Good
            )
            bonus = total_capacity * 0.3 * decay
        
        elif role == Role.TRADER:
            # Value depends on goods and trade probability
            for good in Good:
                if p.goods[good] > 0:
                    trade_prob = self._trade_probability(game, player_idx, good)
                    price = self._GOOD_TRADE_PRICES[good]
                    bonus += trade_prob * price * self._DOUBLOON_TO_VP
        
        elif role == Role.CAPTAIN:
            # Value depends on shippable goods
            total_goods = sum(p.goods.values())
            bonus = total_goods * 0.4 * decay
        
        elif role in (Role.PROSPECTOR_1, Role.PROSPECTOR_2):
            # Prospector gives 1 doubloon
            bonus = self._DOUBLOON_TO_VP * decay
        
        # Add role money bonus (if any on the role card)
        role_doubloons = game.role_doubloons.get(role, 0)
        bonus += role_doubloons * self._DOUBLOON_TO_VP * decay
        
        return bonus
    
    def _plantation_bonus(self, game, player_idx: int, tile_type: TileType, decay: float) -> float:
        """Estimate value of taking a plantation."""
        if tile_type == TileType.QUARRY:
            # Quarry is valuable for building discounts
            return 0.8 * decay
        
        good = self._PLANTATION_TO_GOOD.get(tile_type)
        if good is None:
            return 0.0
        
        # Value based on good price and whether we have matching production building
        price = self._GOOD_TRADE_PRICES[good]
        has_building = self._has_production_building(game, player_idx, good)
        
        # Higher value if we can produce this good
        if good == Good.CORN:
            # Corn doesn't need building
            return (0.3 + price * 0.1) * decay
        elif has_building:
            return (0.4 + price * 0.15) * decay
        else:
            return (0.2 + price * 0.05) * decay
    
    def _building_bonus(self, game, player_idx: int, building_type: BuildingType, decay: float) -> float:
        """Estimate value of building construction."""
        if building_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
            return 0.0
        
        data = BUILDING_DATA.get(building_type)
        if data is None:
            return 0.0
        
        cost, vp, capacity, max_count, is_large, good_produced = data
        
        # Base value from VP
        bonus = vp
        
        # Large building bonus
        if is_large:
            bonus += 2.0  # Large buildings have high end-game potential
        
        # Production building bonus
        if good_produced is not None:
            price = self._GOOD_TRADE_PRICES[good_produced]
            bonus += price * self._DOUBLOON_TO_VP * decay
        
        # Commercial building bonus
        if building_type in self._COMMERCIAL_ABILITY_VALUES:
            # ** 수정: Factory는 동적 가치 계산 사용 **
            if building_type == BuildingType.FACTORY:
                ability_value = self._factory_bonus_value(game, player_idx)
            else:
                ability_value = self._COMMERCIAL_ABILITY_VALUES[building_type]
            
            expected_uses = self._expected_role_uses(decay)
            bonus += ability_value * expected_uses
        
        return bonus
    
    def _shipping_bonus(self, game, player_idx: int, ship_idx: int, good: Good, decay: float) -> float:
        """Estimate value of shipping goods."""
        p = game.players[player_idx]
        
        if ship_idx >= len(game.cargo_ships):
            return 0.0
        
        ship = game.cargo_ships[ship_idx]
        qty = min(p.goods[good], ship.capacity - ship.current_load)
        
        # Base VP from shipping
        bonus = qty * 1.0
        
        # Harbor bonus
        has_harbor = any(
            cb.building_type == BuildingType.HARBOR and cb.colonists > 0
            for cb in p.city_board
        )
        if has_harbor:
            bonus += qty * 1.0  # Additional VP per shipment
        
        return bonus
    
    def _store_bonus(self, game, player_idx: int, good: Good, decay: float) -> float:
        """Estimate value of storing a good (Captain Store phase)."""
        p = game.players[player_idx]
        qty = p.goods[good]
        price = self._GOOD_TRADE_PRICES[good]
        
        # Value of keeping the good for future trade/ship
        return qty * max(0.3, price * self._DOUBLOON_TO_VP * 0.6) * decay
    
    def _trade_bonus(self, game, player_idx: int, good: Good, decay: float) -> float:
        """Estimate value of trading a good."""
        p = game.players[player_idx]
        
        if p.goods[good] <= 0:
            return 0.0
        
        price = self._GOOD_TRADE_PRICES[good]
        
        # Check for market bonuses
        small_market_bonus = any(
            cb.building_type == BuildingType.SMALL_MARKET and cb.colonists > 0
            for cb in p.city_board
        )
        large_market_bonus = any(
            cb.building_type == BuildingType.LARGE_MARKET and cb.colonists > 0
            for cb in p.city_board
        )
        
        total_price = price
        if small_market_bonus:
            total_price += 1
        if large_market_bonus:
            total_price += 2
        
        # Convert doubloons to VP equivalent
        return total_price * self._DOUBLOON_TO_VP * decay
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Heuristic Computation (Main Function) - Revised v2.0
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _compute_heuristic(self, game, player_idx: int) -> float:
        """
        Compute the full heuristic value for a player's state.
        
        H(s) = V_realized + V_potential
        
        V_realized: 확정된 VP (decay 미적용)
        V_potential: 잠재적 VP (decay 적용)
        """
        p = game.players[player_idx]
        progress = self._game_progress(game)
        decay = max(0.0, 1.0 - progress)
        
        # ═══════════════════════════════════════════════════════════════════════
        # 1. V_realized (확정 가치) - 게임 종료 시 확실히 얻는 VP
        # ═══════════════════════════════════════════════════════════════════════
        
        # 1.1 VP 칩
        chip_vp = p.vp_chips
        
        # 1.2 건물 기본 VP 및 분류
        building_vp = 0.0
        num_violet = 0
        num_large_prod = 0
        num_small_prod = 0
        
        for b in p.city_board:
            if b.building_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                continue
            b_type = b.building_type
            building_vp += BUILDING_DATA[b_type][1]
            
            # 건물 분류 (Guildhall, City Hall 보너스용)
            if b_type.value in (0, 1):  # SMALL_INDIGO_PLANT, SMALL_SUGAR_MILL
                num_small_prod += 1
            elif b_type.value in (2, 3, 4, 5):  # INDIGO_PLANT ~ COFFEE_ROASTER
                num_large_prod += 1
            elif b_type.value >= 6:  # Violet buildings
                num_violet += 1
        
        # 1.3 활성화된 대형 건물 동적 보너스
        dynamic_large_vp = 0.0
        for b in p.city_board:
            b_type = b.building_type
            if b_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                continue
            
            # 대형 건물이 활성화된 경우에만 (colonists > 0)
            if b.colonists > 0 and BUILDING_DATA[b_type][4]:  # is_large
                if b_type == BuildingType.CITY_HALL:
                    dynamic_large_vp += num_violet
                elif b_type == BuildingType.CUSTOMS_HOUSE:
                    dynamic_large_vp += chip_vp // 4
                elif b_type == BuildingType.FORTRESS:
                    total_colonists = self._count_total_colonists(p)
                    dynamic_large_vp += total_colonists // 3
                elif b_type == BuildingType.RESIDENCE:
                    island_tiles = sum(1 for tb in p.island_board if tb.tile_type != TileType.EMPTY)
                    dynamic_large_vp += self._residence_bonus(island_tiles)
                elif b_type == BuildingType.GUILDHALL:
                    dynamic_large_vp += (num_large_prod * 2) + (num_small_prod * 1)
        
        v_realized = chip_vp + building_vp + dynamic_large_vp
        
        # ═══════════════════════════════════════════════════════════════════════
        # 2. V_potential (잠재 가치) - 미래 행동으로 VP로 전환 가능한 자원
        # ═══════════════════════════════════════════════════════════════════════
        
        # 2.1 V_goods: 보유 상품의 VP 전환 기대값
        # *** 수정: 선적 성공 확률 반영 ***
        # 상품은 선적해야 VP가 됨. 리스크: 배 공간, 경쟁, 강제 폐기
        v_goods = 0.0
        for good in Good:
            qty = p.goods[good]
            if qty > 0:
                unit_value = self._GOOD_UNIT_VALUES[good]
                # 선적 성공 확률 적용
                ship_value = qty * unit_value * self._SHIPPING_SUCCESS_PROB
                # ** 수정: 비싼 상품의 판매 옵션 가치 추가 (게임 초반에 의미) **
                trade_bonus = qty * self._GOOD_TRADE_BONUS[good] * decay
                v_goods += ship_value + trade_bonus
        # 상품은 가까운 미래에 사용되므로 약한 decay만 적용
        v_goods *= (0.5 + 0.5 * decay)
        
        # 2.2 V_doubloons: 더블론의 VP 전환 기대값
        v_doubloons = p.doubloons * self._DOUBLOON_TO_VP * decay
        
        # 2.3 V_production: 현재 활성화된 생산 능력의 미래 VP 기대값
        # ** V_infrastructure와 중복 방지: 현재 capacity만 계산 **
        v_production = 0.0
        expected_craftsman = self._expected_role_uses(decay)
        
        for good in Good:
            capacity = self._production_capacity(game, player_idx, good)
            if capacity > 0:
                unit_value = self._GOOD_UNIT_VALUES[good]
                # 생산 → 상품 → 선적 체인의 성공 확률 반영
                v_production += capacity * unit_value * expected_craftsman * self._SHIPPING_SUCCESS_PROB
        
        # 2.4 V_commercial: 활성화된 상업 건물의 미래 VP 기대값
        v_commercial = 0.0
        expected_uses = self._expected_role_uses(decay)  # 균등 분포 가정
        
        for cb in p.city_board:
            b_type = cb.building_type
            if b_type in self._COMMERCIAL_ABILITY_VALUES and cb.colonists > 0:
                # Factory는 동적 계산
                if b_type == BuildingType.FACTORY:
                    ability_vp = self._factory_bonus_value(game, player_idx)
                else:
                    ability_vp = self._COMMERCIAL_ABILITY_VALUES[b_type]
                
                v_commercial += ability_vp * expected_uses
        
        # 2.5 V_infrastructure: 인프라 잠재 가치 (중복 제거)
        v_infrastructure = self._compute_infrastructure_value(game, player_idx, decay)
        
        # ═══════════════════════════════════════════════════════════════════════
        # Total Heuristic
        # ═══════════════════════════════════════════════════════════════════════
        v_potential = v_goods + v_doubloons + v_production + v_commercial + v_infrastructure
        total = v_realized + v_potential
        
        return total
    
    def _compute_infrastructure_value(self, game, player_idx: int, decay: float) -> float:
        """
        빈 슬롯/비활성 건물의 활성화 시 얻을 수 있는 VP 기대값.
        ** V_production과 중복되지 않도록 "추가적 생산력"만 계산 **
        """
        p = game.players[player_idx]
        v_infra = 0.0
        
        # colonist 배치 불확실성 반영
        COLONIST_DISCOUNT = 0.5
        
        expected_craftsman = self._expected_role_uses(decay)
        
        # ─────────────────────────────────────────────────────────────────────
        # (a) 빈 농장의 잠재 생산 가치
        # matching 건물 슬롯이 있어야 활성화 시 생산력 증가
        # ─────────────────────────────────────────────────────────────────────
        
        # 각 상품별 현재 상태 계산
        for good in Good:
            # 현재 occupied plantation 수
            occupied_plantations = self._count_occupied_plantations(p, good)
            # 현재 building 슬롯 수 (Corn은 건물 불필요)
            if good == Good.CORN:
                building_slots = float('inf')  # Corn은 제한 없음
            else:
                building_slots = self._count_building_slots(p, good)
            
            # 현재 capacity (이미 V_production에 반영됨)
            current_capacity = min(occupied_plantations, building_slots)
            
            # 빈 농장 수
            unoccupied_plantations = self._count_unoccupied_plantations(p, good)
            
            if unoccupied_plantations > 0:
                # 빈 농장 활성화 시 추가될 수 있는 생산력
                # = min(unoccupied, building_slots - current_capacity)
                if good == Good.CORN:
                    additional_capacity = unoccupied_plantations
                else:
                    available_building_headroom = max(0, building_slots - current_capacity)
                    additional_capacity = min(unoccupied_plantations, available_building_headroom)
                
                if additional_capacity > 0:
                    unit_value = self._GOOD_UNIT_VALUES[good]
                    # 생산 → 선적 체인 성공 확률 반영
                    v_infra += additional_capacity * unit_value * expected_craftsman * self._SHIPPING_SUCCESS_PROB * COLONIST_DISCOUNT
        
        # ─────────────────────────────────────────────────────────────────────
        # (b) 빈 건물 슬롯의 잠재 가치
        # ─────────────────────────────────────────────────────────────────────
        
        for cb in p.city_board:
            b_type = cb.building_type
            if b_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                continue
            
            capacity = BUILDING_DATA[b_type][2]
            empty_slots = capacity - cb.colonists
            
            if empty_slots <= 0:
                continue
            
            # (b-1) 생산 건물: matching plantation이 충분할 때만 가치 있음
            if b_type in self._PRODUCTION_BUILDING_TO_GOOD:
                good = self._PRODUCTION_BUILDING_TO_GOOD[b_type]
                
                # 현재 occupied plantation 수
                occupied_plantations = self._count_occupied_plantations(p, good)
                # 현재 building의 colonist 수 (이 건물 + 같은 상품 다른 건물)
                current_building_colonists = self._count_building_slots(p, good)
                
                # 빈 슬롯 채워도 plantation 부족하면 생산력 안 늘어남
                # 유효한 빈 슬롯 = min(empty_slots, occupied_plantations - current_building_colonists)
                unmatched_plantation_headroom = max(0, occupied_plantations - current_building_colonists)
                effective_empty = min(empty_slots, unmatched_plantation_headroom)
                
                if effective_empty > 0:
                    unit_value = self._GOOD_UNIT_VALUES[good]
                    v_infra += effective_empty * unit_value * expected_craftsman * self._SHIPPING_SUCCESS_PROB * COLONIST_DISCOUNT
            
            # (b-2) 상업 건물: 첫 colonist만 건물 활성화
            elif b_type in self._COMMERCIAL_ABILITY_VALUES:
                if cb.colonists == 0:  # 아직 비활성화
                    ability_vp = self._COMMERCIAL_ABILITY_VALUES[b_type]
                    expected_uses = self._expected_role_uses(decay)
                    v_infra += ability_vp * expected_uses * COLONIST_DISCOUNT
            
            # (b-3) 대형 건물: 활성화 시 예상 보너스 VP
            elif BUILDING_DATA[b_type][4]:  # is_large
                if cb.colonists == 0:  # 아직 비활성화
                    estimated_bonus = self._estimate_large_building_bonus(game, player_idx, b_type)
                    v_infra += estimated_bonus * COLONIST_DISCOUNT
        
        return v_infra
    
    def _expected_role_uses(self, decay: float) -> float:
        """
        남은 게임 기간 동안 특정 역할의 기대 선택 횟수.
        균등 분포 가정: 모든 역할이 동일한 확률로 선택됨.
        
        총 역할 선택: 51회 (17라운드 × 3명)
        역할 수: 6개
        기대값: 51/6 ≈ 8.5회 × decay
        """
        return self._EXPECTED_ROLE_USES_BASE * decay
    
    def _count_total_colonists(self, p) -> int:
        """플레이어의 총 colonist 수."""
        return (
            p.unplaced_colonists +
            sum(1 for tb in p.island_board if tb.is_occupied) +
            sum(cb.colonists for cb in p.city_board 
                if cb.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE))
        )
    
    def _residence_bonus(self, island_tiles: int) -> int:
        """Residence 건물의 보너스 VP 계산."""
        if island_tiles <= 9:
            return 4
        elif island_tiles == 10:
            return 5
        elif island_tiles == 11:
            return 6
        else:
            return 7
    
    def _count_occupied_plantations(self, p, good: Good) -> int:
        """특정 상품의 occupied plantation 수."""
        for tile_type, g in self._PLANTATION_TO_GOOD.items():
            if g == good:
                return sum(1 for tb in p.island_board 
                          if tb.tile_type == tile_type and tb.is_occupied)
        return 0
    
    def _count_unoccupied_plantations(self, p, good: Good) -> int:
        """특정 상품의 unoccupied plantation 수."""
        for tile_type, g in self._PLANTATION_TO_GOOD.items():
            if g == good:
                return sum(1 for tb in p.island_board 
                          if tb.tile_type == tile_type and not tb.is_occupied)
        return 0
    
    def _count_building_slots(self, p, good: Good) -> int:
        """특정 상품 생산 건물의 총 occupied slot 수."""
        slots = 0
        for cb in p.city_board:
            if cb.building_type in self._PRODUCTION_BUILDING_TO_GOOD:
                if self._PRODUCTION_BUILDING_TO_GOOD[cb.building_type] == good:
                    slots += cb.colonists
        return slots
    
    def _estimate_large_building_bonus(self, game, player_idx: int, b_type: BuildingType) -> float:
        """비활성 대형 건물의 예상 보너스 VP."""
        p = game.players[player_idx]
        
        if b_type == BuildingType.CITY_HALL:
            # 현재 보라색 건물 수 기반 예상
            num_violet = sum(1 for b in p.city_board 
                           if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
                           and b.building_type.value >= 6)
            return float(num_violet) + 2.0  # 약간의 성장 기대
        
        elif b_type == BuildingType.CUSTOMS_HOUSE:
            # 현재 VP 칩 기반 예상
            return (p.vp_chips // 4) + 2.0
        
        elif b_type == BuildingType.FORTRESS:
            # 현재 colonist 수 기반 예상
            total = self._count_total_colonists(p)
            return (total // 3) + 1.0
        
        elif b_type == BuildingType.RESIDENCE:
            # 현재 섬 타일 수 기반 예상
            island_tiles = sum(1 for tb in p.island_board if tb.tile_type != TileType.EMPTY)
            return float(self._residence_bonus(island_tiles))
        
        elif b_type == BuildingType.GUILDHALL:
            # 현재 생산 건물 수 기반 예상
            num_small = sum(1 for b in p.city_board if b.building_type.value in (0, 1))
            num_large = sum(1 for b in p.city_board if b.building_type.value in (2, 3, 4, 5))
            return float(num_large * 2 + num_small * 1) + 2.0
        
        return 5.0  # 기본 예상치
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _game_progress(self, game) -> float:
        """Calculate game progress (0.0 = start, 1.0 = near end)."""
        num_players = len(game.players)
        
        # VP chips depletion
        initial_vp = VP_CHIPS_SETUP.get(num_players, 75)
        vp_progress = 1.0 - (game.vp_chips / max(initial_vp, 1))
        
        # City fill progress
        max_city_fill = 0
        for p in game.players:
            filled = sum(1 for b in p.city_board 
                        if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE))
            max_city_fill = max(max_city_fill, filled)
        city_progress = max_city_fill / 12.0
        
        # Colonist depletion
        initial_colonists = COLONIST_SUPPLY_SETUP.get(num_players, 55)
        colonist_progress = 1.0 - (game.colonists_supply / max(initial_colonists, 1))
        
        return max(vp_progress, city_progress, colonist_progress)
    
    def _production_capacity(self, game, player_idx: int, good: Good) -> int:
        """Calculate production capacity for a specific good."""
        p = game.players[player_idx]
        
        # Find plantation type for this good
        plantation_type = None
        for tile_type, g in self._PLANTATION_TO_GOOD.items():
            if g == good:
                plantation_type = tile_type
                break
        
        if plantation_type is None:
            return 0
        
        # Count occupied plantations
        occupied_plantations = sum(
            1 for tb in p.island_board 
            if tb.tile_type == plantation_type and tb.is_occupied
        )
        
        # Corn doesn't need building
        if good == Good.CORN:
            return occupied_plantations
        
        # Count occupied building slots
        building_slots = 0
        for cb in p.city_board:
            if cb.building_type in self._PRODUCTION_BUILDING_TO_GOOD:
                if self._PRODUCTION_BUILDING_TO_GOOD[cb.building_type] == good:
                    building_slots += cb.colonists
        
        return min(occupied_plantations, building_slots)
    
    def _trade_probability(self, game, player_idx: int, good: Good) -> float:
        """Estimate probability of successfully trading a good."""
        p = game.players[player_idx]
        
        # Check for Office
        has_office = any(
            cb.building_type == BuildingType.OFFICE and cb.colonists > 0
            for cb in p.city_board
        )
        
        # Check if good is already in trading house
        if hasattr(game, 'trading_house') and good in game.trading_house:
            if not has_office:
                return 0.0
        
        # Count competitors ahead in turn order
        # ** 수정: production_capacity가 아닌 실제 보유 상품 확인 **
        ahead_competitors = 0
        governor_idx = game.governor_idx
        num_players = len(game.players)
        
        for i in range(num_players):
            if i == player_idx:
                continue
            
            my_order = (player_idx - governor_idx) % num_players
            other_order = (i - governor_idx) % num_players
            
            if other_order < my_order:
                # 상대방이 실제로 해당 상품을 보유하고 있는지 확인
                other_player = game.players[i]
                if other_player.goods[good] > 0:
                    ahead_competitors += 1
        
        return 1.0 / (1.0 + ahead_competitors * 0.3)
    
    def _has_production_building(self, game, player_idx: int, good: Good) -> bool:
        """Check if player has a production building for the given good."""
        p = game.players[player_idx]
        
        for cb in p.city_board:
            if cb.building_type in self._PRODUCTION_BUILDING_TO_GOOD:
                if self._PRODUCTION_BUILDING_TO_GOOD[cb.building_type] == good:
                    return True
        return False
    
    def _count_empty_slots(self, game, player_idx: int) -> int:
        """Count empty colonist slots (plantations + buildings)."""
        p = game.players[player_idx]
        
        # Empty plantation slots
        empty_plantation_slots = sum(
            1 for tb in p.island_board if not tb.is_occupied
        )
        
        # Empty building slots
        empty_building_slots = 0
        for cb in p.city_board:
            if cb.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                capacity = BUILDING_DATA[cb.building_type][2]
                empty_building_slots += capacity - cb.colonists
        
        return empty_plantation_slots + empty_building_slots
    
    def _factory_bonus_value(self, game, player_idx: int) -> float:
        """
        Calculate Factory building dynamic value.
        Factory gives doubloons based on number of different goods produced.
        """
        goods_types = set()
        for good in Good:
            if self._production_capacity(game, player_idx, good) > 0:
                goods_types.add(good)
        
        num_types = len(goods_types)
        # Factory bonus: 0/1/2/3/5 doubloons for 1/2/3/4/5 good types
        if num_types <= 1:
            doubloon_bonus = 0.0
        elif num_types == 2:
            doubloon_bonus = 1.0
        elif num_types == 3:
            doubloon_bonus = 2.0
        elif num_types == 4:
            doubloon_bonus = 3.0
        else:
            doubloon_bonus = 5.0
        
        return doubloon_bonus * self._DOUBLOON_TO_VP


# ═══════════════════════════════════════════════════════════════════════════════
# Simplified Lookahead Agent (Alternative: Pure State Evaluation)
# ═══════════════════════════════════════════════════════════════════════════════

class ActionValueAgentSimple(ActionValueAgent):
    """
    Simplified version that uses only the base heuristic without action-specific
    bonuses. Useful for comparison or when action semantics are unclear.
    """
    
    def _estimate_action_value(self, game, player_idx: int, action_idx: int,
                                base_heuristic: float) -> float:
        """Simply return base heuristic with small random tie-breaking."""
        return base_heuristic + np.random.uniform(0, 0.001)


# Backward compatibility aliases (deprecated - will be removed in future versions)
DaehanHeuristicAgent = ActionValueAgent
DaehanHeuristicAgentSimple = ActionValueAgentSimple
