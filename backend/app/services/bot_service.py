"""
Bot Service — Unified Agent Serving via AgentFactory.
Supports Legacy PPO, Residual PPO, and PhasePPO with safe fallback.
"""
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Optional

import torch
import numpy as np
from uuid import UUID

from app.engine_wrapper.wrapper import EngineWrapper
from app.services.agent_registry import (
    get_wrapper,
    require_valid_bot_type,
    resolve_bot_type_from_actor_id,
)
from app.services.mayor_strategy_adapter import MayorStrategyAdapter
from app.services.state_serializer import apply_backend_action_mask_guards

logger = logging.getLogger(__name__)

# Ensure PuCo_RL is in path for utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL")))
try:
    from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
    from env.pr_env import PuertoRicoEnv
    from configs.constants import Phase
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


@dataclass(frozen=True)
class BotInputSnapshot:
    bot_type: str
    obs: Dict[str, Any]
    action_mask: list[int]
    phase_id: int
    current_player_idx: int
    step_count: int

class BotService:
    _obs_space = None
    _obs_dim: Optional[int] = None

    @classmethod
    def _ensure_obs_space(cls):
        if cls._obs_space is None:
            cls._obs_space, cls._obs_dim = _build_obs_space()

    @classmethod
    def get_agent_wrapper(cls, bot_type: str):
        cls._ensure_obs_space()
        normalized = require_valid_bot_type(bot_type)
        return get_wrapper(normalized, cls._obs_dim)

    @staticmethod
    def guard_action_mask(
        engine: EngineWrapper,
        action_mask: Optional[list[int]] = None,
    ) -> list[int]:
        raw_mask = list(action_mask if action_mask is not None else engine.get_action_mask())
        return apply_backend_action_mask_guards(engine.env.game, raw_mask)

    @staticmethod
    def build_input_snapshot(
        engine: EngineWrapper,
        actor_id: str,
        action_mask: Optional[list[int]] = None,
    ) -> BotInputSnapshot:
        mask = BotService.guard_action_mask(engine, action_mask)
        obs = engine.last_obs
        phase_id = _extract_phase_id(obs)
        current_player_idx = getattr(engine.env.game, "current_player_idx", -1)
        step_count = getattr(engine, "_step_count", 0)
        bot_type = resolve_bot_type_from_actor_id(actor_id)
        return BotInputSnapshot(
            bot_type=bot_type,
            obs=obs,
            action_mask=mask,
            phase_id=phase_id,
            current_player_idx=current_player_idx,
            step_count=step_count,
        )

    @staticmethod
    def get_action(bot_type: str, game_context: Dict[str, Any]) -> int:
        """Universal Agent Interface using Wrapper."""
        wrapper = BotService.get_agent_wrapper(bot_type)

        raw_obs = game_context["vector_obs"]
        action_mask = game_context["action_mask"]
        phase_id = game_context.get("phase_id", 8)
        current_player_idx = game_context.get("current_player_idx")

        # Flatten observation
        BotService._ensure_obs_space()
        flat_obs = flatten_dict_observation(raw_obs, BotService._obs_space)
        obs_tensor = torch.as_tensor(flat_obs, dtype=torch.float32)
        mask_tensor = torch.as_tensor(action_mask, dtype=torch.float32)
        if obs_tensor.dim() == 1:
            obs_tensor = obs_tensor.unsqueeze(0)
        if mask_tensor.dim() == 1:
            mask_tensor = mask_tensor.unsqueeze(0)

        # Use wrapper for inference
        action = wrapper.act(
            obs_tensor,
            mask_tensor,
            phase_id=phase_id,
            obs_dict=raw_obs,
            player_idx=current_player_idx,
        )
        logger.warning(
            "[BOT_TRACE] selected_action bot_type=%s phase_id=%s action=%s valid=%s",
            bot_type,
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
            mask = BotService.guard_action_mask(engine)
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

            snapshot = BotService.build_input_snapshot(
                engine=engine,
                actor_id=actor_id,
                action_mask=mask,
            )
            logger.warning(
                "[BOT_TRACE] input_snapshot game=%s actor=%s bot_type=%s phase_id=%s current_player_idx=%s step_count=%s",
                game_id,
                actor_id,
                snapshot.bot_type,
                snapshot.phase_id,
                snapshot.current_player_idx,
                snapshot.step_count,
            )

            game_context = {
                "vector_obs": snapshot.obs,
                "action_mask": snapshot.action_mask,
                "phase_id": snapshot.phase_id,
                "current_player_idx": snapshot.current_player_idx,
            }

            # ── Mayor phase: adapter 경유 (봇 전용) ──
            is_mayor_phase = getattr(engine.env.game, "current_phase", None) == Phase.MAYOR

            if is_mayor_phase:
                # Mayor mask: action 72를 invalid로 설정 (봇은 strategy 0/1/2만 선택)
                mayor_mask = list(mask)
                mayor_mask[72] = 0
                mayor_game_context = {
                    "vector_obs": snapshot.obs,
                    "action_mask": mayor_mask,
                    "phase_id": snapshot.phase_id,
                    "current_player_idx": snapshot.current_player_idx,
                }

                # 1. 봇 추론: strategy 선택 (action 69-71)
                try:
                    strategy_action = BotService.get_action(snapshot.bot_type, mayor_game_context)
                    logger.warning(
                        "[BOT_TRACE] mayor_strategy_selected game=%s actor=%s bot_type=%s strategy_action=%d",
                        game_id, actor_id, snapshot.bot_type, strategy_action,
                    )
                except Exception as e:
                    logger.exception("[BOT] Mayor inference error for game %s. Falling back to strategy 0.", game_id)
                    strategy_action = 69  # fallback to CAPTAIN_FOCUS

                # 봇이 69-71 범위 외의 action을 선택한 경우 fallback
                if not (69 <= strategy_action <= 71):
                    logger.warning(
                        "[BOT_TRACE] mayor_strategy_out_of_range game=%s actor=%s action=%d, falling back to 69",
                        game_id, actor_id, strategy_action,
                    )
                    strategy_action = 69

                # 2. adapter로 expansion
                adapter = MayorStrategyAdapter()
                strategy = strategy_action - 69
                sequential_actions = adapter.expand(
                    strategy=strategy,
                    game=engine.env.game,
                    player_idx=engine.env.game.current_player_idx,
                )
                logger.warning(
                    "[BOT_TRACE] mayor_expand game=%s actor=%s strategy=%d actions=%s",
                    game_id, actor_id, strategy, sequential_actions,
                )

                # 3. sequential actions를 engine에 순차 적용
                # 중간 step은 suppress_broadcast=True, 마지막 step만 broadcast
                try:
                    for i, seq_action in enumerate(sequential_actions):
                        is_last = (i == len(sequential_actions) - 1)
                        if asyncio.iscoroutinefunction(process_action_callback):
                            await process_action_callback(game_id, actor_id, seq_action, suppress_broadcast=not is_last)
                        else:
                            process_action_callback(game_id, actor_id, seq_action, suppress_broadcast=not is_last)
                    logger.warning(
                        "[BOT_TRACE] mayor_complete game=%s actor=%s actions_applied=%d",
                        game_id, actor_id, len(sequential_actions),
                    )
                except Exception as e:
                    logger.critical(
                        "[BOT] Mayor sequential apply FAILED for game %s at action: %s",
                        game_id, e, exc_info=True,
                    )

            else:
                # ── 비-Mayor phase: 기존 로직 그대로 ──

                # 1. Attempt Model Inference
                try:
                    action_int = BotService.get_action(snapshot.bot_type, game_context)
                    logger.warning(
                        "[BOT_TRACE] turn_action_selected game=%s actor=%s bot_type=%s action=%d phase=%d",
                        game_id,
                        actor_id,
                        snapshot.bot_type,
                        action_int,
                        snapshot.phase_id,
                    )
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
                        retry_mask = BotService.guard_action_mask(engine, retry_mask)
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
