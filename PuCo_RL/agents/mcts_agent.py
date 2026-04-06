import math
import random
from typing import List, Dict, Any
from dataclasses import dataclass, field

from env.engine import PuertoRicoGame
from configs.constants import Phase, Good, BuildingType, TileType, BUILDING_DATA

# Helper to map absolute player idx to relative shift: [Me, Next, Prev] for 3 players
def get_relative_indices(root_player_idx: int, num_players: int) -> Dict[int, int]:
    """
    Returns a mapping from absolute player idx to relative idx.
    0 -> Me, 1 -> Next, 2 -> Prev (or +2)
    """
    return { (root_player_idx + i) % num_players: i for i in range(num_players) }

def heuristic_mayor_assignment(env: PuertoRicoGame, p_idx: int, mayor_weights: tuple = (1.0, 1.0, 1.0)):
    """
    시장(Mayor) 페이즈의 우선순위 휴리스틱 함수입니다 (Progressive Bias 기법 관련).
    게임 단계(Phase)를 초반/중반/후반으로 나누어 최적화된 자원(이주민) 배분을 수행합니다.
    """
    p = env.players[p_idx]
    total = p.total_colonists_owned
    
    ew, mw, lw = mayor_weights
    
    total_buildings = sum(b.building_type != BuildingType.OCCUPIED_SPACE for pl in env.players for b in pl.city_board)
    is_late_game = (env.vp_chips < 15) or any(pl.empty_city_spaces <= 3 for pl in env.players)
    is_early_game = (total_buildings < 3 * env.num_players) and not is_late_game
    
    slots = []
    
    for idx, b in enumerate(p.city_board):
        if b.building_type != BuildingType.OCCUPIED_SPACE:
            b_data = BUILDING_DATA[b.building_type]
            cap = b_data[2]
            is_large = b_data[4]
            produces_good = b_data[5] is not None
            
            for _ in range(cap):
                score = 10
                if is_late_game and is_large:
                    score += 100 * lw
                if is_early_game and b.building_type in (BuildingType.HACIENDA, BuildingType.CONSTRUCTION_HUT, BuildingType.HOSPICE, BuildingType.FACTORY):
                    score += 50 * ew
                if produces_good:
                    score += 30 * mw
                
                slots.append({'type': 'city', 'idx': idx, 'score': score, 'b_type': b.building_type})
                
    for idx, t in enumerate(p.island_board):
        score = 10
        if is_early_game and t.tile_type == TileType.QUARRY:
            score += 80 * ew
        elif t.tile_type == TileType.QUARRY:
            score += 40 * ew
        else:
            score += 30 * mw
            
        slots.append({'type': 'island', 'idx': idx, 'score': score, 't_type': t.tile_type})
        
    combo_map = {
        Good.INDIGO: (TileType.INDIGO_PLANTATION, [BuildingType.SMALL_INDIGO_PLANT, BuildingType.INDIGO_PLANT]),
        Good.SUGAR: (TileType.SUGAR_PLANTATION, [BuildingType.SMALL_SUGAR_MILL, BuildingType.SUGAR_MILL]),
        Good.TOBACCO: (TileType.TOBACCO_PLANTATION, [BuildingType.TOBACCO_STORAGE]),
        Good.COFFEE: (TileType.COFFEE_PLANTATION, [BuildingType.COFFEE_ROASTER]),
    }
    
    for good, (p_type, b_types) in combo_map.items():
        p_slots = [s for s in slots if s['type'] == 'island' and s['t_type'] == p_type]
        b_slots = [s for s in slots if s['type'] == 'city' and s['b_type'] in b_types]
        pairs = min(len(p_slots), len(b_slots))
        for i in range(pairs):
            p_slots[i]['score'] += 100 * mw
            b_slots[i]['score'] += 100 * mw
            
    slots.sort(key=lambda x: x['score'], reverse=True)
    
    c_assign = [0] * len(p.city_board)
    i_assign = [False] * len(p.island_board)
    
    placed = 0
    for slot in slots:
        if placed >= total:
            break
        if slot['type'] == 'city':
            c_assign[slot['idx']] += 1
        elif slot['type'] == 'island':
            i_assign[slot['idx']] = True
        placed += 1
    env.action_mayor_pass(p_idx, i_assign, c_assign)

