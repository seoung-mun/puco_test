import torch
import torch.nn as nn
import numpy as np
import random

from configs.constants import BUILDING_DATA, BuildingType, Good, TileType


# Pre-compute building costs for threshold checks
_COST = {b: BUILDING_DATA[b][0] for b in BuildingType if b not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)}

# Helper to extract int from numpy/tensor
def _iv(x) -> int:
    return int(x.item()) if hasattr(x, "item") else int(x)


class ShippingRushAgent(nn.Module):
    """
    A heuristic agent with Shipping Rush strategy.
    
    Prioritizes shipping goods for VP over building or trading.
    Designed as a baseline opponent for PPO agent evaluation.
    
    v2 Improvements:
    - Opponent state awareness (goods, buildings)
    - Game end prediction (VP chips, city slots)
    - Optimized Captain shipping (maximize VP per shipment)
    """

    def __init__(self, action_dim: int = 200, fixed_strategy: int | None = None):
        super().__init__()
        self.action_dim = action_dim
        self.fixed_strategy = fixed_strategy
        self.strategy = 0
        self.reset_strategy()

    def reset_strategy(self):
        """Only Shipping Rush strategy (strategy 0)."""
        if self.fixed_strategy is not None:
            self.strategy = self.fixed_strategy
        else:
            self.strategy = 0  # Only Shipping Rush

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_building(city_buildings: np.ndarray, b_type: BuildingType) -> bool:
        return int(b_type) in city_buildings

    @staticmethod
    def _building_colonists(city_buildings: np.ndarray, city_colonists: np.ndarray,
                             b_type: BuildingType) -> int:
        for slot, b in enumerate(city_buildings):
            if b == int(b_type):
                return int(city_colonists[slot])
        return 0

    @staticmethod
    def _is_active(city_buildings: np.ndarray, city_colonists: np.ndarray,
                   b_type: BuildingType) -> bool:
        """Building is built AND has at least one colonist."""
        for slot, b in enumerate(city_buildings):
            if b == int(b_type) and city_colonists[slot] > 0:
                return True
        return False

    def _set_role(self, priority: np.ndarray, mask: np.ndarray, role_id: int, p: float):
        if mask[role_id]:
            priority[role_id] = p

    def _set_bldg(self, priority: np.ndarray, mask: np.ndarray,
                  b_list: list[int], base: float = 200.0):
        for rank, b in enumerate(b_list):
            action = 16 + b
            if mask[action]:
                priority[action] = base - rank * 5.0

    def _set_settler(self, priority: np.ndarray, mask: np.ndarray,
                     face_up: np.ndarray, wanted_tiles: list[int], base: float = 150.0):
        """Assign settler priorities for desired plantation types."""
        for rank, tile_type in enumerate(wanted_tiles):
            for slot_idx, t in enumerate(face_up):
                t_val = _iv(t)
                if t_val == tile_type and mask[8 + slot_idx]:
                    priority[8 + slot_idx] = base - rank * 5.0
                    break
        # Quarry (tile_type 5) requested via tile_type 5 convention
        if 5 in wanted_tiles and mask[14]:
            priority[14] = base + 10.0

    # ------------------------------------------------------------------
    # Opponent analysis helpers
    # ------------------------------------------------------------------

    def _get_opponent_goods(self, obs_dict: dict, player_idx: int) -> dict:
        """Get total goods for each opponent."""
        opp_goods = {}
        for i in range(len(obs_dict["players"])):
            if i != player_idx:
                opp_state = obs_dict["players"][f"player_{i}"]
                opp_goods[i] = int(np.sum(opp_state["goods"]))
        return opp_goods

    def _opponent_wants_captain(self, obs_dict: dict, player_idx: int) -> bool:
        """Check if any opponent has more goods than us."""
        my_goods = int(np.sum(obs_dict["players"][f"player_{player_idx}"]["goods"]))
        for i, goods in self._get_opponent_goods(obs_dict, player_idx).items():
            if goods > my_goods:
                return True
        return False

    def _get_game_progress(self, obs_dict: dict, player_idx: int) -> dict:
        """Analyze game state to predict end timing."""
        global_s = obs_dict["global_state"]
        vp_chips = _iv(global_s["vp_chips"])
        
        # Check city fill status for all players
        max_city_fill = 0
        for i in range(len(obs_dict["players"])):
            p_state = obs_dict["players"][f"player_{i}"]
            city_b = p_state["city_buildings"]
            filled = sum(1 for b in city_b if _iv(b) < 23)
            max_city_fill = max(max_city_fill, filled)
        
        # Estimate rounds remaining
        vp_critical = vp_chips <= 15
        city_critical = max_city_fill >= 10
        
        return {
            "vp_chips": vp_chips,
            "vp_critical": vp_critical,
            "city_critical": city_critical,
            "endgame": vp_critical or city_critical,
            "max_city_fill": max_city_fill
        }

    # ------------------------------------------------------------------
    # Captain shipping optimization
    # ------------------------------------------------------------------

    def _get_best_shipping_action(self, mask: np.ndarray, goods: np.ndarray,
                                   cargo_ships_good: np.ndarray,
                                   cargo_ships_load: np.ndarray,
                                   has_harbor: bool, has_wharf: bool,
                                   wharf_used: bool) -> tuple[int, float]:
        """
        Find the best shipping action that maximizes VP.
        Returns (action_id, priority_score).
        """
        ship_capacities = [4, 5, 6]  # Typical 3-player setup
        best_action = -1
        best_score = 0.0
        
        # Evaluate each possible ship/good combination
        for ship_idx in range(3):
            ship_good = _iv(cargo_ships_good[ship_idx])
            ship_load = _iv(cargo_ships_load[ship_idx])
            ship_cap = ship_capacities[ship_idx] if ship_idx < len(ship_capacities) else 6
            ship_space = ship_cap - ship_load
            
            if ship_space <= 0:
                continue
            
            for good_idx in range(5):
                action = 44 + ship_idx * 5 + good_idx
                if not mask[action]:
                    continue
                
                my_amount = _iv(goods[good_idx])
                if my_amount <= 0:
                    continue
                
                # Can we load on this ship?
                can_load = (ship_good == 5 or ship_good == good_idx)  # 5 = empty
                if not can_load:
                    continue
                
                # Calculate VP from this shipment
                load_amount = min(my_amount, ship_space)
                vp = load_amount
                if has_harbor:
                    vp += 1  # Harbor bonus
                
                # Prefer shipping more goods at once
                score = vp * 10 + load_amount
                
                if score > best_score:
                    best_score = score
                    best_action = action
        
        # Check Wharf option (59-63)
        if has_wharf and not wharf_used:
            for good_idx in range(5):
                action = 59 + good_idx
                if not mask[action]:
                    continue
                
                my_amount = _iv(goods[good_idx])
                if my_amount <= 0:
                    continue
                
                vp = my_amount
                if has_harbor:
                    vp += 1
                
                score = vp * 10 + my_amount + 5  # Small bonus for Wharf flexibility
                
                if score > best_score:
                    best_score = score
                    best_action = action
        
        return best_action, best_score

    # ------------------------------------------------------------------
    # Mayor strategy selection
    # ------------------------------------------------------------------

    def _choose_mayor_strategy(self, my_state: dict, mask: np.ndarray,
                                priority: np.ndarray):
        """Mayor actions: 69=CAPTAIN_FOCUS, 70=TRADE_FACTORY_FOCUS, 71=BUILDING_FOCUS"""
        city_b = my_state["city_buildings"]
        city_c = my_state["city_colonists"]

        shipping_bldgs = {BuildingType.HARBOR, BuildingType.WHARF,
                          BuildingType.SMALL_WAREHOUSE, BuildingType.LARGE_WAREHOUSE}
        trade_bldgs    = {BuildingType.SMALL_MARKET, BuildingType.LARGE_MARKET,
                          BuildingType.OFFICE, BuildingType.FACTORY}
        production_bldgs = {BuildingType.SMALL_INDIGO_PLANT, BuildingType.INDIGO_PLANT,
                             BuildingType.SMALL_SUGAR_MILL, BuildingType.SUGAR_MILL,
                             BuildingType.TOBACCO_STORAGE, BuildingType.COFFEE_ROASTER}

        captain_slots = trade_slots = building_slots = 0

        for slot, b in enumerate(city_b):
            if _iv(b) >= 23:
                continue
            try:
                b_type = BuildingType(_iv(b))
            except ValueError:
                continue
            capacity = BUILDING_DATA[b_type][2]
            colonists = _iv(city_c[slot])
            empty_slots = max(0, capacity - colonists)
            if empty_slots == 0:
                continue
            if b_type in shipping_bldgs:
                captain_slots += empty_slots
            elif b_type in trade_bldgs:
                trade_slots += empty_slots
            elif b_type in production_bldgs:
                building_slots += empty_slots

        # For Shipping Rush: prioritize captain focus
        scores = {69: captain_slots + 5, 70: trade_slots, 71: building_slots + 2}

        for action_id, score in sorted(scores.items(), key=lambda x: -x[1]):
            if mask[action_id]:
                priority[action_id] = 200.0 + score * 10
                break

        for action_id in (69, 70, 71):
            if mask[action_id] and priority[action_id] < 50.0:
                priority[action_id] = 50.0

    # ------------------------------------------------------------------
    # Main inference
    # ------------------------------------------------------------------

    def get_action_and_value(self, obs_t: torch.Tensor, mask_t: torch.Tensor,
                              obs_dict: dict | None = None,
                              player_idx: int | None = None):
        priority = np.full(self.action_dim, 10.0, dtype=np.float32)
        mask = mask_t[0].cpu().numpy()

        priority[15] = 1.0  # Pass is weakest
        priority[16:39] = 0.5  # Suppress random building

        if obs_dict is not None and player_idx is not None:
            my_state = obs_dict["players"][f"player_{player_idx}"]
            global_s = obs_dict["global_state"]

            # ── Scalar extraction ──────────────────────────────────────
            doubloons = _iv(my_state["doubloons"])
            goods: np.ndarray = my_state["goods"]
            total_goods = int(goods.sum())
            unplaced_col = _iv(my_state["unplaced_colonists"])

            city_b = my_state["city_buildings"]
            city_c = my_state["city_colonists"]
            island_tiles = my_state["island_tiles"]

            occupied_city = sum(1 for b in city_b if _iv(b) < 23)
            empty_city_slots = 12 - occupied_city
            occupied_island = sum(1 for t in island_tiles if _iv(t) < 6)
            empty_island_slots = 12 - occupied_island

            # ── Active building checks ─────────────────────────────────
            has_harbor = self._is_active(city_b, city_c, BuildingType.HARBOR)
            has_wharf = self._is_active(city_b, city_c, BuildingType.WHARF)
            has_sm_mkt = self._is_active(city_b, city_c, BuildingType.SMALL_MARKET)
            has_harbor_built = self._has_building(city_b, BuildingType.HARBOR)
            has_wharf_built = self._has_building(city_b, BuildingType.WHARF)

            # ── Game state analysis ────────────────────────────────────
            trading_house_count = sum(1 for g in global_s["trading_house"] if _iv(g) < 5)
            is_trader_open = trading_house_count < 4
            
            game_progress = self._get_game_progress(obs_dict, player_idx)
            endgame = game_progress["endgame"]
            vp_critical = game_progress["vp_critical"]
            
            # Opponent analysis
            opp_wants_captain = self._opponent_wants_captain(obs_dict, player_idx)
            opp_goods = self._get_opponent_goods(obs_dict, player_idx)
            max_opp_goods = max(opp_goods.values()) if opp_goods else 0

            face_up = global_s["face_up_plantations"]
            cargo_ships_good = global_s["cargo_ships_good"]
            cargo_ships_load = global_s["cargo_ships_load"]

            # ══════════════════════════════════════════════════════════
            # SHIPPING RUSH STRATEGY
            # ══════════════════════════════════════════════════════════

            # Role priorities with opponent awareness
            self._set_role(priority, mask, 6, 20.0)  # Prospector fallback
            self._set_role(priority, mask, 7, 20.0)

            # CAPTAIN: Core of shipping strategy
            if total_goods >= 2:
                base_captain = 140.0
                if has_harbor:
                    base_captain += 30.0  # Harbor makes shipping very valuable
                if endgame:
                    base_captain += 20.0  # Rush VP in endgame
                if opp_wants_captain and total_goods >= max_opp_goods:
                    base_captain += 15.0  # Pre-empt opponent
                self._set_role(priority, mask, 5, base_captain)
            elif total_goods == 1:
                if has_harbor:
                    self._set_role(priority, mask, 5, 100.0)
                else:
                    self._set_role(priority, mask, 5, 70.0)

            # CRAFTSMAN: Produce when empty or need to restock
            if total_goods == 0:
                base_craft = 120.0
                if has_harbor:
                    base_craft += 15.0  # Need goods to ship
                self._set_role(priority, mask, 3, base_craft)
            elif total_goods <= 2 and not endgame:
                self._set_role(priority, mask, 3, 90.0)

            # TRADER: Sell for doubloons when needed
            if total_goods > 0 and is_trader_open:
                base_trade = 75.0
                if not has_harbor_built and doubloons < _COST[BuildingType.HARBOR]:
                    base_trade = 100.0  # Need money for Harbor
                self._set_role(priority, mask, 4, base_trade)

            # SETTLER: Expand plantations (important early)
            if empty_island_slots > 0:
                base_settler = 95.0
                if occupied_island < 4:
                    base_settler = 115.0  # Critical early
                elif endgame:
                    base_settler = 50.0  # Less important late
                self._set_role(priority, mask, 0, base_settler)

            # BUILDER: When we can afford key buildings
            if empty_city_slots > 0:
                if not has_wharf_built and doubloons >= _COST[BuildingType.WHARF]:
                    self._set_role(priority, mask, 2, 145.0)  # Wharf is top priority
                elif not has_harbor_built and doubloons >= _COST[BuildingType.HARBOR]:
                    self._set_role(priority, mask, 2, 135.0)
                elif not has_sm_mkt and doubloons >= _COST[BuildingType.SMALL_MARKET]:
                    self._set_role(priority, mask, 2, 80.0)
                elif endgame and doubloons >= 10:
                    self._set_role(priority, mask, 2, 130.0)  # Large buildings

            # MAYOR: Place colonists
            if unplaced_col > 0:
                self._set_role(priority, mask, 1, 85.0)

            # Settler tile preferences: Corn > Indigo > Sugar (cheap, high volume)
            self._set_settler(priority, mask, face_up, [2, 4, 3, 5])

            # Building priorities
            bldg_priority = [
                BuildingType.WHARF,
                BuildingType.HARBOR,
                BuildingType.LARGE_WAREHOUSE,
                BuildingType.SMALL_MARKET,
                BuildingType.SMALL_SUGAR_MILL,
                BuildingType.SMALL_INDIGO_PLANT,
                BuildingType.SMALL_WAREHOUSE,
            ]
            self._set_bldg(priority, mask, bldg_priority, base=230.0)

            # Large buildings in endgame
            if endgame or occupied_city >= 8:
                self._set_bldg(priority, mask, [
                    BuildingType.CUSTOMS_HOUSE,
                    BuildingType.FORTRESS,
                    BuildingType.GUILDHALL,
                ], base=200.0)

            # ── Phase-specific actions ──────────────────────────────────

            # Optimized Captain shipping
            best_ship_action, ship_score = self._get_best_shipping_action(
                mask, goods, cargo_ships_good, cargo_ships_load,
                has_harbor, has_wharf, False  # wharf_used tracking would need state
            )
            if best_ship_action >= 0:
                priority[best_ship_action] = 320.0 + ship_score
            
            # Other captain actions get lower priority
            for i in range(44, 64):
                if mask[i] and priority[i] < 300.0:
                    priority[i] = 280.0

            # Mayor strategy
            self._choose_mayor_strategy(my_state, mask, priority)

            # Trader: prefer high-value goods
            for i, good_val in enumerate([4, 3, 0, 2, 1]):
                action = 39 + i
                if mask[action]:
                    priority[action] = 100.0 + good_val * 8

            # Craftsman privilege: prefer high-value goods
            for i, good_val in enumerate([4, 3, 0, 2, 1]):
                action = 93 + i
                if mask[action]:
                    priority[action] = 80.0 + good_val * 5

            # Captain store: keep goods
            for i in range(64, 69):
                if mask[i]:
                    priority[i] = 55.0 + i
            for i in range(106, 111):
                if mask[i]:
                    priority[i] = 55.0 + i

        priority += np.random.uniform(0, 0.1, size=self.action_dim)
        priority[mask == 0] = -1e9

        chosen_act = int(np.argmax(priority))
        chosen_t = torch.tensor([chosen_act], dtype=torch.long, device=mask_t.device)
        return chosen_t, torch.zeros(1, device=mask_t.device), \
               torch.zeros(1, device=mask_t.device), torch.zeros(1, device=mask_t.device)


# Backward compatibility alias (deprecated - will be removed in future versions)
AdvancedRuleBasedAgent = ShippingRushAgent
