"""
run_league.py — Unified Puerto Rico RL Evaluation Pipeline

Usage
-----
# Single PPO vs full ecosystem (Shipping + Fusion + Random×2)
python evaluate/run_league.py ecosystem \
    --agent_path models/ppo_checkpoints/model.pth \
    --games 1000

# Head-to-head: two PPO models with ecosystem bots as 3rd seat
python evaluate/run_league.py head2head \
    --agent_a models/ppo_checkpoints/model_a.pth \
    --agent_b models/ppo_checkpoints/model_b.pth \
    --games 1000

Optional flags
--------------
--report_tag STR   Custom suffix added to the report directory name
--dry_run          Run only 1 game per permutation (quick sanity check)
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import argparse
import itertools
import re
import time
import torch
import torch.multiprocessing as mp
import numpy as np
import pandas as pd

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import get_flattened_obs_dim
from agents.ppo_agent import PhasePPOAgent, Agent as PPOAgent
from agents.advanced_rule_based_agent import AdvancedRuleBasedAgent
from agents.factory_rule_based_agent import FactoryRuleBasedAgent
from agents.heuristic_bots import RandomBot

from utils.evaluation.evaluator import GameEvaluator
from utils.evaluation.metrics import (
    TrueSkillTracker,
    VPMarginTracker,
    VPDecompositionTracker,
    RoleEntropyTracker,
)
from utils.evaluation.plotter import (
    save_trueskill_plot,
    save_vp_margin_boxplot,
    save_vp_decomposition_plot,
    save_role_selection_plot,
    save_winrate_plot,
)


# ── Constants ─────────────────────────────────────────────────────────────────
NUM_PLAYERS = 3


# ── Agent loading ─────────────────────────────────────────────────────────────
def load_ppo(path: str, obs_dim: int, action_dim: int, label: str = "PPO") -> torch.nn.Module:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"[{label}] Checkpoint not found: {path}")

    state_dict = torch.load(path, map_location="cpu", weights_only=True)
    is_phase   = any(k.startswith("phase_heads.") or k.startswith("phase_embed.")
                     for k in state_dict)
    if is_phase:
        print(f"  [{label}] PhasePPOAgent — {os.path.basename(path)}")
        agent = PhasePPOAgent(obs_dim=obs_dim, action_dim=action_dim)
    else:
        print(f"  [{label}] PPOAgent — {os.path.basename(path)}")
        agent = PPOAgent(obs_dim=obs_dim, action_dim=action_dim)

    agent.load_state_dict(state_dict)
    agent.eval()
    return agent


def _sanitize(path: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "", os.path.basename(path).replace(".pth", ""))[:40]


# ── Ecosystem pool (always available) ─────────────────────────────────────────
def build_ecosystem_pool(action_dim: int) -> dict:
    """
    Canonical opponent pool.

    Removed bots (ecosystem league 1775450115 evidence):
      - AdvRule_Fusion:   TrueSkill 16.93 << Random ~21.85 → sub-random
      - AdvRule_Building: removed earlier (sub-random)
      - AdvRule_Blocking: removed earlier (sub-random)

    Retained:
      - AdvRule_Shipping: TrueSkill 24.22 > Random ~21.85 → reference benchmark
      - FactoryBot:       Human-designed Factory diversification strategy
      - Random_1, Random_2: baseline floor
    """
    return {
        "AdvRule_Shipping": AdvancedRuleBasedAgent(action_dim, fixed_strategy=0).eval(),
        "FactoryBot":       FactoryRuleBasedAgent(action_dim).eval(),
        "Random_1":         RandomBot(action_dim).eval(),
        "Random_2":         RandomBot(action_dim).eval(),
    }


# ── Accumulation helpers ──────────────────────────────────────────────────────
def _accumulate(raw_results: list, pool: list,
                ts: TrueSkillTracker,
                vp_margin: VPMarginTracker,
                vp_decomp: VPDecompositionTracker,
                role_entropy: RoleEntropyTracker,
                win_counts: dict,
                win_counts_focal: dict,
                games_played: dict,
                games_played_focal: dict,
                total_apa: dict,
                total_ppa: dict,
                focal_agents: set):
    """Merge one permutation's raw_results into all accumulators."""
    has_focal = any(n in focal_agents for n in win_counts_focal)

    for match in raw_results:
        ts.update(match["ranks"])
        vp_margin.update(match["scores"])
        vp_decomp.update(match["vp_decomp"])
        role_entropy.update(match["role_counts"])

        is_focal_game = any(n in focal_agents for n in match["ranks"])

        for name in match["ranks"]:
            if name not in pool:
                continue
            games_played[name] += 1
            if is_focal_game:
                games_played_focal[name] += 1
            if match["ranks"][name] == 1:
                win_counts[name] += 1
                if is_focal_game:
                    win_counts_focal[name] += 1

        for name, apa_val in match["apa"].items():
            if name in pool:
                total_apa[name] += apa_val
        for name, ppa_val in match["ppa"].items():
            if name in pool:
                total_ppa[name] += ppa_val