def heuristic_factory_mayor_assignment(env: PuertoRicoGame, p_idx: int):
    p = env.players[p_idx]
    slots = []
    
    for idx, b in enumerate(p.city_board):
        if b.building_type != BuildingType.OCCUPIED_SPACE:
            b_data = BUILDING_DATA[b.building_type]
            cap = b_data[2]
            produces_good = b_data[5] is not None
            
            for _ in range(cap):
                score = 10
                if b.building_type == BuildingType.FACTORY:
                    score += 1000
                elif produces_good:
                    good = b_data[5]
                    has_farm = any(getattr(t, 'value', None) == good.value for t in p.island_board if getattr(t, 'tile_type', None) != TileType.QUARRY)
                    if has_farm:
                        score += 800
                        
                slots.append({'type': 'city', 'idx': idx, 'score': score, 'b_type': b.building_type})
                
    for idx, t in enumerate(p.island_board):
        score = 10
        t_type = getattr(t, 'tile_type', None)
        if t_type == TileType.QUARRY:
            score += 500
        elif t_type is not None:
            # Check if matching production building exists
            for b in p.city_board:
                b_data = BUILDING_DATA.get(b.building_type)
                if b_data and b_data[5] is not None and getattr(t, 'value', None) == b_data[5].value:
                    score += 800
                    break
        slots.append({'type': 'island', 'idx': idx, 'score': score, 'b_type': t_type})
        
    slots.sort(key=lambda x: x['score'], reverse=True)
    
    total = p.total_colonists_owned
    
    c_assign = [0] * len(p.city_board)
    i_assign = [False] * len(p.island_board)
    
    placed = 0
    for slot in slots:
        if placed >= total:
            break
        if slot['type'] == 'city':
            c_assign[slot['idx']] += 1
        elif slot['type'] == 'island':
            i_assign[slot['idx']] = True
        placed += 1
        
    env.action_mayor_pass(p_idx, i_assign, c_assign)

def heuristic_captain_store(env: PuertoRicoGame, p_idx: int):
    # MVP: Dump everything, this implies discarding not stored.
    # Actually advancing phase is handled inside the engine.
    env._advance_phase_turn()

