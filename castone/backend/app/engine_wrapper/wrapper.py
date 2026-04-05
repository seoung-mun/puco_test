import os
import sys
from typing import Any, Dict, List, Optional
import numpy as np

# Ensure PuCo_RL is in path if running locally without Docker
PUCO_RL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL"))
if PUCO_RL_PATH not in sys.path:
    sys.path.append(PUCO_RL_PATH)

try:
    from env.pr_env import PuertoRicoEnv
except ImportError:
    import traceback
    traceback.print_exc()
    PuertoRicoEnv = None

class EngineWrapper:
    def __init__(
        self,
        num_players: int = 3,
        max_game_steps: int = 1200,
        **env_kwargs: Any,
    ):
        if PuertoRicoEnv is None:
            raise RuntimeError("PuertoRicoEnv could not be imported. Check PYTHONPATH.")
        self.env = PuertoRicoEnv(
            num_players=num_players,
            max_game_steps=max_game_steps,
            **env_kwargs,
        )
        
        # Ensure governor is always player_0 (room owner) for UI consistency
        # We repeat reset() until governor_idx is 0 to maintain internal state consistency
        # (e.g. plantation distribution depends on who is the governor)
        for _ in range(100):
            self.env.reset()
            if self.env.game.governor_idx == 0:
                break
        else:
            # Fallback (should not happen statistically)
            self.env.game.governor_idx = 0
            self.env.game.current_player_idx = 0

        # PettingZoo AEC retrieve observation via observe()
        self._refresh_cached_view()
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
        self._refresh_cached_view()

        # Retrieve reward, done, truncated from env properties
        reward = self.env.rewards[self.env.agent_selection]
        done = self.env.terminations[self.env.agent_selection]
        truncated = self.env.truncations[self.env.agent_selection]

        # Track round/step
        self._step_count += 1
        if self.env.game.governor_idx != self._last_governor:
            self._round_count += 1
            self._last_governor = self.env.game.governor_idx

        self.last_info["current_phase_id"] = int(getattr(self.env.game, "current_phase", 8))
        self.last_info["current_player_idx"] = int(getattr(self.env.game, "current_player_idx", -1))
        self.last_info["step_count"] = self._step_count

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

    def _refresh_cached_view(self) -> None:
        obs_dict = self.env.observe(self.env.agent_selection)
        observation, action_mask = self._extract_observation(obs_dict)
        self.last_obs = observation
        self.last_info = dict(self.env.infos.get(self.env.agent_selection, {}))
        self.last_info.setdefault("current_phase_id", int(getattr(self.env.game, "current_phase", 8)))
        self.last_info.setdefault("current_player_idx", int(getattr(self.env.game, "current_player_idx", -1)))
        self.last_info.setdefault("step_count", int(getattr(self, "_step_count", 0)))
        self.last_action_mask = action_mask

    def _extract_observation(self, obs_dict: Any) -> tuple[Any, Any]:
        """Normalize different observe() payload shapes into observation + mask."""
        if isinstance(obs_dict, dict):
            if "observation" in obs_dict:
                observation = obs_dict["observation"]
            else:
                # Fallback for envs that already expose a dict observation directly.
                observation = obs_dict

            action_mask = obs_dict.get("action_mask")
            if action_mask is None:
                inferred = self._infer_action_mask_from_info()
                if inferred is None:
                    raise KeyError("Observation payload is missing action_mask")
                action_mask = inferred
            return observation, action_mask

        inferred = self._infer_action_mask_from_info()
        if inferred is None:
            raise TypeError("Unsupported observation payload returned by environment")
        return obs_dict, inferred

    def _infer_action_mask_from_info(self) -> Optional[Any]:
        info = self.env.infos.get(self.env.agent_selection, {})
        return info.get("action_mask")

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
        return obs

def create_game_engine(num_players: int = 3, **env_kwargs: Any) -> EngineWrapper:
    return EngineWrapper(num_players=num_players, **env_kwargs)
