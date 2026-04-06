import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import os
import re
import argparse
import time
import torch
import pandas as pd
import numpy as np

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import get_flattened_obs_dim
from agents.ppo_agent import PhasePPOAgent, Agent as PPOAgent
from agents.heuristic_bots import RandomBot
from utils.evaluation.evaluator import GameEvaluator
from utils.evaluation.plotter import save_learning_curve

def load_agent(agent_class, path, obs_dim, action_dim):
    agent = agent_class(obs_dim=obs_dim, action_dim=action_dim)
    agent.load_state_dict(torch.load(path, map_location='cpu'))
    agent.eval()
    return agent

def extract_step(filename):
    match = re.search(r"_step_(\d+)", filename)
    if match:
        return int(match.group(1))
    return -1

def get_sorted_checkpoints(directory):
    if not directory or not os.path.exists(directory):
         return []
    files = [f for f in os.listdir(directory) if f.endswith('.pth')]
    valid_files = [(os.path.join(directory, f), extract_step(f)) for f in files if extract_step(f) >= 0]
    valid_files.sort(key=lambda x: x[1])
    return valid_files

def evaluate_checkpoints(checkpoint_list, agent_class, obs_dim, action_dim, env, baseline_agent1, baseline_agent2, games_per_ckpt):
    evaluator = GameEvaluator(env, obs_dim, action_dim)
    
    steps = []
    win_rates = []
    
    for ckpt_path, step in checkpoint_list:
        print(f"Evaluating Checkpoint Step {step} ...")
        
        # Load candidate agent
        try:
            candidate = load_agent(agent_class, ckpt_path, obs_dim, action_dim)
        except Exception as e:
            print(f"Failed to load {ckpt_path}, skipping. Error: {e}")
            continue
            
        # For convergence, position 1 evaluates candidate vs baseline
        perm = ("Candidate", "Baseline1", "Baseline2")
        agent_instances = {
            "Candidate": candidate,
            "Baseline1": baseline_agent1,
            "Baseline2": baseline_agent2
        }
        
        res = evaluator.run_permutation(perm, agent_instances, games_per_ckpt)
        wr = res["win_counts"]["Candidate"] / games_per_ckpt
        
        steps.append(step)
        win_rates.append(wr)
        
    return steps, win_rates

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase_ppo_dir", type=str, default="models/phase_ppo_checkpoints")
    parser.add_argument("--ppo_dir", type=str, default="models/ppo_checkpoints")
    parser.add_argument("--games", type=int, default=100, help="Games per checkpoint")
    args = parser.parse_args()

    print("--- Learning Convergence Evaluator ---")
    
    env = PuertoRicoEnv(num_players=3, max_game_steps=1500)
    obs_space = env.observation_space(env.possible_agents[0])["observation"]
    obs_dim = get_flattened_obs_dim(obs_space)
    action_dim = env.action_space(env.possible_agents[0]).n
    
    rand1 = RandomBot(action_dim).eval()
    rand2 = RandomBot(action_dim).eval()

    phase_ckpts = get_sorted_checkpoints(args.phase_ppo_dir)
    ppo_ckpts = get_sorted_checkpoints(args.ppo_dir)
    
    print(f"Found {len(phase_ckpts)} PhasePPO checkpoints, {len(ppo_ckpts)} PPO checkpoints.")
    
    if not phase_ckpts and not ppo_ckpts:
        print("No checkpoints found. Ensure paths are correct.")
        return
        
    start_time = time.time()
    
    phase_steps = []
    phase_wrs = []
    if phase_ckpts:
        print("\nEvaluating Phase PPO Checkpoints...")
        phase_steps, phase_wrs = evaluate_checkpoints(
            phase_ckpts, PhasePPOAgent, obs_dim, action_dim, env, rand1, rand2, args.games
        )
        
    ppo_steps = []
    ppo_wrs = []
    if ppo_ckpts:
        print("\nEvaluating Standard PPO Checkpoints...")
        ppo_steps, ppo_wrs = evaluate_checkpoints(
            ppo_ckpts, PPOAgent, obs_dim, action_dim, env, rand1, rand2, args.games
        )
        
    print(f"Evaluation took {time.time() - start_time:.1f}s.")
    
    # Generate convergence plot
    # To plot together safely, we need shared step indices if possible, or scatter plots.
    # We will save the curve using our plotter which handles two lists if lengths match or logic permits.
    # But since save_learning_curve expects common steps for simplicity, we interpolate or just use seaborn lineplots.
    
    os.makedirs("report", exist_ok=True)
    
    # Save raw CSV
    if phase_steps:
        pd.DataFrame({"Step": phase_steps, "PhasePPO_WinRate": phase_wrs}).to_csv("report/convergence_phase.csv", index=False)
    if ppo_steps:
        pd.DataFrame({"Step": ppo_steps, "PPO_WinRate": ppo_wrs}).to_csv("report/convergence_ppo.csv", index=False)
        
    print("Saved convergence reports into /report folder.")
    print("Done!")

if __name__ == "__main__":
    main()