class MCTSNode:
    def __init__(self, state: PuertoRicoGame, parent=None, action=None):
        self.state = state
        self.parent = parent
        self.action = action
        self.children: Dict[Any, 'MCTSNode'] = {}
        self.visits = 0
        self.value_sum = [0.0] * state.num_players
        self._untried_actions = None
        
    def get_untried_actions(self) -> List[Any]:
        if self._untried_actions is None:
            self._untried_actions = self._generate_legal_actions(self.state)
        return self._untried_actions

    def is_terminal(self) -> bool:
        return self.state.check_game_end()

    def is_fully_expanded(self) -> bool:
        return self._untried_actions is not None and len(self._untried_actions) == 0

    def get_best_child(self, c_param=math.sqrt(2), w_param=10.0, heuristic_fn=None):
        best_score = -float('inf')
        best_child = None
        
        root = self
        while root.parent is not None:
            root = root.parent
            
        root_p_idx = root.state.current_player_idx
        relative_map = get_relative_indices(root_p_idx, self.state.num_players)
        
        acting_player = self.state.current_player_idx
        value_idx = relative_map[acting_player]

        for action_str, child in self.children.items():
            h_score = 0.0
            if heuristic_fn is not None:
                h_score = heuristic_fn(self.state, child.action)

            if child.visits == 0:
                score = float('inf') if h_score == 0.0 else 10000.0 + h_score
            else:
                exploit = child.value_sum[value_idx] / child.visits
                explore = c_param * math.sqrt(2 * math.log(self.visits) / child.visits)
                bias = (w_param * h_score) / (child.visits + 1)
                
                score = exploit + explore + bias
                
            if score > best_score:
                best_score = score
                best_child = child
                
        return best_child

    def _generate_legal_actions(self, env: PuertoRicoGame) -> List[Any]:
        actions = []
        phase = env.current_phase
        p_idx = env.current_player_idx
        p = env.players[p_idx]
        
        if phase == Phase.END_ROUND or phase is None:
            for role in env.available_roles:
                actions.append({"type": "role", "role": role})
                
        elif phase == Phase.MAYOR:
            actions.append({"type": "mayor_auto"})
            
        elif phase == Phase.SETTLER:
            has_hacienda = p.is_building_occupied(BuildingType.HACIENDA)
            if has_hacienda and not env._hacienda_used and p.empty_island_spaces > 0 and env.plantation_stack:
                actions.append({"type": "hacienda"})
                
            if p.empty_island_spaces > 0:
                for i in range(len(env.face_up_plantations)):
                    actions.append({"type": "settler", "choice": i})
                    
                has_privilege = (p_idx == env.active_role_player_idx())
                if (has_privilege or p.is_building_occupied(BuildingType.CONSTRUCTION_HUT)) and env.quarry_stack > 0:
                    actions.append({"type": "settler", "choice": -1}) # Quarry
            actions.append({"type": "settler", "choice": -2}) # Pass
            
        elif phase == Phase.BUILDER:
            actions.append({"type": "builder", "choice": None})
            has_privilege = (p_idx == env.active_role_player_idx())
            active_quarries = sum(1 for t in p.island_board if t.tile_type == TileType.QUARRY and t.is_occupied)
            
            for b_type, data in BUILDING_DATA.items():
                if b_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                    continue
                if env.building_supply.get(b_type, 0) > 0 and not p.has_building(b_type):
                    base_cost = data[0]
                    mod_cost = max(0, base_cost - 1) if has_privilege else base_cost
                    final_cost = max(0, mod_cost - min(active_quarries, data[1]))
                    if p.doubloons >= final_cost:
                        spaces_needed = 2 if data[4] else 1
                        if p.empty_city_spaces >= spaces_needed:
                            actions.append({"type": "builder", "choice": b_type})
                            
        elif phase == Phase.CRAFTSMAN:
            actions.append({"type": "craftsman", "privilege": None})
            kinds = getattr(env, '_craftsman_produced_kinds', [])
            for g in kinds:
                if env.goods_supply[g] > 0:
                    actions.append({"type": "craftsman", "privilege": g})
                    
        elif phase == Phase.TRADER:
            actions.append({"type": "trader", "sell": None})
            if len(env.trading_house) < 4:
                has_office = p.is_building_occupied(BuildingType.OFFICE)
                for g in Good:
                    if p.goods[g] > 0:
                        if g not in env.trading_house or has_office:
                            actions.append({"type": "trader", "sell": g})
                            
        elif phase == Phase.CAPTAIN:
            valid_loads = []
            for s_idx, ship in enumerate(env.cargo_ships):
                if not ship.is_full:
                    for g in Good:
                        if p.goods[g] > 0:
                            allowed = False
                            if ship.good_type is None:
                                other_has = any(os.good_type == g for i, os in enumerate(env.cargo_ships) if i != s_idx)
                                if not other_has:
                                    allowed = True
                            elif ship.good_type == g:
                                allowed = True
                                
                            if allowed:
                                valid_loads.append({"type": "captain_load", "ship": s_idx, "good": g})
                                
            if p.is_building_occupied(BuildingType.WHARF) and not env._wharf_used.get(p_idx, False):
                for g in Good:
                    if p.goods[g] > 0:
                        valid_loads.append({"type": "captain_load", "ship": -1, "good": g})
                        
            if valid_loads:
                max_loadable = 0
                for act in valid_loads:
                    g = act["good"]
                    s_idx = act["ship"]
                    if s_idx == -1:
                        potential = p.goods[g]
                    else:
                        potential = min(p.goods[g], env.cargo_ships[s_idx].capacity - env.cargo_ships[s_idx].current_load)
                    max_loadable = max(max_loadable, potential)
                
                for act in valid_loads:
                    g = act["good"]
                    s_idx = act["ship"]
                    potential = p.goods[g] if s_idx == -1 else min(p.goods[g], env.cargo_ships[s_idx].capacity - env.cargo_ships[s_idx].current_load)
                    if potential == max_loadable:
                        actions.append(act)
            else:
                actions.append({"type": "captain_pass"})
                
        elif phase == Phase.CAPTAIN_STORE:
            actions.append({"type": "captain_store_done"})
            
        elif phase == Phase.PROSPECTOR:
            pass

        return actions

