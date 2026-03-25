"""
Bot Service — PPO / HPPO inference aligned with training environment.

Model type is selected via MODEL_TYPE env var:
  MODEL_TYPE=ppo        → Agent (standard PPO, PPO_MODEL_FILENAME)
  MODEL_TYPE=hppo       → PhasePPOAgent (hierarchical, HPPO_MODEL_FILENAME)

Phase extraction mirrors train_hppo_selfplay_server.py exactly:
  phase_id = int(obs_dict["global_state"]["current_phase"])
"""
import asyncio
import logging
import os
import sys
import torch
from typing import Dict, Any
from uuid import UUID

from app.engine_wrapper.wrapper import EngineWrapper

logger = logging.getLogger(__name__)

# Ensure PuCo_RL is in path for model loading
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL")))
try:
    from agents.ppo_agent import Agent, PhasePPOAgent
    from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
    from env.pr_env import PuertoRicoEnv
except ImportError:
    logger.exception("Failed to import PuCo_RL modules")


# ---------------------------------------------------------------------------
# Helpers (identical to train_hppo_selfplay_server.py)
# ---------------------------------------------------------------------------

def _extract_phase_id(obs_dict: dict) -> int:
    """Extract current phase integer from observation dict.

    Mirrors: extract_phase_id() in train_hppo_selfplay_server.py
      → int(obs_dict["global_state"]["current_phase"])
    """
    return int(obs_dict["global_state"]["current_phase"])


def _build_obs_space():
    """Build observation space once for flattening — matches training num_players=3."""
    dummy_env = PuertoRicoEnv(num_players=3)
    dummy_env.reset()
    space = dummy_env.observation_space(dummy_env.possible_agents[0])["observation"]
    dim = get_flattened_obs_dim(space)
    return space, dim


class BotService:
    _agent_instance = None
    _model_type: str = None   # "ppo" or "hppo"
    _obs_space = None
    _obs_dim: int = None

    # -----------------------------------------------------------------------
    # Initialisation (lazy, called once)
    # -----------------------------------------------------------------------

    @classmethod
    def _init(cls):
        """Load model and cache obs_space.  Called at most once."""
        # Observation space — shared by both model types
        cls._obs_space, cls._obs_dim = _build_obs_space()

        model_type = os.getenv("MODEL_TYPE", "ppo").lower()
        device = torch.device("cpu")

        if model_type == "hppo":
            cls._model_type = "hppo"
            agent = PhasePPOAgent(obs_dim=cls._obs_dim, action_dim=200).to(device)
            model_filename = os.getenv(
                "HPPO_MODEL_FILENAME", "HPPO_PR_Server_1774241514_step_14745600.pth"
            )
        else:
            cls._model_type = "ppo"
            agent = Agent(obs_dim=cls._obs_dim, action_dim=200).to(device)
            model_filename = os.getenv("PPO_MODEL_FILENAME", "ppo_agent_update_100.pth")

        model_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), f"../../../PuCo_RL/models/{model_filename}")
        )

        if os.path.exists(model_path):
            try:
                checkpoint = torch.load(model_path, map_location=device, weights_only=True)
                state_dict = (
                    checkpoint["model_state_dict"]
                    if "model_state_dict" in checkpoint
                    else checkpoint
                )
                agent.load_state_dict(state_dict, strict=True)
                logger.info(
                    "Loaded %s weights (strict=True) from %s", cls._model_type.upper(), model_path
                )
            except RuntimeError as e:
                # Architecture mismatch — fall back to strict=False and warn loudly
                logger.error(
                    "strict=True load failed for %s: %s — retrying strict=False. "
                    "Check MODEL_TYPE matches the checkpoint architecture.",
                    model_path, e,
                )
                checkpoint = torch.load(model_path, map_location=device, weights_only=True)
                state_dict = (
                    checkpoint["model_state_dict"]
                    if "model_state_dict" in checkpoint
                    else checkpoint
                )
                agent.load_state_dict(state_dict, strict=False)
            except Exception as e:
                logger.error(
                    "Failed to load %s weights: %s — using random init.", cls._model_type.upper(), e
                )
        else:
            logger.warning(
                "%s weights not found at %s — using uninitialized bot.", cls._model_type.upper(), model_path
            )

        agent.eval()
        cls._agent_instance = agent

    @classmethod
    def get_agent(cls):
        if cls._agent_instance is None:
            cls._init()
        return cls._agent_instance

    # -----------------------------------------------------------------------
    # Inference
    # -----------------------------------------------------------------------

    @staticmethod
    def get_action(game_context: Dict[str, Any]) -> int:
        """
        Universal Agent Interface.

        For standard PPO:   agent.get_action_and_value(obs, mask)
        For HPPO:           agent.get_action_and_value(obs, mask, phase_ids=phase_t)
        Mirrors training inference in train_hppo_selfplay_server.py.
        """
        BotService.get_agent()  # ensure _init() ran

        raw_obs = game_context["vector_obs"]
        action_mask = game_context["action_mask"]

        # Flatten observation — use cached obs_space (no dummy env construction here)
        flat_obs = flatten_dict_observation(raw_obs, BotService._obs_space)

        obs_tensor = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
        mask_tensor = torch.as_tensor(action_mask, dtype=torch.float32).unsqueeze(0)

        agent = BotService._agent_instance

        with torch.no_grad():
            if BotService._model_type == "hppo":
                # Extract phase from observation dict — same as training
                phase_id = _extract_phase_id(raw_obs)
                phase_t = torch.tensor([phase_id], dtype=torch.long)
                action_sample, _, _, _ = agent.get_action_and_value(
                    obs_tensor, mask_tensor, phase_ids=phase_t
                )
            else:
                action_sample, _, _, _ = agent.get_action_and_value(obs_tensor, mask_tensor)

        return action_sample.item()

    # -----------------------------------------------------------------------
    # Async bot turn runner
    # -----------------------------------------------------------------------

    @staticmethod
    async def run_bot_turn(
        game_id: UUID,
        engine: EngineWrapper,
        actor_id: str,
        process_action_callback,
    ):
        """Background task to execute a bot's turn with UX delay."""
        mask = engine.get_action_mask()
        is_role_selection = sum(mask[0:8]) > 0 and any(mask[0:8])
        delay = 2.0 if is_role_selection else 1.0
        logger.debug("Bot waiting %.1fs for game %s (actor %s)", delay, game_id, actor_id)
        await asyncio.sleep(delay)

        game_context = {
            "vector_obs": engine.last_obs,
            "action_mask": mask,
            "phase_id": engine.last_info.get("current_phase_id", 8),
        }

        try:
            action_int = BotService.get_action(game_context)
            logger.debug("Bot selected action %d for game %s", action_int, game_id)
        except Exception as e:
            logger.error("Bot inference error for game %s: %s", game_id, e, exc_info=True)
            action_int = 15  # fallback: Pass

        try:
            if asyncio.iscoroutinefunction(process_action_callback):
                await process_action_callback(game_id, actor_id, action_int)
            else:
                process_action_callback(game_id, actor_id, action_int)
        except Exception as e:
            logger.error("Bot action application failed for game %s: %s", game_id, e)
