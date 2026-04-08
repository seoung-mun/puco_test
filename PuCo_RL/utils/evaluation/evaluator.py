import os
import torch
import numpy as np
import torch.multiprocessing as mp
from configs.constants import BUILDING_DATA, BuildingType
from utils.env_wrappers import flatten_dict_observation
from agents.factory_rule_based_agent import FactoryRuleBasedAgent


def _worker_run_games(args):
    permutation, agent_instances, num_games, obs_dim, action_dim = args
    from env.pr_env import PuertoRicoEnv
    from agents.action_value_agent import ActionValueAgent
    
    env = PuertoRicoEnv(num_players=len(permutation), max_game_steps=1500)
    
    # Connect ActionValueAgent instances to the new env
    for name, agent in agent_instances.items():
        if isinstance(agent, ActionValueAgent):
            agent.set_env(env)
    
    evaluator = GameEvaluator(env, obs_dim, action_dim)
    return evaluator.run_permutation(permutation, agent_instances, num_games)


class GameEvaluator:
    def __init__(self, env, obs_dim: int, action_dim: int):
        self.env = env
        self.obs_dim = obs_dim
        self.action_dim = action_dim

    # ------------------------------------------------------------------
    # Phase-value helper (for APA / PPA computation)
    # ------------------------------------------------------------------
    def _compute_phase_values(self) -> list[float]:
        """
        Approximate current game value per player using full heuristic.
        Captures confirmed VP, goods, doubloons, and infrastructure potential.
        """
        if not hasattr(self, '_val_agent'):
            from agents.action_value_agent import ActionValueAgent
            self._val_agent = ActionValueAgent(self.action_dim)
            self._val_agent.set_env(self.env)
            
        values = []
        for p_idx in range(len(self.env.game.players)):
            val = self._val_agent._compute_heuristic(self.env.game, p_idx)
            values.append(float(val))
        return values

    # ------------------------------------------------------------------
    # Parallel execution (spawns N workers)
    # ------------------------------------------------------------------
    def run_permutation_parallel(self, permutation, agent_instances, num_games: int,
                                  num_workers: int | None = None) -> dict:
        if num_workers is None:
            num_workers = max(1, (os.cpu_count() or 4) - 2)
        num_workers = min(num_workers, num_games)

        base = num_games // num_workers
        remainder = num_games % num_workers
        worker_args = [
            (permutation, agent_instances, base + (1 if i < remainder else 0),
             self.obs_dim, self.action_dim)
            for i in range(num_workers)
        ]

        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=num_workers) as pool:
            results = pool.map(_worker_run_games, worker_args)

        aggregated = {
            "win_counts":  {n: 0 for n in permutation},
            "score_sums":  {n: 0 for n in permutation},
            "raw_results": [],
            "total_games": 0,
        }
        for res in results:
            for n in permutation:
                aggregated["win_counts"][n] += res["win_counts"][n]
                aggregated["score_sums"][n] += res["score_sums"][n]
            aggregated["raw_results"].extend(res["raw_results"])
            aggregated["total_games"] += res["total_games"]
        return aggregated

    # ------------------------------------------------------------------
    # Single-process permutation runner
    # ------------------------------------------------------------------
    def run_permutation(self, permutation: tuple, agent_instances: dict,
                        num_games: int) -> dict:
        """
        permutation : ordered tuple of agent names filling player seats.
        agent_instances : name → model/bot object.
        Returns aggregated stats + raw per-game records.
        """
        win_counts  = {n: 0 for n in permutation}
        score_sums  = {n: 0 for n in permutation}
        raw_results: list[dict] = []

        for _ in range(num_games):
            self.env.reset()

            # Reset per-game strategy for rule-based bots
            for agent_obj in agent_instances.values():
                if callable(getattr(agent_obj, "reset_strategy", None)):
                    agent_obj.reset_strategy()

            game_length   = 0
            role_counts   = {n: [0] * 8 for n in permutation}
            apa_accum     = {n: 0.0 for n in permutation}
            ppa_accum     = {n: 0.0 for n in permutation}
            role_owner_idx: int | None = None
            phase_start_vals: list[float] | None = None

            # PettingZoo AEC loop
            for agent_id in self.env.agent_iter():
                obs, reward, termination, truncation, info = self.env.last()

                if termination or truncation:
                    self.env.step(None)
                    continue

                player_idx    = int(agent_id.split("_")[1])
                curr_name     = permutation[player_idx]
                agent_model   = agent_instances[curr_name]
                action        = self._get_agent_action(agent_model, obs)

                # --- Role selection bookkeeping ---
                if 0 <= action <= 7 and obs["action_mask"][action] == 1:
                    role_counts[curr_name][action] += 1

                    # APA/PPA: close previous phase, open new one
                    if phase_start_vals is not None and role_owner_idx is not None:
                        end_vals = self._compute_phase_values()
                        deltas   = [end_vals[j] - phase_start_vals[j]
                                    for j in range(len(permutation))]
                        owner_d  = deltas[role_owner_idx]
                        others_d = [deltas[j] for j in range(len(permutation))
                                    if j != role_owner_idx]
                        avg_oth  = sum(others_d) / max(1, len(others_d))
                        apa_accum[permutation[role_owner_idx]] += owner_d - avg_oth
                        for j in range(len(permutation)):
                            if j != role_owner_idx:
                                ppa_accum[permutation[j]] += deltas[j] - owner_d

                    role_owner_idx   = player_idx
                    phase_start_vals = self._compute_phase_values()

                self.env.step(action)
                game_length += 1

            # Close final phase
            if phase_start_vals is not None and role_owner_idx is not None:
                end_vals = self._compute_phase_values()
                deltas   = [end_vals[j] - phase_start_vals[j]
                            for j in range(len(permutation))]
                owner_d  = deltas[role_owner_idx]
                others_d = [deltas[j] for j in range(len(permutation))
                            if j != role_owner_idx]
                avg_oth  = sum(others_d) / max(1, len(others_d))
                apa_accum[permutation[role_owner_idx]] += owner_d - avg_oth
                for j in range(len(permutation)):
                    if j != role_owner_idx:
                        ppa_accum[permutation[j]] += deltas[j] - owner_d

            # --- Final scores & VP decomposition ---
            scores_raw = self.env.game.get_scores()   # [(total_vp, tiebreaker), ...]
            scores:     dict[str, float] = {}
            ranks:      dict[str, int]   = {}
            vp_decomp:  dict[str, dict]  = {}

            for p_idx in range(len(permutation)):
                name      = permutation[p_idx]
                total_vp  = scores_raw[p_idx][0]
                ship_vp   = self.env.game.players[p_idx].vp_chips
                scores[name]    = total_vp
                vp_decomp[name] = {
                    "shipping": ship_vp,
                    "building": max(0, total_vp - ship_vp),
                }

            max_score = max(scores.values())
            sorted_names = sorted(scores, key=lambda k: scores[k], reverse=True)
            for rank, name in enumerate(sorted_names, start=1):
                ranks[name] = rank

            for name in scores:
                if scores[name] == max_score:
                    win_counts[name] += 1
                    ranks[name] = 1
                score_sums[name] += scores[name]

            raw_results.append({
                "scores":      scores,
                "ranks":       ranks,
                "game_length": game_length,
                "role_counts": role_counts,
                "apa":         apa_accum,
                "ppa":         ppa_accum,
                "vp_decomp":   vp_decomp,
            })

        return {
            "win_counts":  win_counts,
            "score_sums":  score_sums,
            "raw_results": raw_results,
            "total_games": num_games,
        }

    # ------------------------------------------------------------------
    # Type-safe action dispatch
    # ------------------------------------------------------------------
    def _get_agent_action(self, agent_model, obs: dict) -> int:
        """
        Unified action getter.
        Dispatch is type-based, NOT name-based, to avoid fragile string matching.
        """
        # Lazy import to avoid circular dependency at module level
        from agents.ppo_agent import PhasePPOAgent
        from agents.shipping_rush_agent import ShippingRushAgent
        from agents.action_value_agent import ActionValueAgent

        flat_obs = flatten_dict_observation(
            obs["observation"],
            self.env.observation_space("player_0")["observation"]
        )
        mask     = obs["action_mask"]
        phase_id = int(obs["observation"]["global_state"]["current_phase"])

        obs_t  = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
        mask_t = torch.as_tensor(mask, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            if isinstance(agent_model, (ShippingRushAgent, FactoryRuleBasedAgent)):
                player_idx = int(obs["observation"]["global_state"]["current_player"])
                act, _, _, _ = agent_model.get_action_and_value(
                    obs_t, mask_t,
                    obs_dict=obs["observation"], player_idx=player_idx
                )

            elif isinstance(agent_model, PhasePPOAgent):
                phase_t = torch.tensor([phase_id], dtype=torch.long)
                act, _, _, _ = agent_model.get_action_and_value(obs_t, mask_t, phase_ids=phase_t)

            elif isinstance(agent_model, ActionValueAgent):
                # Ensure env is connected for ActionValueAgent
                if agent_model._env is None:
                    agent_model.set_env(self.env)
                act, _, _, _ = agent_model.get_action_and_value(obs_t, mask_t)

            else:
                # Standard PPOAgent or BaseHeuristicBot (RandomBot, etc.)
                act, _, _, _ = agent_model.get_action_and_value(obs_t, mask_t)

        return int(act.item())