def apply_action(env: PuertoRicoGame, action: Any, heuristic_weights: dict = None):
    p_idx = env.current_player_idx
    
    if action["type"] == "role":
        env.select_role(p_idx, action["role"])
    elif action["type"] == "settler":
        env.action_settler(p_idx, action.get("choice"))
    elif action["type"] == "hacienda":
        env.action_hacienda_draw(p_idx)
    elif action["type"] == "builder":
        env.action_builder(p_idx, action.get("choice"))
    elif action["type"] == "mayor_auto":
        mw = heuristic_weights["mayor"] if heuristic_weights else (1.0, 1.0, 1.0)
        heuristic_mayor_assignment(env, p_idx, mw)
    elif action["type"] == "mayor_factory":
        heuristic_factory_mayor_assignment(env, p_idx)
    elif action["type"] == "craftsman":
        env.action_craftsman(p_idx, action.get("privilege"))
    elif action["type"] == "trader":
        env.action_trader(p_idx, action.get("sell"))
    elif action["type"] == "captain_load":
        env.action_captain_load(p_idx, action["ship"], action["good"])
    elif action["type"] == "captain_pass":
        env.action_captain_pass(p_idx)
    elif action["type"] == "captain_store_done":
        heuristic_captain_store(env, p_idx)

@dataclass
class MCTSConfig:
    num_simulations: int = 500
    c_param: float = math.sqrt(2)
    w_param: float = 10.0
    rollout_depth_limit: int = 50
    # Pre-defined MCTS variation strategies
    strategy: str = "default" # "default", "bias_and_slow_node", "slow_node_and_widening_captain"
    # Node expansion threshold (Slow Node Creation)
    node_expansion_threshold: int = 5
    # Progressive Bias: Whether to use heuristic scoring W * H(a) / (N(v') + 1)
    use_progressive_bias: bool = True
    # Progressive Widening: Limits expansion based on visits C * N(v)^alpha
    use_progressive_widening: bool = False
    pw_c: float = 1.0
    pw_alpha: float = 0.5
    heuristic_weights: Dict[str, Any] = field(default_factory=lambda: {
        "mayor": (1.0, 1.0, 1.0),
        "captain": (1.0, 1.0),
        "trader": 1.0
    })

