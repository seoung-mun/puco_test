import os
import torch
import numpy as np
from collections import defaultdict
import torch.multiprocessing as mp
from utils.env_wrappers import flatten_dict_observation

def _worker_run_games(args):
    permutation, agent_instances, num_games, obs_dim, action_dim = args
    from env.pr_env import PuertoRicoEnv
    env = PuertoRicoEnv(num_players=len(permutation), max_game_steps=1500)
    evaluator = GameEvaluator(env, obs_dim, action_dim)
    return evaluator.run_permutation(permutation, agent_instances, num_games)

class GameEvaluator:
    def __init__(self, env, obs_dim, action_dim):
        self.env = env
        self.obs_dim = obs_dim
        self.action_dim = action_dim

    def run_permutation_parallel(self, permutation, agent_instances, num_games, num_workers=None):
        if num_workers is None:
            num_workers = max(1, os.cpu_count() - 2)
        num_workers = min(num_workers, num_games)

        base_games = num_games // num_workers
        remainder = num_games % num_workers

        worker_args = []
        for i in range(num_workers):
            games_for_this_worker = base_games + (1 if i < remainder else 0)
            worker_args.append((permutation, agent_instances, games_for_this_worker, self.obs_dim, self.action_dim))

        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=num_workers) as pool:
            results = pool.map(_worker_run_games, worker_args)

        aggregated_res = {
            "win_counts": {name: 0 for name in permutation},
            "score_sums": {name: 0 for name in permutation},
            "raw_results": [],
            "total_games": 0
        }

        for res in results:
            for name in permutation:
                aggregated_res["win_counts"][name] += res["win_counts"][name]
                aggregated_res["score_sums"][name] += res["score_sums"][name]
            aggregated_res["raw_results"].extend(res["raw_results"])
            aggregated_res["total_games"] += res["total_games"]

        return aggregated_res
        
    def run_permutation(self, permutation, agent_instances, num_games):
        """
        permutation: tuple/list of agent names representing seat order. ex ('PhasePPO', 'PPO', 'Random')
        agent_instances: dict mapping agent name -> initialized agent model or bot
        Returns stats about the matches played.
        """
        win_counts = {name: 0 for name in permutation}
        score_sums = {name: 0 for name in permutation}
        raw_results = [] # Detailed results for metrics tracker

        for _ in range(num_games):
            self.env.reset()
            agent_generator = iter(self.env.agent_iter())
            
            game_length = 0
            role_counts = {name: [0]*8 for name in permutation}
            
            # Use appropriate logic to step through PettingZoo env
            for i in range(1500): # max steps failsafe
                try:
                    agent_id = next(agent_generator)
                except StopIteration:
                    break
                    
                obs, reward, termination, truncation, info = self.env.last()
                
                if termination or truncation:
                    self.env.step(None)
                    continue
                
                player_idx = int(agent_id.split("_")[1])
                curr_agent_name = permutation[player_idx]
                agent_model = agent_instances[curr_agent_name]
                
                # Retrieve Action
                action = self._get_agent_action(agent_model, curr_agent_name, obs)
                
                if 0 <= action <= 7 and obs["action_mask"][action] == 1:
                    role_counts[curr_agent_name][action] += 1
                
                self.env.step(action)
                game_length += 1
                
            # Collect end-game scores
            scores_raw = self.env.game.get_scores()
            # We map scores back to agent names
            # scores_raw is a list of tuples: [(vp_total, player_obj), ...] mapping directly to player_0... player_2
            scores = {}
            ranks = {}
            for p_idx in range(len(permutation)):
                name = permutation[p_idx]
                scores[name] = scores_raw[p_idx][0]
                
            max_score = max(scores.values())
            
            # Build rank dict for this single match (1st, 2nd, 3rd)
            sorted_by_score = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
            current_rank = 1
            for name in sorted_by_score:
                ranks[name] = current_rank
                current_rank += 1
                
            # Tie breakers logic
            for name in scores:
                if scores[name] == max_score:
                    win_counts[name] += 1
                    ranks[name] = 1 # Update to rank 1 if tied max score
                score_sums[name] += scores[name]
                
            raw_results.append({
                "scores": scores,
                "ranks": ranks,
                "game_length": game_length,
                "role_counts": role_counts
            })
            
        return {
            "win_counts": win_counts,
            "score_sums": score_sums,
            "raw_results": raw_results,
            "total_games": num_games
        }

    def _get_agent_action(self, agent_model, agent_name, obs):
        if not hasattr(agent_model, "get_action_and_value"):
            # Probably heuristic bot
            if type(agent_model).__name__ == "RandomBot":
                 # Fallback to random choice from mask
                mask = obs["action_mask"]
                valid_actions = np.where(mask == 1)[0]
                return np.random.choice(valid_actions)
            elif callable(getattr(agent_model, "act", None)):
                # If there's an act method using raw obs
                return agent_model.act(obs)
            return self.env.action_space("player_0").sample(obs["action_mask"])

        # Tensor preparation for Neural Nets
        flat_obs = flatten_dict_observation(obs["observation"], self.env.observation_space("player_0")["observation"])
        mask = obs["action_mask"]
        phase_id = int(obs["observation"]["global_state"]["current_phase"])
        
        obs_t = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
        mask_t = torch.as_tensor(mask, dtype=torch.float32).unsqueeze(0)
        
        with torch.no_grad():
            if "Phase" in agent_name or type(agent_model).__name__ == "PhasePPOAgent" or getattr(agent_model, "num_phases", 0) > 1:
                phase_t = torch.tensor([phase_id], dtype=torch.long)
                action, _, _, _ = agent_model.get_action_and_value(obs_t, mask_t, phase_ids=phase_t)
            else:
                # Standard PPO Agent (assuming it doesn't take phase_ids)
                action, _, _, _ = agent_model.get_action_and_value(obs_t, mask_t)
                
        return action.item()
