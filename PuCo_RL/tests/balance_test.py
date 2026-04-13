import os
import sys
import argparse
import random

import numpy as np
import torch
import torch.multiprocessing as mp

REPO_ROOT = "/home/daehan/PuertoRico_RL"
sys.path.insert(0, REPO_ROOT)

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import get_flattened_obs_dim
from utils.evaluation.evaluator import GameEvaluator
from agents.ppo_agent import PhasePPOAgent, Agent as PPOAgent


def load_state_dict(path: str):
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        return torch.load(path, map_location="cpu")


def build_agents(state_dict, obs_dim: int, action_dim: int):
    is_phase = any(
        k.startswith("phase_heads.") or k.startswith("phase_embed.")
        for k in state_dict
    )
    AgentCls = PhasePPOAgent if is_phase else PPOAgent

    agents = []
    for _ in range(3):
        a = AgentCls(obs_dim=obs_dim, action_dim=action_dim)
        a.load_state_dict(state_dict)
        a.eval()
        agents.append(a)

    return agents, AgentCls.__name__


def main():
    default_model = os.path.join(
        REPO_ROOT,
        "models/ppo_checkpoints/순수자기대결/"
        "PPO_PR_Server_순수자기대결_20260406_135525_step_99942400.pth",
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", type=str, default=default_model)
    parser.add_argument("--games", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)

    if not os.path.exists(args.model_path):
        raise FileNotFoundError(f"Model not found: {args.model_path}")

    env = PuertoRicoEnv(num_players=3, max_game_steps=1500)
    obs_dim = get_flattened_obs_dim(
        env.observation_space(env.possible_agents[0])["observation"]
    )
    action_dim = env.action_space(env.possible_agents[0]).n

    state_dict = load_state_dict(args.model_path)
    agents, agent_name = build_agents(state_dict, obs_dim, action_dim)

    if args.workers > 1:
        try:
            mp.set_start_method("spawn", force=True)
        except RuntimeError:
            pass
        for a in agents:
            a.share_memory()

    # Seats map to player_0, player_1, player_2 in that order.
    agent_instances = {
        "Seat1": agents[0],
        "Seat2": agents[1],
        "Seat3": agents[2],
    }
    permutation = ("Seat1", "Seat2", "Seat3")

    evaluator = GameEvaluator(env, obs_dim, action_dim)
    if args.workers > 1:
        res = evaluator.run_permutation_parallel(
            permutation, agent_instances, args.games, num_workers=args.workers
        )
    else:
        res = evaluator.run_permutation(permutation, agent_instances, args.games)

    total = res["total_games"]
    print(f"Model: {agent_name}")
    print(f"Games: {total}")
    for seat in permutation:
        wins = res["win_counts"][seat]
        rate = wins / total * 100
        print(f"{seat} win rate: {wins}/{total} ({rate:.2f}%)")
    print("Tie handling: tied top scores are all counted as wins.")


if __name__ == "__main__":
    main()