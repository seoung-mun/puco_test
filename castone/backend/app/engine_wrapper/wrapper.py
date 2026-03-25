import os
import sys
from typing import Any, Dict, List
import numpy as np

# Ensure PuCo_RL is in path if running locally without Docker
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL")))

try:
    from env.pr_env import PuertoRicoEnv
except ImportError:
    import traceback
    traceback.print_exc()
    PuertoRicoEnv = None

class EngineWrapper:
    def __init__(self, num_players: int = 3, max_game_steps: int = 1200):
        if PuertoRicoEnv is None:
            raise RuntimeError("PuertoRicoEnv could not be imported. Check PYTHONPATH.")
        self.env = PuertoRicoEnv(num_players=num_players, max_game_steps=max_game_steps)
        self.env.reset()
        # PettingZoo AEC retrieve observation via observe()
        obs_dict = self.env.observe(self.env.agent_selection)
        self.last_obs = obs_dict["observation"]
        self.last_info = self.env.infos[self.env.agent_selection]
        self.last_action_mask = obs_dict["action_mask"]
        # Round/step tracking for DB logging
        self._step_count = 0
        self._round_count = 0
        self._last_governor = self.env.game.governor_idx

    def get_state(self) -> Dict[str, Any]:
        """Returns the current state/observation as a serializable dict."""
        # Use the last_obs which is updated after each step or reset
        return self._sanitize_obs(self.last_obs)

    def get_action_mask(self) -> List[int]:
        """Returns the current valid action mask as a list of 0/1."""
        # Use the last_action_mask which is updated after each step or reset
        return self.last_action_mask.tolist() if hasattr(self.last_action_mask, "tolist") else list(self.last_action_mask)

    def step(self, action: int) -> Dict[str, Any]:
        """
        Executes an action and returns a dictionary containing:
        - state_before
        - action
        - action_mask (before action)
        - state_after
        - reward
        - done
        - info
        """
        state_before = self.get_state()
        mask_before = self.get_action_mask()
        
        # apply action
        self.env.step(action)
        
        # update current state using observe() as PettingZoo AEC step returns None
        obs_dict = self.env.observe(self.env.agent_selection)
        self.last_obs = obs_dict["observation"]
        self.last_info = self.env.infos[self.env.agent_selection]
        self.last_action_mask = obs_dict["action_mask"]

        # Retrieve reward, done, truncated from env properties
        reward = self.env.rewards[self.env.agent_selection]
        done = self.env.terminations[self.env.agent_selection]
        truncated = self.env.truncations[self.env.agent_selection]

        # Track round/step
        self._step_count += 1
        if self.env.game.governor_idx != self._last_governor:
            self._round_count += 1
            self._last_governor = self.env.game.governor_idx

        info = dict(self.last_info) if self.last_info else {}
        info["round"] = self._round_count
        info["step"] = self._step_count

        state_after = self.get_state()
        
        return {
            "state_before": state_before,
            "action": action,
            "action_mask": mask_before,
            "state_after": state_after,
            "reward": float(reward) if isinstance(reward, (int, float, np.number)) else [float(r) for r in reward],
            "done": bool(done or truncated),
            "terminated": bool(done),
            "truncated": bool(truncated),
            "info": info
        }

    def _sanitize_obs(self, obs: Any) -> Any:
        """Converts numpy types in observation to JSON serializable types."""
        if isinstance(obs, dict):
            return {k: self._sanitize_obs(v) for k, v in obs.items()}
        elif isinstance(obs, np.ndarray):
            if obs.ndim == 0:
                return obs.item()
            return [self._sanitize_obs(i) for i in obs]
        elif isinstance(obs, (list, tuple)):
            return [self._sanitize_obs(i) for i in obs]
        elif isinstance(obs, (np.integer, np.floating)):
            return obs.item()
        elif isinstance(obs, np.ndarray):
            return obs.tolist()
        return obs

def create_game_engine(num_players: int = 3) -> EngineWrapper:
    return EngineWrapper(num_players=num_players)
