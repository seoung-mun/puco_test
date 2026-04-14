"""
Bot Service — Unified Agent Serving via AgentFactory.
Supports Legacy PPO, Residual PPO, and PhasePPO with safe fallback.
"""
import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import torch
import numpy as np
from uuid import UUID

from app.engine_wrapper.wrapper import EngineWrapper
from app.services.engine_gateway.constants import Phase
from app.services.engine_gateway.env import (
    PuertoRicoEnv,
    flatten_dict_observation,
    get_flattened_obs_dim,
)
from app.services.agent_registry import (
    get_wrapper,
    require_valid_bot_type,
    resolve_bot_type_from_actor_id,
)

logger = logging.getLogger(__name__)

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
        return list(action_mask if action_mask is not None else engine.get_action_mask())

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
        env_context = (
            game_context.get("env")
            or game_context.get("engine_env")
            or game_context.get("engine_instance")
        )

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
            env=env_context,
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
    def normalize_selected_action(action: int, action_mask: list[int], phase: Any) -> int:
        is_valid = 0 <= action < len(action_mask) and bool(action_mask[action])
        if phase == Phase.MAYOR:
            # New slot-direct contract: legal actions are 120-131 (island) and 140-151 (city)
            if is_valid and (120 <= action <= 131 or 140 <= action <= 151):
                return action
            # Heuristic bridge: if model returned legacy 69-71 or any invalid action,
            # pick the first legal island slot, then city slot.
            for a in range(120, 132):
                if a < len(action_mask) and action_mask[a]:
                    return a
            for a in range(140, 152):
                if a < len(action_mask) and action_mask[a]:
                    return a
            # No legal Mayor slot — should not happen; engine auto-advances turn
            logger.warning("[BOT] Mayor normalize: no legal slot-direct action found, returning original %d", action)
            return action
        return action

    @staticmethod
    def _current_phase(engine: EngineWrapper):
        game = getattr(getattr(engine, "env", None), "game", None)
        return getattr(game, "current_phase", None)

    @staticmethod
    def _current_player_remaining_colonists(engine: EngineWrapper) -> int:
        game = getattr(getattr(engine, "env", None), "game", None)
        if game is None:
            return 0

        try:
            current_player_idx = int(getattr(game, "current_player_idx", -1))
            players = getattr(game, "players", [])
            if current_player_idx < 0 or current_player_idx >= len(players):
                return 0
            remaining = getattr(players[current_player_idx], "unplaced_colonists", 0)
            return max(0, int(remaining))
        except (TypeError, ValueError, IndexError):
            return 0

    @staticmethod
    def _has_legal_mayor_slot(action_mask: list[int]) -> bool:
        island_legal = any(
            idx < len(action_mask) and bool(action_mask[idx])
            for idx in range(120, 132)
        )
        city_legal = any(
            idx < len(action_mask) and bool(action_mask[idx])
            for idx in range(140, 152)
        )
        return island_legal or city_legal

    @staticmethod
    def _callback_supports_suppress_broadcast(process_action_callback) -> bool:
        try:
            signature = inspect.signature(process_action_callback)
        except (TypeError, ValueError):
            return False

        if "suppress_broadcast" in signature.parameters:
            return True

        return any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )

    @staticmethod
    async def _dispatch_action(
        process_action_callback,
        game_id: UUID,
        actor_id: str,
        action_int: int,
        *,
        suppress_broadcast: bool = False,
        supports_suppress_broadcast: bool = False,
    ):
        kwargs = {}
        if supports_suppress_broadcast:
            kwargs["suppress_broadcast"] = suppress_broadcast

        result = process_action_callback(game_id, actor_id, action_int, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    @staticmethod
    def _select_action_for_current_state(
        game_id: UUID,
        engine: EngineWrapper,
        actor_id: str,
        action_mask: Optional[list[int]] = None,
    ) -> tuple[int, BotInputSnapshot]:
        mask = BotService.guard_action_mask(engine, action_mask)
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
            "env": engine.env,
        }
        phase = BotService._current_phase(engine)

        try:
            action_int = BotService.get_action(snapshot.bot_type, game_context)
            action_int = BotService.normalize_selected_action(
                action=action_int,
                action_mask=snapshot.action_mask,
                phase=phase,
            )
            logger.warning(
                "[BOT_TRACE] turn_action_selected game=%s actor=%s bot_type=%s action=%d phase=%d",
                game_id,
                actor_id,
                snapshot.bot_type,
                action_int,
                snapshot.phase_id,
            )
        except Exception:
            if phase == Phase.MAYOR:
                logger.exception(
                    "[BOT] Mayor inference error for game %s. Falling back to legal slot heuristic.",
                    game_id,
                )
                action_int = BotService.normalize_selected_action(
                    action=-1,
                    action_mask=snapshot.action_mask,
                    phase=phase,
                )
            else:
                logger.exception(
                    "[BOT] inference error for game %s. Falling back to random.",
                    game_id,
                )
                valid_indices = [
                    idx for idx, value in enumerate(mask) if value > 0.5
                ]
                action_int = int(np.random.choice(valid_indices)) if valid_indices else 15

        return action_int, snapshot

    @staticmethod
    async def _apply_action_with_retry(
        game_id: UUID,
        engine: EngineWrapper,
        actor_id: str,
        action_int: int,
        process_action_callback,
        *,
        suppress_broadcast: bool = False,
        supports_suppress_broadcast: bool = False,
    ) -> Optional[int]:
        try:
            await BotService._dispatch_action(
                process_action_callback,
                game_id,
                actor_id,
                action_int,
                suppress_broadcast=suppress_broadcast,
                supports_suppress_broadcast=supports_suppress_broadcast,
            )
            logger.warning(
                "[BOT_TRACE] turn_action_applied game=%s actor=%s action=%d suppress_broadcast=%s",
                game_id,
                actor_id,
                action_int,
                suppress_broadcast,
            )
            return action_int
        except Exception as e:
            logger.error(
                "[BOT] action %d REJECTED for game %s: %s. Attempting fallback retry...",
                action_int,
                game_id,
                e,
            )

            try:
                retry_mask = engine.get_action_mask()
                retry_mask = BotService.guard_action_mask(engine, retry_mask)
                valid_indices = [
                    idx
                    for idx, value in enumerate(retry_mask)
                    if value > 0.5 and idx != action_int
                ]

                if valid_indices:
                    fallback_action = int(np.random.choice(valid_indices))
                    logger.warning(
                        "[BOT] retrying game %s with fallback action %d",
                        game_id,
                        fallback_action,
                    )
                    await BotService._dispatch_action(
                        process_action_callback,
                        game_id,
                        actor_id,
                        fallback_action,
                        suppress_broadcast=suppress_broadcast,
                        supports_suppress_broadcast=supports_suppress_broadcast,
                    )
                    logger.warning(
                        "[BOT_TRACE] turn_fallback_applied game=%s actor=%s action=%d suppress_broadcast=%s",
                        game_id,
                        actor_id,
                        fallback_action,
                        suppress_broadcast,
                    )
                    return fallback_action

                logger.critical(
                    "[BOT] no valid fallback actions found for game %s. Game is likely STUCK.",
                    game_id,
                )
            except Exception as retry_err:
                logger.critical(
                    "[BOT] fallback retry ALSO FAILED for game %s: %s",
                    game_id,
                    retry_err,
                    exc_info=True,
                )

        return None

    @staticmethod
    async def _run_mayor_batch_turn(
        game_id: UUID,
        engine: EngineWrapper,
        actor_id: str,
        process_action_callback,
        *,
        initial_mask: list[int],
        supports_suppress_broadcast: bool,
    ) -> None:
        placements_applied = 0
        current_mask = initial_mask

        logger.warning(
            "[BOT_TRACE] mayor_batch_start game=%s actor=%s current_player_idx=%s remaining=%s",
            game_id,
            actor_id,
            getattr(engine.env.game, "current_player_idx", None),
            BotService._current_player_remaining_colonists(engine),
        )

        while True:
            phase = BotService._current_phase(engine)
            current_player_idx = getattr(engine.env.game, "current_player_idx", None)
            remaining = BotService._current_player_remaining_colonists(engine)

            if phase != Phase.MAYOR or remaining <= 0:
                logger.warning(
                    "[BOT_TRACE] mayor_batch_stop game=%s actor=%s phase=%s remaining=%s placements=%d",
                    game_id,
                    actor_id,
                    phase,
                    remaining,
                    placements_applied,
                )
                break

            if not BotService._has_legal_mayor_slot(current_mask):
                logger.warning(
                    "[BOT_TRACE] mayor_batch_no_legal_slot game=%s actor=%s current_player_idx=%s remaining=%s placements=%d",
                    game_id,
                    actor_id,
                    current_player_idx,
                    remaining,
                    placements_applied,
                )
                break

            suppress_broadcast = remaining > 1
            action_int, _snapshot = BotService._select_action_for_current_state(
                game_id=game_id,
                engine=engine,
                actor_id=actor_id,
                action_mask=current_mask,
            )
            applied_action = await BotService._apply_action_with_retry(
                game_id=game_id,
                engine=engine,
                actor_id=actor_id,
                action_int=action_int,
                process_action_callback=process_action_callback,
                suppress_broadcast=suppress_broadcast,
                supports_suppress_broadcast=supports_suppress_broadcast,
            )
            if applied_action is None:
                break

            placements_applied += 1
            next_phase = BotService._current_phase(engine)
            next_player_idx = getattr(engine.env.game, "current_player_idx", None)
            next_remaining = BotService._current_player_remaining_colonists(engine)

            if not suppress_broadcast:
                logger.warning(
                    "[BOT_TRACE] mayor_batch_complete game=%s actor=%s placements=%d next_player_idx=%s next_phase=%s",
                    game_id,
                    actor_id,
                    placements_applied,
                    next_player_idx,
                    next_phase,
                )
                break

            if next_phase != Phase.MAYOR or next_player_idx != current_player_idx:
                logger.error(
                    "[BOT_TRACE] mayor_batch_exit_after_suppressed_action game=%s actor=%s prev_player_idx=%s next_player_idx=%s prev_remaining=%s next_remaining=%s next_phase=%s placements=%d",
                    game_id,
                    actor_id,
                    current_player_idx,
                    next_player_idx,
                    remaining,
                    next_remaining,
                    next_phase,
                    placements_applied,
                )
                break

            if next_remaining >= remaining:
                logger.warning(
                    "[BOT_TRACE] mayor_batch_no_progress game=%s actor=%s player_idx=%s remaining_before=%s remaining_after=%s placements=%d",
                    game_id,
                    actor_id,
                    current_player_idx,
                    remaining,
                    next_remaining,
                    placements_applied,
                )
                break

            current_mask = BotService.guard_action_mask(engine)

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
            supports_suppress_broadcast = BotService._callback_supports_suppress_broadcast(
                process_action_callback
            )
            if (
                supports_suppress_broadcast
                and BotService._current_phase(engine) == Phase.MAYOR
                and BotService._current_player_remaining_colonists(engine) > 0
                and BotService._has_legal_mayor_slot(mask)
            ):
                await BotService._run_mayor_batch_turn(
                    game_id=game_id,
                    engine=engine,
                    actor_id=actor_id,
                    process_action_callback=process_action_callback,
                    initial_mask=mask,
                    supports_suppress_broadcast=supports_suppress_broadcast,
                )
                return

            action_int, _snapshot = BotService._select_action_for_current_state(
                game_id=game_id,
                engine=engine,
                actor_id=actor_id,
                action_mask=mask,
            )
            await BotService._apply_action_with_retry(
                game_id=game_id,
                engine=engine,
                actor_id=actor_id,
                action_int=action_int,
                process_action_callback=process_action_callback,
                supports_suppress_broadcast=supports_suppress_broadcast,
            )
        except Exception as e:
            logger.critical("[BOT] UNHANDLED ERROR in run_bot_turn game=%s actor=%s: %s", 
                            game_id, actor_id, e, exc_info=True)
