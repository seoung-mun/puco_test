import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
import time
import os
import torch
import torch.multiprocessing as mp
import pandas as pd
from collections import defaultdict

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import get_flattened_obs_dim
from agents.ppo_agent import PhasePPOAgent, Agent as PPOAgent
from agents.heuristic_bots import RandomBot

from utils.evaluation.evaluator import GameEvaluator
from utils.evaluation.matchups import get_mixed_matchups, get_asymmetric_matchups
from utils.evaluation.metrics import TrueSkillTracker, VPMarginTracker
from utils.evaluation.plotter import save_trueskill_plot, save_vp_margin_boxplot, save_selfplay_avg_vp_plot, save_role_selection_plot

def load_agent(path, obs_dim, action_dim, agent_label="Agent"):
    if not path or not os.path.exists(path):
        print(f"Warning: Checkpoint '{path}' not found. Using randomly initialized PPOAgent for {agent_label}.")
        agent = PPOAgent(obs_dim=obs_dim, action_dim=action_dim)
        agent.eval()
        return agent

    print(f"Loading weights from {path}...")
    state_dict = torch.load(path, map_location='cpu')
    
    # Auto-detect architecture based on state_dict keys
    is_phase_ppo = any(k.startswith('phase_heads.') or k.startswith('phase_embed.') for k in state_dict.keys())
    
    if is_phase_ppo:
        print(f"[{agent_label}] Detected PhasePPOAgent architecture.")
        agent = PhasePPOAgent(obs_dim=obs_dim, action_dim=action_dim)
    else:
        print(f"[{agent_label}] Detected PPOAgent architecture.")
        agent = PPOAgent(obs_dim=obs_dim, action_dim=action_dim)
        
    agent.load_state_dict(state_dict)
    agent.eval()
    return agent