class MCTSAgent:
    def __init__(self, action_space, env, config: MCTSConfig = None):
        self.action_space = action_space
        self.env = env
        self.player_idx = env.game.current_player_idx # Will be updated dynamically or not used directly if determined by context
        self.config = config or MCTSConfig()
        
        # Apply strategy overrides
        if self.config.strategy == "bias_and_slow_node":
            self.config.use_progressive_bias = True
            self.config.use_progressive_widening = False
        elif self.config.strategy == "slow_node_and_widening_captain":
            self.config.use_progressive_bias = False
            self.config.use_progressive_widening = False
            
        self.num_simulations = self.config.num_simulations
        self.c_param = self.config.c_param
        self.w_param = self.config.w_param
        self.heuristic_weights = self.config.heuristic_weights
        self.rollout_depth_limit = self.config.rollout_depth_limit

    def get_heuristic_score(self, state: PuertoRicoGame, action: Any) -> float:
        if action["type"] == "captain_load":
            score = 0.5
            p = state.players[state.current_player_idx]
            g_type = action["good"]
            ship_idx = action["ship"]
            cw_lock, cw_withhold = self.heuristic_weights.get("captain", (1.0, 1.0))
            
            if g_type in (Good.COFFEE, Good.TOBACCO):
                score -= 0.3 * cw_withhold
            else:
                score += 0.1 * cw_withhold
                
            if ship_idx != -1:
                ship = state.cargo_ships[ship_idx]
                if ship.current_load == 0:
                    my_amt = p.goods[g_type]
                    total_others_capacity = sum(v for i, other in enumerate(state.players) if i != state.current_player_idx for k, v in other.goods.items())
                    
                    if my_amt <= 2 and total_others_capacity >= 5:
                        score += 0.4 * cw_lock
                        
            return max(0.0, min(1.0, score))
            
        elif action["type"] == "mayor_auto":
            return 1.0
            
        elif action["type"] == "trader":
            score = 0.5
            tw = self.heuristic_weights.get("trader", 1.0)
            p = state.players[state.current_player_idx]
            if action.get("sell") is not None:
                has_office = p.is_building_occupied(BuildingType.OFFICE)
                has_market = p.is_building_occupied(BuildingType.SMALL_MARKET) or p.is_building_occupied(BuildingType.LARGE_MARKET)
                if has_office or has_market:
                    score += 0.3 * tw
                else:
                    score += 0.1 * tw
            return max(0.0, min(1.0, score))
            
        return 0.5

    def select_action(self, obs, valid_mask) -> int:
        """
        The main entrypoint for the PuCo_RL environment wrapper.
        We ignore `obs` and directly use self.env.game to build the MCTS tree.
        """
        current_game = self.env.game
        root_node = MCTSNode(current_game.fast_clone(randomize_hidden=True))

        for _ in range(self.num_simulations):
            node = self._tree_policy(root_node)
            reward_vector = self._default_policy(node.state)
            self._backpropagate(node, reward_vector, root_node.state.current_player_idx)

        best_child = root_node.get_best_child(c_param=0.0, w_param=0.0, heuristic_fn=None)
        
        # Fallback if no children (should not happen if valid_mask has actions)
        if best_child is None:
            # Random valid action based on mask
            import numpy as np
            valid_actions = np.where(valid_mask)[0]
            if len(valid_actions) > 0:
                return np.random.choice(valid_actions)
            return 15 # Default Pass
            
        dict_action = best_child.action
        return self._map_dict_to_discrete(dict_action, valid_mask)

    def _tree_policy(self, node: MCTSNode) -> MCTSNode:
        while not node.is_terminal():
            is_fully_expanded = node.is_fully_expanded()
            current_phase = node.state.current_phase
            
            # Slow Node Creation logic (do not expand unless visited sufficient times)
            is_slow_node_creation_active = self.config.strategy in ["bias_and_slow_node", "slow_node_and_widening_captain"]
            if is_slow_node_creation_active and node.visits < self.config.node_expansion_threshold and node.parent is not None:
                return node
                
            # Dynamic Widening Flag based on phase explicitly
            is_widening_active = self.config.use_progressive_widening
            if self.config.strategy == "slow_node_and_widening_captain" and current_phase == Phase.CAPTAIN:
                is_widening_active = True
            
            # Progressive Widening Logic
            if is_widening_active:
                # Calculate allowed number of children: max(1, ceil(C * N(v)^alpha))
                allowed_children = max(1, math.ceil(self.config.pw_c * (node.visits ** self.config.pw_alpha)))
                # If we have reached the allowed limit, we MUST select among existing kids, 
                # unless we are already fully expanded (all legal actions exhausted).
                if not is_fully_expanded and len(node.children) < allowed_children:
                    return self._expand(node)
                else:
                    node = node.get_best_child(
                        c_param=self.c_param, 
                        w_param=self.w_param if self.config.use_progressive_bias else 0.0, 
                        heuristic_fn=self.get_heuristic_score if self.config.use_progressive_bias else None
                    )
            else:
                # Standard MCTS: Expand if not fully expanded
                if not is_fully_expanded:
                    return self._expand(node)
                else:
                    node = node.get_best_child(
                        c_param=self.c_param, 
                        w_param=self.w_param if self.config.use_progressive_bias else 0.0, 
                        heuristic_fn=self.get_heuristic_score if self.config.use_progressive_bias else None
                    )
        return node

    def _expand(self, node: MCTSNode) -> MCTSNode:
        untried_actions = node.get_untried_actions()
        action = untried_actions.pop(random.randrange(len(untried_actions)))
        
        next_state = node.state.fast_clone()
        apply_action(next_state, action, self.heuristic_weights)
        
        child_node = MCTSNode(state=next_state, parent=node, action=action)
        node.children[str(action)] = child_node
        return child_node

    def _default_policy(self, state: PuertoRicoGame) -> List[float]:
        sim_state = state.fast_clone()
        depth = 0
        
        while not sim_state.check_game_end() and depth < self.rollout_depth_limit:
            untried = MCTSNode(sim_state).get_untried_actions()
            if not untried:
                break
            
            weights = []
            for a in untried:
                w = self.get_heuristic_score(sim_state, a)
                weights.append(max(0.01, w))
                
            action = random.choices(untried, weights=weights, k=1)[0]
            apply_action(sim_state, action, self.heuristic_weights)
            depth += 1
            
        scores = sim_state.get_scores()
        root_p_idx = self.env.game.current_player_idx
        relative_map = get_relative_indices(root_p_idx, sim_state.num_players)
        
        ranked = sorted([(i, sc[0], sc[1]) for i, sc in enumerate(scores)], key=lambda x: (x[1], x[2]), reverse=True)
        
        abs_rewards = [0.0] * sim_state.num_players
        top_score = (ranked[0][1], ranked[0][2])
        
        for i, vp, tie in ranked:
            if (vp, tie) == top_score:
                abs_rewards[i] = 1.0
            else:
                margin = vp / max(1, top_score[0]) * 0.05
                abs_rewards[i] = margin
                
        rel_rewards = [0.0] * sim_state.num_players
        for abs_idx, reward in enumerate(abs_rewards):
            rel_idx = relative_map[abs_idx]
            rel_rewards[rel_idx] = reward
            
        return rel_rewards

    def _backpropagate(self, node: MCTSNode, reward_vector: List[float], root_p_idx: int):
        while node is not None:
            node.visits += 1
            for i in range(len(reward_vector)):
                node.value_sum[i] += reward_vector[i]
            node = node.parent

    def _map_dict_to_discrete(self, dict_action: dict, valid_mask) -> int:
        """
        Maps the dictionary MCTS action to the integer action used by PuCo_RL pr_env.py.
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
            # Pass triggers the pass logic in env which automatically solidifies assignments.
            discrete_action = 15
            
        elif a_type == "captain_store_done":
            discrete_action = 15

        # Safety Check: Fallback if MCTS selected an action somehow masked out
        if not valid_mask[discrete_action]:
            import numpy as np
            valid_actions = np.where(valid_mask)[0]
            if len(valid_actions) > 0:
                print(f"Warning: MCTS mapped action {discrete_action} is invalid. Falling back to random. (Dict was: {dict_action})")
                return np.random.choice(valid_actions)
                
        return discrete_action
