import asyncio
import os
import sys
import torch
import numpy as np
from typing import Dict, Any
from uuid import UUID

from app.engine_wrapper.wrapper import EngineWrapper

# Ensure PuCo_RL is in path for model loading
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL")))
try:
    from agents.ppo_agent import Agent
    from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
    from env.pr_env import PuertoRicoEnv
except ImportError as e:
    import traceback
    traceback.print_exc()

class BotService:
    _agent_instance = None
    _obs_dim = None

    @classmethod
    def get_agent(cls):
        if cls._agent_instance is None:
            # Determine observation dimension
            dummy_env = PuertoRicoEnv(num_players=3)
            dummy_env.reset()
            obs_space = dummy_env.observation_space(dummy_env.possible_agents[0])["observation"]
            cls._obs_dim = get_flattened_obs_dim(obs_space)
            
            # Load PyTorch Model
            device = torch.device("cpu") # Server-side inference on CPU is fine for small board game MLP
            agent = Agent(obs_dim=cls._obs_dim, action_dim=200).to(device)
            
            model_filename = os.getenv("PPO_MODEL_FILENAME", "ppo_agent_update_100.pth")
            model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), f"../../../PuCo_RL/models/{model_filename}"))
            
            if os.path.exists(model_path):
                try:
                    checkpoint = torch.load(model_path, map_location=device)
                    # Handle both raw state_dict and dict containing 'model_state_dict'
                    if "model_state_dict" in checkpoint:
                        agent.load_state_dict(checkpoint["model_state_dict"], strict=False)
                    else:
                        agent.load_state_dict(checkpoint, strict=False)
                    print(f"[BotService] Successfully loaded PPO weights (strict=False) from {model_path}")
                except Exception as e:
                    print(f"[BotService] ERROR loading weights: {e}. Falling back to random init.")
            else:
                print(f"[BotService] WARNING: Could not find weights at {model_path}. Using uninitialized PPO bot.")
            
            agent.eval()
            cls._agent_instance = agent
            
        return cls._agent_instance

    @staticmethod
    async def run_bot_turn(game_id: UUID, engine: EngineWrapper, actor_id: str,
                           process_action_callback):
        """
        Background task to execute a bot's turn with dynamic delays.
        """
        # 1. Dynamic UX Delay Calculation
        phase_id = engine.last_info.get("current_phase_id", 9)
        mask = engine.get_action_mask()
        is_role_selection = any(mask[0:8]) and sum(mask[0:8]) > 0
        
        delay = 2.0 if is_role_selection else 1.0
        print(f"[BotService] Waiting {delay}s for game {game_id} (actor {actor_id})")
        await asyncio.sleep(delay)

        # 2. Universal Agent Interface Context
        game_context = {
            "vector_obs": engine.last_obs,
            "engine_instance": engine.env.game,
            "action_mask": mask,
            "phase_id": phase_id
        }

        # 3. Request Action
        try:
            action_int = BotService.get_action(game_context)
            print(f"[BotService] Inference selected action: {action_int}")
        except Exception as e:
            print(f"[BotService] Inference error: {e}")
            import traceback
            traceback.print_exc()
            action_int = 15  # TDD D-2 Edge Case: Fallback to Pass to prevent freezing

        # 4. Apply Action
        try:
            if asyncio.iscoroutinefunction(process_action_callback):
                await process_action_callback(game_id, actor_id, action_int)
            else:
                process_action_callback(game_id, actor_id, action_int)
        except Exception as e:
            print(f"[BotService] Action application failed for {game_id}: {e}")

    @staticmethod
    def get_action(game_context: Dict[str, Any]) -> int:
        """
        Universal Agent Interface.
        Executes PPO model inference natively.
        """
        agent = BotService.get_agent()
        raw_obs = game_context["vector_obs"]
        action_mask = game_context["action_mask"]
        
        # Flatten dictionary
        dummy_env = PuertoRicoEnv(num_players=3) # Needed just for space definition structure
        obs_space = dummy_env.observation_space("player_0")["observation"]
        flat_obs = flatten_dict_observation(raw_obs, obs_space)
        
        # Convert to Tensor
        obs_tensor = torch.Tensor(flat_obs).unsqueeze(0)
        mask_tensor = torch.Tensor(action_mask).unsqueeze(0)
        
        with torch.no_grad():
            action_sample, _, _, _ = agent.get_action_and_value(obs_tensor, mask_tensor)
            
        return action_sample.item()