# ── Report generation ────────────────────────────────────────────────────────
def save_report(report_dir: str, pool: list,
                ts: TrueSkillTracker,
                vp_margin: VPMarginTracker,
                vp_decomp: VPDecompositionTracker,
                role_entropy: RoleEntropyTracker,
                win_counts: dict,
                win_counts_focal: dict,
                games_played: dict,
                games_played_focal: dict,
                total_apa: dict,
                total_ppa: dict,
                focal_agents: set,
                mode: str):

    os.makedirs(report_dir, exist_ok=True)
    ratings = ts.get_ratings_dict()

    # ── Plots ──────────────────────────────────────────────────────────────
    save_trueskill_plot(ratings, f"{report_dir}/trueskill_ecosystem.png")
    save_vp_margin_boxplot(vp_margin.vp_margins, f"{report_dir}/vp_margins.png")
    save_vp_decomposition_plot(vp_decomp.get_averages(), f"{report_dir}/vp_decomposition.png")
    save_role_selection_plot(role_entropy.get_distributions(), f"{report_dir}/role_selection.png")

    win_rates = {
        n: (win_counts[n] / games_played[n] * 100) if games_played[n] > 0 else 0.0
        for n in pool
    }
    save_winrate_plot(win_rates, f"{report_dir}/win_rates.png",
                      title=f"Win Rate — {mode.capitalize()} League")

    # ── CSV metrics summary ────────────────────────────────────────────────
    focal_label = "Win%(Focal games)" if focal_agents else "Win%(All)"
    rows = []
    for name in pool:
        g       = games_played[name]
        g_focal = games_played_focal[name]
        mu      = ratings[name]["mu"]
        margin  = vp_margin.get_average_margins()[name]
        apa     = total_apa[name] / max(1, g)
        ppa     = total_ppa[name] / max(1, g)
        win_all = (win_counts[name] / max(1, g)) * 100
        win_foc = (win_counts_focal[name] / max(1, g_focal)) * 100 if g_focal > 0 else 0.0
        rows.append({
            "Agent":           name,
            "Win%(All)":       f"{win_all:.1f}%",
            focal_label:       f"{win_foc:.1f}%",
            "TrueSkill_Mu":    f"{mu:.2f}",
            "Avg_VP_Margin":   f"{margin:.2f}",
            "Avg_APA":         f"{apa:.2f}",
            "Avg_PPA":         f"{ppa:.2f}",
        })

    df = pd.DataFrame(rows)
    csv_path = f"{report_dir}/metrics_summary.csv"
    df.to_csv(csv_path, index=False)

    print(f"\n{'='*60}")
    print(f"  Report saved → {report_dir}")
    print(f"{'='*60}")
    print(df.to_string(index=False))
    return df


# ── Mode: ecosystem ───────────────────────────────────────────────────────────
def run_ecosystem(args, obs_dim: int, action_dim: int, env: PuertoRicoEnv):
    print(f"\n[Ecosystem League]  Model: {args.agent_path}")
    print(f"Games per permutation: {args.games}\n")

    ppo_agent = load_ppo(args.agent_path, obs_dim, action_dim, "PPO_Agent")
    ppo_agent.share_memory()

    eco_pool  = build_ecosystem_pool(action_dim)
    for a in eco_pool.values():
        a.share_memory()

    agent_instances = {"PPO_Agent": ppo_agent, **eco_pool}
    pool = list(agent_instances.keys())

    # All C(5,3) × 3! permutations
    all_perms = [perm for combo in itertools.combinations(pool, NUM_PLAYERS)
                       for perm in itertools.permutations(combo)]
    print(f"Total permutations: {len(all_perms)}  ×  {args.games} games = "
          f"{len(all_perms) * args.games:,} games")

    ts           = TrueSkillTracker(pool)
    vp_margin    = VPMarginTracker(pool)
    vp_decomp_t  = VPDecompositionTracker(pool)
    role_entropy = RoleEntropyTracker(pool)
    win_counts   = {n: 0 for n in pool}
    win_focal    = {n: 0 for n in pool}
    gp           = {n: 0 for n in pool}
    gp_focal     = {n: 0 for n in pool}
    total_apa    = {n: 0.0 for n in pool}
    total_ppa    = {n: 0.0 for n in pool}
    focal        = {"PPO_Agent"}

    evaluator = GameEvaluator(env, obs_dim, action_dim)
    t0 = time.time()

    for idx, perm in enumerate(all_perms):
        print(f"\r  [{idx+1:3d}/{len(all_perms)}] {perm}", end="", flush=True)
        res = evaluator.run_permutation_parallel(perm, agent_instances, args.games)
        _accumulate(res["raw_results"], pool, ts, vp_margin, vp_decomp_t, role_entropy,
                    win_counts, win_focal, gp, gp_focal, total_apa, total_ppa, focal)

    print(f"\n  Finished in {time.time() - t0:.1f}s")

    tag   = f"_{args.report_tag}" if args.report_tag else ""
    rdir  = f"report/Ecosystem_League_{int(time.time())}{tag}"
    return save_report(rdir, pool, ts, vp_margin, vp_decomp_t, role_entropy,
                       win_counts, win_focal, gp, gp_focal, total_apa, total_ppa,
                       focal, mode="ecosystem")


