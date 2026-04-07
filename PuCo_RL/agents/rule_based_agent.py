import torch
import torch.nn as nn
import numpy as np
import random

class RuleBasedAgent(nn.Module):
    """
    A unified interface that mimics HierarchicalAgent for the environment rollout.
    It uses heuristic rules based on 10 predefined human-like strategies.
    To prevent PPO from overfitting to a specific meta, this agent randomly 
    selects one of the 10 sub-strategies upon each game reset.
    """
    def __init__(self, action_dim=200):
        super().__init__()
        self.action_dim = action_dim
        self.strategy = 0
        self.reset_strategy()

    def reset_strategy(self):
        """
        4가지 큰 전략군, 총 10가지 세부 전략 중 하나를 무작위 선택:
        0: Shipping Rush - Corn/Indigo Rush
        1: Shipping Rush - Harbor + Wharf combo
        2: Building Rush - Early Tobacco/Coffee
        3: Building Rush - Quarry Rush
        4: Fusion Rush - Factory + Harbor
        5: Fusion Rush - Factory + Fortress
        6: Fusion Rush - Multi-crop
        7: Blocking - Ship high tier selectively to block
        8: Blocking / Mixed Balance
        9: Speed End (Rush cheap buildings / colonist drain)
        """
        self.strategy = random.randint(0, 9)

    def get_action_and_value(self, obs_t, mask_t, obs_dict=None, player_idx=None):
        priority = np.zeros(self.action_dim, dtype=np.float32)
        mask = mask_t[0].cpu().numpy()
        priority[:] = 10.0
        priority[15] = 1.0 # Pass is lower than taking free stuff
        
        # [CRITICAL FIX] Prevent compulsive building. Untargeted buildings should have priority < Pass.
        for i in range(16, 39):
            priority[i] = 0.5 

        if obs_dict is not None and player_idx is not None:
            # me = obs_dict["players"][f"player_{player_idx}"]
            global_s = obs_dict["global_state"]
            
            # Helper Functions to set priority mapping
            def set_role_priority(p_list):
                # 0:SETTLER, 1:MAYOR, 2:BUILDER, 3:CRAFTSMAN, 4:TRADER, 5:CAPTAIN, 6:PROSPECTOR_1, 7:PROSPECTOR_2
                for i, r in enumerate(p_list):
                    priority[r] = 100.0 - i * 5

            def set_bldg_priority(b_list):
                # 16~38: 23 Building Types
                for i, b in enumerate(b_list):
                    priority[16 + b] = 200.0 - i * 5

            def set_settler_priority(tiles_wanted):
                # 8-13 map to indices of face_up_plantations
                # Types -> 0:Quarry, 1:Corn, 2:Indigo, 3:Sugar, 4:Tobacco, 5:Coffee
                face_up = global_s["face_up_plantations"]
                for wanted in tiles_wanted:
                    for slot_idx, t_type in enumerate(face_up):
                        if t_type == wanted:
                            priority[8 + slot_idx] = 150.0 - (tiles_wanted.index(wanted) * 5)
                            break
                # 14 corresponds to standalone Quarry
                if 0 in tiles_wanted: 
                    priority[14] = 160.0

            # Sub-Strategies Definitions
            if self.strategy == 0:
                set_role_priority([1, 2, 0, 5, 3, 4, 6, 7]) 
                set_settler_priority([1, 2]) # 1:Corn, 2:Indigo
                set_bldg_priority([0, 6, 8, 3, 5, 17, 21]) # S.Ind, L.Ind, Hospice, Hacienda, S.Wharf, Wharf, Customs

            elif self.strategy == 1:
                set_role_priority([0, 2, 3, 5, 1, 4, 6, 7])
                set_settler_priority([1, 2, 3, 4, 5]) 
                set_bldg_priority([16, 17, 0, 1]) # Harbor, Wharf, S.Ind, S.Sug

            elif self.strategy == 2:
                set_role_priority([0, 2, 4, 1, 3, 5, 6, 7])
                set_settler_priority([4, 5]) 
                set_bldg_priority([12, 13, 9, 10, 22]) # Tob Sto, Cof Roa, Office, L.Market, City Hall

            elif self.strategy == 3:
                set_role_priority([0, 2, 1, 3, 4, 5, 6, 7])
                set_settler_priority([0, 1, 2]) # Quarry absolute
                set_bldg_priority([4, 15, 18, 19, 20, 21, 22]) # Const Hut, Univ, Large Bldgs

            elif self.strategy == 4:
                set_role_priority([0, 2, 3, 1, 5, 4, 6, 7])
                set_settler_priority([1, 2, 3, 4, 5])
                set_bldg_priority([14, 16, 0, 1, 12, 13]) # Factory, Harbor, Productions

            elif self.strategy == 5:
                set_role_priority([0, 2, 1, 3, 5, 4, 6, 7])
                set_settler_priority([1, 2, 3, 4, 5])
                set_bldg_priority([14, 20, 0, 1, 12, 13]) # Factory, Fortress

            elif self.strategy == 6:
                set_role_priority([0, 2, 3, 1, 5, 4, 6, 7])
                set_settler_priority([5, 4, 3, 2, 1])
                set_bldg_priority([3, 8, 14, 0, 1, 12, 13]) # Hacienda, Hospice, Factory

            elif self.strategy == 7:
                set_role_priority([0, 4, 5, 3, 2, 1, 6, 7])
                set_settler_priority([5, 4])
                set_bldg_priority([13, 12, 9, 10]) # High Tier

            elif self.strategy == 8:
                set_role_priority([2, 5, 3, 0, 1, 4, 6, 7])
                set_settler_priority([1, 3, 4])
                set_bldg_priority([1, 7, 2, 10, 16])

            elif self.strategy == 9:
                set_role_priority([1, 2, 0, 3, 5, 4, 6, 7])
                set_settler_priority([1, 0])
                set_bldg_priority([0, 1, 2, 3, 4, 5, 6, 8, 9, 10]) # Rush cheap bldgs

            # Phase-specific local optimizations overrides:
            
            # Captain Load (44-63)
            # Captain phase priority is an absolute order logic (load max possible)
            for i in range(44, 64):
                if mask[i] == 1:
                    priority[i] = 300.0
            
            # Mayor Placement (69-72) -> 69: 0, 70: 1, 71: 2, 72: 3
            # Prioritize placing maximum colonists
            for i in range(69, 73):
                if mask[i] == 1:
                    priority[i] = 50.0 + i 

            # Trader Sell (39-43) -> 39:Corn, 40:Indigo, 41:Sugar, 42:Tobacco, 43:Coffee
            # Prioritize selling highest value good unconditionally
            for i in range(39, 44):
                if mask[i] == 1:
                    priority[i] = 100.0 + i 

            # Craftsman Privilege (93-97)
            # Prioritize taking the most expensive good
            for i in range(93, 98):
                if mask[i] == 1:
                    priority[i] = 80.0 + i

            # Captain Store Windrose (64-68) & Warehouse (106-110)
            # Keep highest value good as a safe heuristic
            for i in range(64, 69):
                if mask[i] == 1:
                    priority[i] = 60.0 + i
            for i in range(106, 111):
                if mask[i] == 1:
                    priority[i] = 60.0 + i
                    
            # Late Game Fallback: If we can afford a Large Building (18-22) but it wasn't targeted,
            # we should still buy it instead of passing, since they give massive VP.
            # Target buildings have priority > 150. Pass is 1.0.
            for b in range(18, 23):
                if priority[16 + b] == 0.5: # If untargeted
                    priority[16 + b] = 5.0 # 5.0 > Pass(1.0), so we buy it if affordable!

        # Add small randomness to break ties naturally
        priority += np.random.uniform(0, 0.1, size=self.action_dim)
        priority[mask == 0] = -1e9

        chosen_act = int(np.argmax(priority))
        chosen_t = torch.tensor([chosen_act], dtype=torch.long, device=mask_t.device)

        # Return format expected by base loops: action, logp, entropy, val
        return chosen_t, torch.zeros(1, device=mask_t.device), torch.zeros(1, device=mask_t.device), torch.zeros(1, device=mask_t.device)
