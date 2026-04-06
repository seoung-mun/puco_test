import torch
import torch.nn as nn
import numpy as np

class BaseHeuristicBot(nn.Module):
    """
    A unified interface that mimics HierarchicalAgent for the environment rollout.
    Instead of a neural network, it uses static or rule-based priorities 
    over the 200 discrete actions.
    """
    def __init__(self, action_dim=200):
        super().__init__()
        self.action_dim = action_dim
        # Base priority vector
        self.priority = torch.zeros(action_dim, dtype=torch.float32)
        
    def get_action_and_value(self, obs_t, mask_t, phase_ids=None, action=None):
        # We only support single batch inference for rollout
        valid_p = self.priority.clone().unsqueeze(0) # (1, 200)
        
        # In case of random bot, we dynamically generate priority
        if getattr(self, 'is_random', False):
            valid_p = torch.rand((1, self.action_dim), dtype=torch.float32)
            
        valid_p[mask_t == 0] = -1e9
        
        # Select argmax
        chosen_act = torch.argmax(valid_p, dim=1)
        
        # Return dummy logp, entropy, val
        return chosen_act, torch.zeros_like(chosen_act, dtype=torch.float), torch.zeros_like(chosen_act, dtype=torch.float), torch.zeros_like(chosen_act, dtype=torch.float)


class BuilderBot(BaseHeuristicBot):
    """
    Prioritizes Builder, Mayor, Quarry, and Large/Violet Buildings.
    """
    def __init__(self, action_dim=200):
        super().__init__(action_dim)
        
        # Initialize default priority to neutral (10)
        self.priority[:] = 10.0
        
        # Role selection (0-7): Builder > Mayor > Settler
        self.priority[2] = 100.0 # BUILDER
        self.priority[1] = 90.0  # MAYOR
        self.priority[0] = 80.0  # SETTLER
        
        # Settler: Quarry is absolute priority
        self.priority[14] = 100.0 # Quarry
        for i in range(8, 14): self.priority[i] = 50.0 # Normal Plantations
        
        # Builder: Large Buildings > Violet > Production
        for i in range(34, 39): self.priority[i] = 100.0 # Large Buildings (18-22 mapped to 16+18)
        for i in range(22, 34): self.priority[i] = 80.0 # Commercial Violet
        for i in range(16, 22): self.priority[i] = 50.0 # Production Buildings
        
        # Pass is always lowest except when forced
        self.priority[15] = 1.0


class ShipperBot(BaseHeuristicBot):
    """
    Prioritizes Craftsman, Captain, and Production/Shipping infrastructure.
    """
    def __init__(self, action_dim=200):
        super().__init__(action_dim)
        
        self.priority[:] = 10.0
        
        # Role selection: Craftsman > Captain > Trader
        self.priority[3] = 100.0 # CRAFTSMAN
        self.priority[5] = 90.0  # CAPTAIN
        self.priority[4] = 80.0  # TRADER
        
        # Builder: Production & Shipping infrastructure
        self.priority[16 + 16] = 100.0 # HARBOR
        self.priority[16 + 17] = 100.0 # WHARF
        self.priority[16 + 11] = 80.0  # OFFICE
        for i in range(16, 22): self.priority[i] = 90.0 # Production Buildings
        
        # Captain: Always load as much as possible
        for i in range(44, 64): self.priority[i] = 100.0 
        
        self.priority[15] = 1.0


class RandomBot(BaseHeuristicBot):
    def __init__(self, action_dim=200):
        super().__init__(action_dim)
        self.is_random = True
