"""
Bot Service — Unified Agent Serving via AgentFactory.
Supports Legacy PPO, Residual PPO, and PhasePPO with safe fallback.
"""
import asyncio
import logging
import os
import sys
import torch
import numpy as np
from typing import Dict, Any, Optional
from uuid import UUID

from app.engine_wrapper.wrapper import EngineWrapper
from app.services.agents.factory import AgentFactory
from app.services.agents.wrappers import AgentWrapper

logger = logging.getLogger(__name__)

# Ensure PuCo_RL is in path for utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL")))
try:
    from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
    from env.pr_env import PuertoRicoEnv
except ImportError:
    logger.exception("Failed to import PuCo_RL modules")

def _extract_phase_id(obs_dict: dict) -> int:
    """Extract current phase integer from observation dict with robustness."""
    try:
        phase = obs_dict["global_state"]["current_phase"]
        if hasattr(phase, 'item'):
            phase = phase.item()  # Handle numpy scalar
        val = int(phase)
        return min(max(0, val), 9)  # Clamp to valid range (0-9)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        return 8 # Default to Role Selection/End Round

def _build_obs_space():
    """Build observation space once for flattening."""
    dummy_env = PuertoRicoEnv(num_players=3)
    dummy_env.reset()
    space = dummy_env.observation_space(dummy_env.possible_agents[0])["observation"]
    dim = get_flattened_obs_dim(space)
    return space, dim

class BotService:
    _agent_wrapper: Optional[AgentWrapper] = None
    _obs_space = None
    _obs_dim: int = None

    @classmethod
    def _init(cls):
        """Initialize observation space and load agent via factory."""
        if cls._obs_space is None:
            cls._obs_space, cls._obs_dim = _build_obs_space()

        model_type = os.getenv("MODEL_TYPE", "legacy_ppo").lower()
        
        # Determine model filename based on type
        if model_type == "hppo" or model_type == "phase_ppo":
            model_filename = os.getenv("HPPO_MODEL_FILENAME", "HPPO_PR_Server_1774241514_step_14745600.pth")
        else:
            model_filename = os.getenv("PPO_MODEL_FILENAME", "ppo_agent_update_100.pth")

        model_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), f"../../../PuCo_RL/models/{model_filename}")
        )

        logger.info(f"BotService initializing with {model_type} from {model_path}")
        cls._agent_wrapper = AgentFactory.get_agent(model_path)

    @classmethod
    def get_agent_wrapper(cls) -> AgentWrapper:
        if cls._agent_wrapper is None:
            cls._init()
        return cls._agent_wrapper

    @staticmethod
    def get_action(game_context: Dict[str, Any]) -> int:
        """Universal Agent Interface using Wrapper."""
        wrapper = BotService.get_agent_wrapper()

        raw_obs = game_context["vector_obs"]
        action_mask = game_context["action_mask"]
        phase_id = game_context.get("phase_id", 8)

        # Flatten observation
        flat_obs = flatten_dict_observation(raw_obs, BotService._obs_space)
        obs_tensor = torch.as_tensor(flat_obs, dtype=torch.float32)
        mask_tensor = torch.as_tensor(action_mask, dtype=torch.float32)

        # Use wrapper for inference
        action = wrapper.act(obs_tensor, mask_tensor, phase_id=phase_id)
        logger.warning(
            "[BOT_TRACE] selected_action phase_id=%s action=%s valid=%s",
            phase_id,
            action,
            (0 <= action < len(action_mask) and bool(action_mask[action])) if action_mask else False,
        )
        return action

    @staticmethod
    async def run_bot_turn(
        game_id: UUID,
        engine: EngineWrapper,
        actor_id: str,
        process_action_callback,
    ):
        """Background task to execute a bot's turn with UX delay."""
        logger.warning(
            "[BOT_TRACE] turn_start game=%s actor=%s current_player_idx=%s governor_idx=%s agent_selection=%s",
            game_id,
            actor_id,
            getattr(engine.env.game, "current_player_idx", None),
            getattr(engine.env.game, "governor_idx", None),
            getattr(engine.env, "agent_selection", None),
        )
        try:
            mask = engine.get_action_mask()
            valid_count = sum(1 for v in mask if v > 0.5)
            logger.warning(
                "[BOT_TRACE] turn_mask game=%s actor=%s valid_actions=%d current_player_idx=%s governor_idx=%s agent_selection=%s",
                game_id,
                actor_id,
                valid_count,
                getattr(engine.env.game, "current_player_idx", None),
                getattr(engine.env.game, "governor_idx", None),
                getattr(engine.env, "agent_selection", None),
            )

            # Detect role selection phase (indices 0-7 are roles)
            is_role_selection = any(mask[0:8])
            
            # Enhanced UX delay as per report.md
            delay = 3.0 if is_role_selection else 2.0
            
            logger.warning("[BOT_TRACE] turn_delay game=%s actor=%s delay=%.1fs role_selection=%s", game_id, actor_id, delay, is_role_selection)
            await asyncio.sleep(delay)

            # Extract phase_id for PhasePPO support
            current_phase = _extract_phase_id(engine.last_obs)
            logger.warning(
                "[BOT_TRACE] phase_id game=%s actor=%s phase_id=%s",
                game_id,
                actor_id,
                current_phase,
            )

            game_context = {
                "vector_obs": engine.last_obs,
                "action_mask": mask,
                "phase_id": current_phase,
            }

            # 1. Attempt Model Inference
            try:
                action_int = BotService.get_action(game_context)
                logger.warning("[BOT_TRACE] turn_action_selected game=%s actor=%s action=%d phase=%d", game_id, actor_id, action_int, current_phase)
            except Exception as e:
                logger.exception("[BOT] inference error for game %s. Falling back to random.", game_id)
                valid_indices = [i for i, v in enumerate(mask) if v > 0.5]
                action_int = int(np.random.choice(valid_indices)) if valid_indices else 15

            # 2. Attempt Action Application with Retry Safety Net
            try:
                if asyncio.iscoroutinefunction(process_action_callback):
                    await process_action_callback(game_id, actor_id, action_int)
                else:
                    process_action_callback(game_id, actor_id, action_int)
                logger.warning("[BOT_TRACE] turn_action_applied game=%s actor=%s action=%d", game_id, actor_id, action_int)
            except Exception as e:
                logger.error("[BOT] action %d REJECTED for game %s: %s. Attempting fallback retry...", action_int, game_id, e)
                
                # Action was rejected (likely an engine rule violation like Mayor Pass)
                # Try a random valid action from the CURRENT mask to keep the game moving.
                try:
                    # Refresh mask in case engine state changed (unlikely but safe)
                    retry_mask = engine.get_action_mask()
                    valid_indices = [i for i, v in enumerate(retry_mask) if v > 0.5 and i != action_int]
                    
                    if valid_indices:
                        fallback_action = int(np.random.choice(valid_indices))
                        logger.warning("[BOT] retrying game %s with fallback action %d", game_id, fallback_action)
                        if asyncio.iscoroutinefunction(process_action_callback):
                            await process_action_callback(game_id, actor_id, fallback_action)
                        else:
                            process_action_callback(game_id, actor_id, fallback_action)
                    else:
                        logger.critical("[BOT] no valid fallback actions found for game %s. Game is likely STUCK.", game_id)
                except Exception as retry_err:
                    logger.critical("[BOT] fallback retry ALSO FAILED for game %s: %s", game_id, retry_err, exc_info=True)
        except Exception as e:
            logger.critical("[BOT] UNHANDLED ERROR in run_bot_turn game=%s actor=%s: %s", 
                            game_id, actor_id, e, exc_info=True)
