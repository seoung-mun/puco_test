import logging
import inspect
from typing import Any, Dict, List, Optional
import numpy as np
from app.services.engine_gateway.bootstrap import ensure_puco_rl_path

# Keep all non-legacy PuCo_RL path bootstrapping routed through engine_gateway.
ensure_puco_rl_path()

try:
    from env.pr_env import PuertoRicoEnv
except ImportError:
    import traceback
    traceback.print_exc()
    PuertoRicoEnv = None

logger = logging.getLogger(__name__)

class EngineWrapper:
    def __init__(
        self,
        num_players: int = 3,
        max_game_steps: int = 1200,
        game_seed: Optional[int] = None,
        governor_idx: Optional[int] = None,
        **env_kwargs: Any,
    ):
        if PuertoRicoEnv is None:
            raise RuntimeError("PuertoRicoEnv could not be imported. Check PYTHONPATH.")
        supported_env_kwargs = self._filter_env_kwargs(env_kwargs)
        self.env = PuertoRicoEnv(
            num_players=num_players,
            max_game_steps=max_game_steps,
            **supported_env_kwargs,
        )

        self._reset_environment(game_seed=game_seed, governor_idx=governor_idx)

        # PettingZoo AEC retrieve observation via observe()
        self._refresh_cached_view()
        # Round/step tracking for DB logging
        self._step_count = 0
        self._round_count = 0
        self._last_governor = self.env.game.governor_idx

    @staticmethod
    def _filter_env_kwargs(env_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Drop backend-only kwargs when the upstream env signature does not support them."""
        if not env_kwargs:
            return {}
        if PuertoRicoEnv is None:
            return dict(env_kwargs)

        signature = inspect.signature(PuertoRicoEnv.__init__)
        supports_var_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
        if supports_var_kwargs:
            return dict(env_kwargs)

        accepted = {
            name
            for name, param in signature.parameters.items()
            if name != "self"
            and param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        }
        filtered = {key: value for key, value in env_kwargs.items() if key in accepted}
        dropped = sorted(set(env_kwargs) - set(filtered))
        if dropped:
            logger.warning(
                "Dropping unsupported PuertoRicoEnv kwargs for current upstream signature: %s",
                ", ".join(dropped),
            )
        return filtered

    def _reset_environment(self, game_seed: Optional[int], governor_idx: Optional[int]) -> None:
        if governor_idx is None:
            self.env.reset(seed=game_seed)
            return

        if governor_idx < 0 or governor_idx >= self.env.num_players:
            raise ValueError(
                f"governor_idx must be between 0 and {self.env.num_players - 1}, got {governor_idx}"
            )

        # Re-run reset until the engine itself chooses the requested governor.
        # This preserves all governor-dependent setup, including initial plantations.
        max_attempts = 64
        for attempt in range(max_attempts):
            seed = None if game_seed is None else game_seed + attempt
            self.env.reset(seed=seed)
            if self.env.game.governor_idx == governor_idx:
                return

        raise RuntimeError(
            f"Unable to initialize engine with governor_idx={governor_idx} after {max_attempts} attempts"
        )

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
        phase_before = getattr(self.env.game, "current_phase", None)
        player_before = getattr(self.env.game, "current_player_idx", None)
        logger.warning(
            "[ACTION_TRACE] engine_step_enter action=%s phase_before=%s current_player_idx_before=%s agent_selection=%s",
            action,
            phase_before,
            player_before,
            getattr(self.env, "agent_selection", None),
        )
        
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
        logger.warning(
            "[ACTION_TRACE] engine_step_exit action=%s phase_after=%s current_player_idx_after=%s terminated=%s truncated=%s",
            action,
            getattr(self.env.game, "current_phase", None),
            getattr(self.env.game, "current_player_idx", None),
            bool(done),
            bool(truncated),
        )
        
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

def create_game_engine(
    num_players: int = 3,
    game_seed: Optional[int] = None,
    governor_idx: Optional[int] = None,
    **env_kwargs: Any,
) -> EngineWrapper:
    return EngineWrapper(
        num_players=num_players,
        game_seed=game_seed,
        governor_idx=governor_idx,
        **env_kwargs,
    )
