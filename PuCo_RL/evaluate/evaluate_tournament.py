import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import torch
import numpy as np
import itertools
from collections import defaultdict
import time

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
from agents.ppo_agent import PhasePPOAgent
from agents.heuristic_bots import BuilderBot, ShipperBot, RandomBot

# ==========================================
# Tournament Configuration
# ==========================================
# Format: (AgentName, AgentType, WeightPath)
# AgentType options: "PhasePPO", "BUILDER", "SHIPPER", "RANDOM"
PARTICIPANTS = [
    ("Phase2_Agent", "PhasePPO", "models/PhasePPO_PR_Server_1774230650_step_14745600.pth"), # Example path
    ("Builder_Bot", "BUILDER", None),
    ("Shipper_Bot", "SHIPPER", None)
]

GAMES_PER_PERMUTATION = 50 # Total games = 6 permutations * 50 = 300 games

def get_agent_instance(ptype, path, obs_dim, action_dim):
    if ptype == "BUILDER": return BuilderBot(action_dim).eval()
    if ptype == "SHIPPER": return ShipperBot(action_dim).eval()
    if ptype == "RANDOM": return RandomBot(action_dim).eval()
    if ptype == "PhasePPO":
        agent = PhasePPOAgent(obs_dim=obs_dim, action_dim=action_dim)
        if path:
            print(f"Loading weights for PhasePPO from {path}...")
            try:
                agent.load_state_dict(torch.load(path, map_location='cpu'))
            except Exception as e:
                print(f"Warning: Failed to load {path} - {e}. Using uninitialized weights.")
        agent.eval()
        return agent
    raise ValueError(f"Unknown agent type: {ptype}")

def main():
    print(f"--- Puerto Rico RL Tournament Evaluator ---")
    env = PuertoRicoEnv(num_players=3, max_game_steps=1500)
    obs_space = env.observation_space(env.possible_agents[0])["observation"]
    obs_dim = get_flattened_obs_dim(obs_space)
    action_dim = env.action_space(env.possible_agents[0]).n
    
    # Pre-instantiate models
    agent_instances = {}
    for name, ptype, path in PARTICIPANTS:
        agent_instances[name] = get_agent_instance(ptype, path, obs_dim, action_dim)
        
    permutations = list(itertools.permutations([p[0] for p in PARTICIPANTS]))
    
    # Stats trackers
    win_counts = {p[0]: 0 for p in PARTICIPANTS}
    score_sums = {p[0]: 0.0 for p in PARTICIPANTS}
    total_games = 0
    
    start_time = time.time()
    
    print(f"\nStarting Tournament. 3 Participants. 6 Permutations. {GAMES_PER_PERMUTATION} games per perm.")
    print(f"Total Games to play: {len(permutations) * GAMES_PER_PERMUTATION}\n")
    
    for perm_idx, perm in enumerate(permutations):
        print(f"Running Permutation {perm_idx+1}/{len(permutations)}: Seat 1:[{perm[0]}] Seat 2:[{perm[1]}] Seat 3:[{perm[2]}]")
        
        for g in range(GAMES_PER_PERMUTATION):
            env.reset()
            agent_generator = iter(env.agent_iter())
            agent_name_mapped = next(agent_generator)
            
            while True:
                obs, reward, termination, truncation, info = env.last()
                if termination or truncation:
                    env.step(None)
                    try:
                        agent_name_mapped = next(agent_generator)
                    except StopIteration:
                        break
                    continue
                
                # Turn Env Player ID (player_0, player_1, player_2) into our Participant Name
                p_idx = int(agent_name_mapped.split("_")[1])
                current_participant_name = perm[p_idx]
                model = agent_instances[current_participant_name]
                
                # Get Action
                flat_obs = flatten_dict_observation(obs["observation"], obs_space)
                mask = obs["action_mask"]
                phase_id = int(obs["observation"]["global_state"]["current_phase"])
                
                obs_t = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
                mask_t = torch.as_tensor(mask, dtype=torch.float32).unsqueeze(0)
                phase_t = torch.tensor([phase_id], dtype=torch.long)
                
                with torch.no_grad():
                    action, _, _, _ = model.get_action_and_value(obs_t, mask_t, phase_ids=phase_t)
                
                env.step(action.item())
                try:
                    agent_name_mapped = next(agent_generator)
                except StopIteration:
                    break
                    
            # Game Finished
            scores = env.game.get_scores()
            max_score = max(s[0] for s in scores)
            
            # Record stats
            for p_idx in range(3):
                participant_name = perm[p_idx]
                score = scores[p_idx][0]
                score_sums[participant_name] += score
                if score >= max_score: # Tie counts as win for both
                    win_counts[participant_name] += 1
            
            total_games += 1
            if total_games % 30 == 0:
                print(f"  ... played {total_games} games ...")

    elapsed = time.time() - start_time
    print(f"\n==========================================")
    print(f"TOURNAMENT RESULTS (Took {elapsed:.1f}s, {elapsed/total_games:.2f}s/game)")
    print(f"==========================================")
    print(f"{'Agent Name':<20} | {'Win Rate':<10} | {'Average VP':<10}")
    print(f"-" * 45)
    
    # Sort by Win Rate
    sorted_agents = sorted(win_counts.keys(), key=lambda k: win_counts[k], reverse=True)
    
    for name in sorted_agents:
        wr = win_counts[name] / total_games
        avg_vp = score_sums[name] / total_games
        print(f"{name:<20} | {wr*100:>8.1f}% | {avg_vp:>8.2f}")
    
    print(f"==========================================\n")

if __name__ == "__main__":
    main()