def main():
    try:
        mp.set_start_method('spawn', force=True)
    except RuntimeError:
        pass
        
    parser = argparse.ArgumentParser(description="Evaluate RL Agents Strategy & Performance")
    parser.add_argument("--agent_a_path", type=str, default="", help="Path to first agent's model")
    parser.add_argument("--agent_b_path", type=str, default="", help="Path to second agent's model")
    # For backward compatibility
    parser.add_argument("--A_ppo_path", type=str, default="", help="Legacy arg for first agent's model")
    parser.add_argument("--B_ppo_path", type=str, default="", help="Legacy arg for second agent's model")
    parser.add_argument("--games", type=int, default=10000, help="Number of games per permutation")
    args = parser.parse_args()

    path_a = args.agent_a_path if args.agent_a_path else args.A_ppo_path
    path_b = args.agent_b_path if args.agent_b_path else args.B_ppo_path

    print(f"--- Puerto Rico RL Massive Tournament Evaluator ---")
    print(f"Simulating {args.games} games per permutation.\n")

    env = PuertoRicoEnv(num_players=3, max_game_steps=1500)
    obs_space = env.observation_space(env.possible_agents[0])["observation"]
    obs_dim = get_flattened_obs_dim(obs_space)
    action_dim = env.action_space(env.possible_agents[0]).n

    # Auto-detect and instantiate underlying models based on state dict
    agent_a = load_agent(path_a, obs_dim, action_dim, agent_label="Agent_A")
    agent_b = load_agent(path_b, obs_dim, action_dim, agent_label="Agent_B")
    random_bot = RandomBot(action_dim).eval()
    
    # Share memory to allow fast multiprocess reads across environments
    agent_a.share_memory()
    agent_b.share_memory()
    random_bot.share_memory()

    # Agent names used in permutations
    AGENT_A = "Agent_A"
    AGENT_B = "Agent_B"
    RANDOM = "Random"
    
    agent_instances = {
        AGENT_A: agent_a,
        AGENT_B: agent_b,
        RANDOM: random_bot,
        f"{AGENT_A}_1": agent_a,
        f"{AGENT_A}_2": agent_a,
        f"{AGENT_B}_1": agent_b,
        f"{AGENT_B}_2": agent_b,
    }

    # Generate permutations
    permutations = []
    permutations.extend(get_mixed_matchups(AGENT_A, AGENT_B, RANDOM)) # 6 perms
    permutations.extend(get_asymmetric_matchups(AGENT_A, AGENT_B))     # 3 perms
    permutations.extend(get_asymmetric_matchups(AGENT_B, AGENT_A))     # 3 perms
    permutations.append((AGENT_A, f"{AGENT_A}_1", f"{AGENT_A}_2"))     # A-A-A
    permutations.append((AGENT_B, f"{AGENT_B}_1", f"{AGENT_B}_2"))     # B-B-B

    # Setup Metrics
    all_agent_names = list(agent_instances.keys())
    ts_tracker = TrueSkillTracker(all_agent_names)
    vp_tracker = VPMarginTracker(all_agent_names)
    evaluator = GameEvaluator(env, obs_dim, action_dim)

    start_time = time.time()
    total_games_played = 0

    # New trackers for advanced metrics
    total_game_lengths = []
    role_counts_agg = {AGENT_A: [0]*8, AGENT_B: [0]*8, RANDOM: [0]*8}
    selfplay_vp_sums = {AGENT_A: 0.0, AGENT_B: 0.0}
    selfplay_matches = {AGENT_A: 0, AGENT_B: 0}

    # Execute Simulations
    for idx, perm in enumerate(permutations):
        print(f"\n[{idx+1}/{len(permutations)}] Running Permutation: {perm}")
        
        # Execute massive batched multithreaded matches
        # Results are aggregated sequentially for TrueSkill updating locally
        res = evaluator.run_permutation_parallel(perm, agent_instances, args.games)
        
        for raw_match in res["raw_results"]:
            ts_tracker.update(raw_match["ranks"])
            vp_tracker.update(raw_match["scores"])
            
            total_game_lengths.append(raw_match["game_length"])
            
            # Sub-agent parsing logic: f"{AGENT_A}_1" -> "Agent_A"
            agents_in_match = set([k.split("_")[0] + "_" + k.split("_")[1] if "Agent_" in k else k for k in perm])
            
            if len(agents_in_match) == 1:
                base_name = agents_in_match.pop()
                if base_name in selfplay_vp_sums:
                    avg_vp = sum(raw_match["scores"].values()) / len(raw_match["scores"])
                    selfplay_vp_sums[base_name] += avg_vp
                    selfplay_matches[base_name] += 1
            
            for agent_key, counts in raw_match["role_counts"].items():
                base_name = agent_key.split("_")[0] + "_" + agent_key.split("_")[1] if "Agent_" in agent_key else agent_key
                if base_name in role_counts_agg:
                    for i in range(8):
                        role_counts_agg[base_name][i] += counts[i]
            
        total_games_played += args.games
        
    elapsed = time.time() - start_time
    print(f"\n==========================================")
    print(f"TOURNAMENT FINISHED! (Took {elapsed:.1f}s)")
    print(f"Total Games Played: {total_games_played}")
    print(f"==========================================\n")

    # Generate Reports
    import re
    def sanitize(p):
        return re.sub(r'[^a-zA-Z0-9_\-]', '', os.path.basename(p).replace(".pth", ""))
    
    name_a = sanitize(path_a) if path_a else "Random_A"
    name_b = sanitize(path_b) if path_b else "Random_B"
    report_dir = f"report/{name_a}_vs_{name_b}_{int(time.time())}"
    os.makedirs(report_dir, exist_ok=True)
    
    # Merge TrueSkill ratings for duplicated agents to show aggregate rating
    ratings = ts_tracker.get_ratings_dict()
    # Let's save the RAW true skill
    save_trueskill_plot(ratings, f"{report_dir}/trueskill_all_agents.png")
    
    # VP Margins Boxplot
    vp_margins = vp_tracker.vp_margins
    save_vp_margin_boxplot(vp_margins, f"{report_dir}/vp_margins_boxplot.png")
    
    # Self-play average VP tracking
    selfplay_avg_vp = {}
    for base_name in [AGENT_A, AGENT_B]:
        if selfplay_matches[base_name] > 0:
            selfplay_avg_vp[base_name] = selfplay_vp_sums[base_name] / selfplay_matches[base_name]
    if selfplay_avg_vp:
        save_selfplay_avg_vp_plot(selfplay_avg_vp, f"{report_dir}/selfplay_avg_vp.png")
        
    # Role Selection Frequencies tracking
    role_names = ["Settler", "Mayor", "Builder", "Craftsman", "Trader", "Captain", "Prospector1", "Prospector2"]
    save_role_selection_plot(role_counts_agg, role_names, f"{report_dir}/role_selection_frequency.png")
    
    avg_game_len = sum(total_game_lengths) / max(1, len(total_game_lengths))
    print(f"Overall average game length: {avg_game_len:.1f} steps")
    
    # Save CSV
    df = pd.DataFrame(columns=["Agent Name", "TrueSkill Mu", "TrueSkill Sigma", "Avg VP Margin", "SelfPlay Avg VP"])
    for name in all_agent_names:
        r = ratings[name]
        avg_margin = vp_tracker.get_average_margins()[name]
        
        # Try to map to base name to attach tracking stats
        base_name = name.split("_")[0] + "_" + name.split("_")[1] if "Agent_" in name else name
        sp_vp = selfplay_avg_vp.get(base_name, 0.0) if name in [AGENT_A, AGENT_B] else 0.0
        
        df.loc[len(df)] = [name, r["mu"], r["sigma"], avg_margin, sp_vp]
        
    df.to_csv(f"{report_dir}/tournament_summary.csv", index=False)
    print(f"Metrics successfully saved to {report_dir}/ directory.")
    print(f" - {report_dir}/trueskill_all_agents.png")
    print(f" - {report_dir}/vp_margins_boxplot.png")
    print(f" - {report_dir}/selfplay_avg_vp.png")
    print(f" - {report_dir}/role_selection_frequency.png")
    print(f" - {report_dir}/tournament_summary.csv")

if __name__ == "__main__":
    main()