# ── Mode: head2head ───────────────────────────────────────────────────────────
def run_head2head(args, obs_dim: int, action_dim: int, env: PuertoRicoEnv):
    print(f"\n[Head-to-Head League]")
    print(f"  Model A: {args.agent_a}")
    print(f"  Model B: {args.agent_b}")
    print(f"Games per permutation: {args.games}\n")

    model_a = load_ppo(args.agent_a, obs_dim, action_dim, "Model_A")
    model_b = load_ppo(args.agent_b, obs_dim, action_dim, "Model_B")
    model_a.share_memory()
    model_b.share_memory()

    eco_pool = build_ecosystem_pool(action_dim)
    for a in eco_pool.values():
        a.share_memory()

    third_seats = list(eco_pool.keys())
    agent_instances = {"Model_A": model_a, "Model_B": model_b, **eco_pool}
    pool = list(agent_instances.keys())

    # Permutations containing BOTH Model_A and Model_B
    all_perms = []
    for third in third_seats:
        for perm in itertools.permutations(["Model_A", "Model_B", third]):
            all_perms.append(perm)
    print(f"Total permutations: {len(all_perms)}  ×  {args.games} games = "
          f"{len(all_perms) * args.games:,} games")

    ts           = TrueSkillTracker(pool)
    vp_margin    = VPMarginTracker(pool)
    vp_decomp_t  = VPDecompositionTracker(pool)
    role_entropy = RoleEntropyTracker(pool)
    win_counts   = {n: 0 for n in pool}
    win_focal    = {n: 0 for n in pool}
    gp           = {n: 0 for n in pool}
    gp_focal     = {n: 0 for n in pool}
    total_apa    = {n: 0.0 for n in pool}
    total_ppa    = {n: 0.0 for n in pool}
    focal        = {"Model_A", "Model_B"}

    evaluator = GameEvaluator(env, obs_dim, action_dim)
    t0 = time.time()

    for idx, perm in enumerate(all_perms):
        print(f"\r  [{idx+1:3d}/{len(all_perms)}] {perm}", end="", flush=True)
        res = evaluator.run_permutation_parallel(perm, agent_instances, args.games)
        _accumulate(res["raw_results"], pool, ts, vp_margin, vp_decomp_t, role_entropy,
                    win_counts, win_focal, gp, gp_focal, total_apa, total_ppa, focal)

    print(f"\n  Finished in {time.time() - t0:.1f}s")

    tag  = f"_{args.report_tag}" if args.report_tag else ""
    name_a, name_b = _sanitize(args.agent_a), _sanitize(args.agent_b)
    rdir = f"report/H2H_{name_a}_vs_{name_b}_{int(time.time())}{tag}"
    return save_report(rdir, pool, ts, vp_margin, vp_decomp_t, role_entropy,
                       win_counts, win_focal, gp, gp_focal, total_apa, total_ppa,
                       focal, mode="head2head")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    try:
        mp.set_start_method("spawn", force=True)
    except RuntimeError:
        pass

    parser = argparse.ArgumentParser(
        description="Puerto Rico RL — Unified Evaluation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # ── ecosystem ──────────────────────────────────────────────────────────
    p_eco = subparsers.add_parser("ecosystem",
                                   help="Single PPO vs full ecosystem pool")
    p_eco.add_argument("--agent_path", type=str, required=True,
                        help="Path to the PPO model checkpoint (.pth)")
    p_eco.add_argument("--games", type=int, default=1000,
                        help="Games per permutation (default: 1000)")
    p_eco.add_argument("--report_tag", type=str, default="",
                        help="Optional suffix for the report directory name")
    p_eco.add_argument("--dry_run", action="store_true",
                        help="Run 1 game per permutation for quick sanity check")

    # ── head2head ──────────────────────────────────────────────────────────
    p_h2h = subparsers.add_parser("head2head",
                                   help="Compare two PPO models head-to-head")
    p_h2h.add_argument("--agent_a", type=str, required=True,
                        help="Path to Model A checkpoint (.pth)")
    p_h2h.add_argument("--agent_b", type=str, required=True,
                        help="Path to Model B checkpoint (.pth)")
    p_h2h.add_argument("--games", type=int, default=1000,
                        help="Games per permutation (default: 1000)")
    p_h2h.add_argument("--report_tag", type=str, default="",
                        help="Optional suffix for the report directory name")
    p_h2h.add_argument("--dry_run", action="store_true",
                        help="Run 1 game per permutation for quick sanity check")

    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN] Overriding --games → 1")
        args.games = 1

    # Shared environment setup
    env        = PuertoRicoEnv(num_players=NUM_PLAYERS, max_game_steps=1500)
    obs_dim    = get_flattened_obs_dim(env.observation_space(env.possible_agents[0])["observation"])
    action_dim = env.action_space(env.possible_agents[0]).n

    if args.mode == "ecosystem":
        run_ecosystem(args, obs_dim, action_dim, env)
    elif args.mode == "head2head":
        run_head2head(args, obs_dim, action_dim, env)


if __name__ == "__main__":
    main()
