import random
from typing import Any
from env.engine import PuertoRicoGame
from configs.constants import Good, BuildingType, Role, TileType, BUILDING_DATA
from agents.mcts_agent import MCTSNode # To reuse legal action generation and action mapper logic

class FactoryAgent:
    """
    공장(Factory) 다품종 생산 전략 기반의 휴리스틱 에이전트.
    PuCo_RL 환경을 위해 action_space, env를 받아 초기화하며, obs를 무시하고 env.game 객체를 직접 참조합니다.
    """
    def __init__(self, action_space, env):
        self.action_space = action_space
        self.env = env

    def select_action(self, obs, valid_mask) -> int:
        current_game = self.env.game
        self.player_idx = current_game.current_player_idx
        
        legal_actions = MCTSNode(current_game).get_untried_actions()
        
        if not legal_actions:
            # Fallback
            import numpy as np
            valid_actions = np.where(valid_mask)[0]
            if len(valid_actions) > 0:
                return np.random.choice(valid_actions)
            return 15
            
        if len(legal_actions) == 1:
            best_action = legal_actions[0]
        else:
            best_action = None
            best_score = -1.0
            
            for action in legal_actions:
                score = self._evaluate_action(current_game, action)
                if score > best_score:
                    best_score = score
                    best_action = action
                    
            if best_action is None:
                best_action = random.choice(legal_actions)
                
        # Use MCTS agent's mapping logic (duplicate here for standalone or import if refactored)
        # For this implementation, we include the mapper directly to avoid circular/awkward dependency on MCTSAgent class instance,
        # but the logic is identical.
        return self._map_dict_to_discrete(best_action, valid_mask)

    def _evaluate_action(self, state: PuertoRicoGame, action: Any) -> float:
        a_type = action.get("type")
        
        if a_type == "role":
            return self._evaluate_role_selection(state, action)
        elif a_type == "builder":
            return self._evaluate_builder_action(state, action)
        elif a_type in ["settler", "hacienda"]:
            return self._evaluate_settler_action(state, action)
        elif a_type == "mayor_auto":
            return 1000.0
        elif a_type == "craftsman":
            return self._evaluate_craftsman_action(state, action)
        elif a_type == "trader":
            return self._evaluate_trader_action(state, action)
        elif a_type == "captain_load":
            return self._evaluate_captain_action(state, action)
        elif a_type in ["captain_pass", "captain_store_done"]:
            return 0.0
        else:
            return 10.0
            
    # --- Phase-Specific Evaluators ---

    def _evaluate_role_selection(self, state: PuertoRicoGame, action: Any) -> float:
        p = state.players[self.player_idx]
        role = action.get("role")
        score = 10.0
        
        if role == Role.BUILDER:
            base_cost = BUILDING_DATA[BuildingType.FACTORY][0]
            column = BUILDING_DATA[BuildingType.FACTORY][1]
            active_quarries = sum(1 for t in p.island_board if getattr(t, 'tile_type', None) == TileType.QUARRY and getattr(t, 'is_occupied', False))
            q_discount = min(active_quarries, column)
            factory_price = max(0, base_cost - 1 - q_discount)
            
            if p.doubloons >= factory_price and state.building_supply.get(BuildingType.FACTORY, 0) > 0:
                score += 2000.0
            else:
                score += 50.0

        elif role == Role.CRAFTSMAN:
            has_factory_active = p.is_building_occupied(BuildingType.FACTORY)
            if has_factory_active:
                my_types = self._get_production_diversity(p)
                max_opp_types = 0
                for i, opp in enumerate(state.players):
                    if i != self.player_idx:
                        max_opp_types = max(max_opp_types, self._get_production_diversity(opp))
                
                if my_types > max_opp_types:
                    score += 1500.0
                else:
                    score += 800.0
            else:
                score += 40.0

        elif role == Role.MAYOR:
            unmanned = 0
            has_factory = p.has_building(BuildingType.FACTORY)
            
            for b in p.city_board:
                if b.building_type == BuildingType.FACTORY and not b.is_occupied:
                    score += 1000.0
                elif b.building_type != BuildingType.OCCUPIED_SPACE and not b.is_occupied:
                    unmanned += BUILDING_DATA[b.building_type][2]
                    
            if has_factory and unmanned > 0:
                score += 800.0
            else:
                score += 30.0

        elif role == Role.SETTLER:
            has_factory = p.is_building_occupied(BuildingType.FACTORY)
            if has_factory:
                score += 1000.0
            else:
                score += 60.0

        elif role == Role.TRADER:
            has_factory = p.is_building_occupied(BuildingType.FACTORY)
            if not has_factory:
                score += 500.0
            else:
                score += 20.0

        elif role == Role.CAPTAIN:
            score += 10.0

        elif role == Role.PROSPECTOR:
            if p.doubloons < 3:
                score += 100.0
            else:
                score += 30.0

        return score + state.role_doubloons.get(role, 0) * 10

    def _evaluate_builder_action(self, state: PuertoRicoGame, action: Any) -> float:
        b_type = action.get("choice")
        if b_type is None:
            return 0.0
            
        p = state.players[self.player_idx]
        score = 10.0
        
        if b_type == BuildingType.FACTORY:
            return 2000.0
            
        produces_good = BUILDING_DATA[b_type][5]
        if produces_good is not None:
            if not p.has_building(b_type):
                score += 500.0
            else:
                score += 100.0
                
        if b_type in [BuildingType.HACIENDA, BuildingType.CONSTRUCTION_HUT]:
            score += 300.0
            
        if b_type in [BuildingType.HARBOR, BuildingType.WHARF]:
            score += 400.0

        if b_type in [BuildingType.GUILDHALL, BuildingType.CUSTOMS_HOUSE, BuildingType.CITY_HALL]:
            if state.vp_chips < 30:
                score += 800.0
                
        return score

    def _evaluate_settler_action(self, state: PuertoRicoGame, action: Any) -> float:
        a_type = action.get("type")
        if a_type == "hacienda":
            return 500.0
            
        choice = action.get("choice")
        if choice == -2:
            return 0.0
            
        if choice == -1:
            return 400.0
            
        p = state.players[self.player_idx]
        t_type = state.face_up_plantations[choice]
        score = 10.0
        
        has_factory = p.is_building_occupied(BuildingType.FACTORY)
        if has_factory:
            current_types = set()
            for b in p.city_board:
                if b.building_type != BuildingType.OCCUPIED_SPACE and b.is_occupied:
                    g = BUILDING_DATA[b.building_type][5]
                    if g:
                        current_types.add(g)
                        
            good_map = {
                TileType.INDIGO_PLANTATION: Good.INDIGO,
                TileType.SUGAR_PLANTATION: Good.SUGAR,
                TileType.CORN_PLANTATION: Good.CORN,
                TileType.TOBACCO_PLANTATION: Good.TOBACCO,
                TileType.COFFEE_PLANTATION: Good.COFFEE
            }
            g_target = good_map.get(t_type)
            
            if g_target and g_target not in current_types:
                score += 800.0
            else:
                score += 100.0
        else:
            if t_type in [TileType.CORN_PLANTATION, TileType.INDIGO_PLANTATION]:
                score += 200.0
                
        return score

    def _evaluate_craftsman_action(self, state: PuertoRicoGame, action: Any) -> float:
        privilege = action.get("privilege")
        if not privilege:
            return 0.0
        
        p = state.players[self.player_idx]
        score = 10.0
        
        has_factory = p.is_building_occupied(BuildingType.FACTORY)
        if has_factory:
            if privilege in [Good.CORN, Good.INDIGO]:
                score += 500.0
            elif getattr(p, '_factory_income_this_turn', 0) > 0:
                score += 1000.0
                
        if privilege in [Good.COFFEE, Good.TOBACCO]:
            score += 300.0
            
        return score

    def _evaluate_trader_action(self, state: PuertoRicoGame, action: Any) -> float:
        sell = action.get("sell")
        if not sell:
            return 0.0
            
        score = 10.0
        if sell == Good.COFFEE:
            score += 500.0
        elif sell == Good.TOBACCO:
            score += 400.0
        elif sell == Good.SUGAR:
            score += 200.0
            
        return score

    def _evaluate_captain_action(self, state: PuertoRicoGame, action: Any) -> float:
        good = action.get("good")
        score = 10.0
        
        if good == Good.CORN:
            score += 300.0
            
        p = state.players[self.player_idx]
        has_harbor = p.is_building_occupied(BuildingType.HARBOR)
        if has_harbor:
            score += 500.0
            
        return score

    def _get_production_diversity(self, player) -> int:
        types = set()
        for t in player.island_board:
            if getattr(t, 'is_occupied', False) and getattr(t, 'value', None):
                types.add(t.value)
        return len(types)

    def _map_dict_to_discrete(self, dict_action: dict, valid_mask) -> int:
        """
        Maps the dictionary MCTS action to the integer action used by PuCo_RL pr_env.py.
        Duplicated from MCTSAgent for standalone capability.
        """
        a_type = dict_action.get("type")
        discrete_action = 15 # Default pass
        
        if a_type == "role":
            discrete_action = dict_action["role"].value # 0-7
            
        elif a_type == "settler":
            choice = dict_action.get("choice")
            if choice == -2:
                discrete_action = 15
            elif choice == -1:
                discrete_action = 14
            elif choice is not None:
                discrete_action = 8 + choice
                
        elif a_type == "hacienda":
            discrete_action = 105
            
        elif a_type == "builder":
            choice = dict_action.get("choice")
            if choice is None:
                discrete_action = 15
            else:
                discrete_action = 16 + choice.value
                
        elif a_type == "trader":
            sell = dict_action.get("sell")
            if sell is None:
                discrete_action = 15
            else:
                discrete_action = 39 + sell.value
                
        elif a_type == "captain_load":
            ship_idx = dict_action["ship"]
            g = dict_action["good"]
            if ship_idx == -1:
                discrete_action = 59 + g.value
            else:
                discrete_action = 44 + (ship_idx * 5) + g.value
                
        elif a_type == "captain_pass":
            discrete_action = 15
            
        elif a_type == "craftsman":
            privilege = dict_action.get("privilege")
            if privilege is None:
                discrete_action = 15
            else:
                discrete_action = 93 + privilege.value
                
        elif a_type == "mayor_auto":
            discrete_action = 15
            
        elif a_type == "captain_store_done":
            discrete_action = 15

        if not valid_mask[discrete_action]:
            import numpy as np
            valid_actions = np.where(valid_mask)[0]
            if len(valid_actions) > 0:
                print(f"Warning: Factory mapped action {discrete_action} is invalid. Falling back to random. (Dict was: {dict_action})")
                return np.random.choice(valid_actions)
                
        return discrete_action
