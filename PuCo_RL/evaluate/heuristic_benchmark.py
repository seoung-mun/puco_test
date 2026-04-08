"""
heuristic_benchmark.py — Heuristic Bot Qualification Suite

Purpose
-------
Evaluates whether heuristic bots are qualified to join the PPO evaluation ecosystem.
A bot must demonstrate statistically significant superiority over Random to qualify.

Qualification Criteria
----------------------
1. Win Rate vs Random: > 40% (baseline: 33.3% for 3-player)
2. TrueSkill μ: > 27 (baseline: 25)
3. Statistical significance: 95% confidence interval must not overlap with Random

Scenarios
---------
  1. Shipping vs Random vs Random   — Shipping qualification test
  2. Factory vs Random vs Random    — Factory qualification test
  3. ActionValue vs Random vs Random     — ActionValue qualification test
  4. ActionValue vs Shipping vs Factory  — Relative strength comparison

Metrics
-------
- TrueSkill μ ± σ (with 95% CI)
- Win Rate (with binomial confidence interval)
- VP Margin
- APA (Action Player Advantage) — gain from own actions
- PPA (Passive Player Advantage) — gain from others' actions
- Role selection entropy

Usage
-----
    python evaluate/heuristic_benchmark.py --games 500
    python evaluate/heuristic_benchmark.py --games 200 --scenarios 1,2,3  # Qualification only
    python evaluate/heuristic_benchmark.py --dry_run  # Quick sanity check
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import argparse
import itertools
import json
import time
from typing import NamedTuple

import torch
import numpy as np
from scipy import stats

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import get_flattened_obs_dim
from utils.evaluation.evaluator import GameEvaluator
from utils.evaluation.metrics import (
    TrueSkillTracker, VPMarginTracker, VPDecompositionTracker, RoleEntropyTracker
)
from agents.shipping_rush_agent import ShippingRushAgent
from agents.factory_rule_based_agent import FactoryRuleBasedAgent
from agents.heuristic_bots import RandomBot
from agents.action_value_agent import ActionValueAgent

NUM_PLAYERS = 3

# ── Qualification thresholds ──────────────────────────────────────────────────
QUAL_WIN_RATE_THRESHOLD = 0.40      # Must win > 40% vs Random (baseline: 33.3%)
QUAL_TRUESKILL_THRESHOLD = 27.0     # Must have μ > 27 (baseline: 25)
CONFIDENCE_LEVEL = 0.95             # 95% confidence interval

# ── Role name map ─────────────────────────────────────────────────────────────
ROLE_NAMES = [
    "Settler", "Mayor", "Builder", "Craftsman",
    "Trader", "Captain", "Prospector1", "Prospector2",
]


# ── Scenario definition ───────────────────────────────────────────────────────
class Scenario(NamedTuple):
    name: str
    agents: dict[str, object]  # unique_name → agent_instance
    focal: set[str]            # agents of interest
    is_qualification: bool     # True if this is a "vs Random" qualification test


def build_scenarios(action_dim: int, env: PuertoRicoEnv = None) -> list[Scenario]:
    """
    Instantiate all required agent objects and define evaluation scenarios.
    
    Scenarios 1-3: Qualification tests (Bot vs Random × 2)
    Scenario 4: Relative strength comparison (all 3 bots)
    
    Args:
        action_dim: Action dimension for agents
        env: Environment reference (needed for ActionValueAgent)
    """
    # Scenario 1: Shipping vs Random vs Random (Qualification)
    S1 = ShippingRushAgent(action_dim, fixed_strategy=0).eval()
    R1 = RandomBot(action_dim).eval()
    R2 = RandomBot(action_dim).eval()
    sc1_agents = {"Shipping": S1, "Random_A": R1, "Random_B": R2}

    # Scenario 2: Factory vs Random vs Random (Qualification)
    F1 = FactoryRuleBasedAgent(action_dim).eval()
    R3 = RandomBot(action_dim).eval()
    R4 = RandomBot(action_dim).eval()
    sc2_agents = {"Factory": F1, "Random_A": R3, "Random_B": R4}

    # Scenario 3: ActionValue vs Random vs Random (Qualification)
    D1 = ActionValueAgent(action_dim).eval()
    if env is not None:
        D1.set_env(env)
    R5 = RandomBot(action_dim).eval()
    R6 = RandomBot(action_dim).eval()
    sc3_agents = {"ActionValue": D1, "Random_A": R5, "Random_B": R6}

    # Scenario 4: ActionValue vs Shipping vs Factory (Relative Strength)
    D2 = ActionValueAgent(action_dim).eval()
    if env is not None:
        D2.set_env(env)
    S2 = ShippingRushAgent(action_dim, fixed_strategy=0).eval()
    F2 = FactoryRuleBasedAgent(action_dim).eval()
    sc4_agents = {"ActionValue": D2, "Shipping": S2, "Factory": F2}

    return [
        Scenario("Shipping vs Random vs Random", sc1_agents, {"Shipping"}, is_qualification=True),
        Scenario("Factory vs Random vs Random",  sc2_agents, {"Factory"}, is_qualification=True),
        Scenario("ActionValue vs Random vs Random",   sc3_agents, {"ActionValue"}, is_qualification=True),
        Scenario("ActionValue vs Shipping vs Factory", sc4_agents, {"ActionValue", "Shipping", "Factory"}, is_qualification=False),
    ]


# ── Statistical helpers ───────────────────────────────────────────────────────
def _wilson_ci(wins: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score confidence interval for binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    p = wins / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return (max(0, center - margin), min(1, center + margin))


def _trueskill_ci(mu: float, sigma: float, confidence: float = 0.95) -> tuple[float, float]:
    """Approximate confidence interval for TrueSkill μ."""
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    return (mu - z * sigma, mu + z * sigma)


# ── Accumulate results into trackers ─────────────────────────────────────────
def _accumulate(raw_results: list[dict],
                pool: list[str],
                ts: TrueSkillTracker,
                vp_margin: VPMarginTracker,
                vp_decomp_t: VPDecompositionTracker,
                role_entropy: RoleEntropyTracker,
                win_counts: dict[str, int],
                gp: dict[str, int],
                total_apa: dict[str, float],
                total_ppa: dict[str, float]) -> None:
    for rec in raw_results:
        ts.update(rec["ranks"])
        vp_margin.update(rec["scores"])
        vp_decomp_t.update(rec["vp_decomp"])
        role_entropy.update(rec["role_counts"])
        for name, rank in rec["ranks"].items():
            gp[name] += 1
            if rank == 1:
                win_counts[name] += 1
        # APA/PPA accumulation
        for name, apa_val in rec.get("apa", {}).items():
            if name in pool:
                total_apa[name] += apa_val
        for name, ppa_val in rec.get("ppa", {}).items():
            if name in pool:
                total_ppa[name] += ppa_val


# ── Run a single scenario ─────────────────────────────────────────────────────
def run_scenario(scenario: Scenario, games_per_perm: int,
                 env: PuertoRicoEnv, obs_dim: int, action_dim: int) -> dict:
    pool      = list(scenario.agents.keys())
    all_perms = list(itertools.permutations(pool))

    ts           = TrueSkillTracker(pool)
    vp_margin    = VPMarginTracker(pool)
    vp_decomp_t  = VPDecompositionTracker(pool)
    role_entropy = RoleEntropyTracker(pool)
    win_counts   = {n: 0 for n in pool}
    gp           = {n: 0 for n in pool}
    total_apa    = {n: 0.0 for n in pool}
    total_ppa    = {n: 0.0 for n in pool}

    # Update env reference for ActionValueAgent
    for name, agent in scenario.agents.items():
        if isinstance(agent, ActionValueAgent):
            agent.set_env(env)

    evaluator = GameEvaluator(env, obs_dim, action_dim)

    total_perms = len(all_perms)
    total_games = total_perms * games_per_perm
    qual_tag = " [QUALIFICATION]" if scenario.is_qualification else ""
    print(f"\n  {'─'*60}")
    print(f"  Scenario : {scenario.name}{qual_tag}")
    print(f"  Agents   : {pool}")
    print(f"  Perms    : {total_perms}  ×  {games_per_perm} games = {total_games:,} total")
    print(f"  {'─'*60}")

    t0 = time.time()
    for idx, perm in enumerate(all_perms):
        print(f"    [{idx+1:2d}/{total_perms}] {perm} ...", end="", flush=True)
        res = evaluator.run_permutation_parallel(perm, scenario.agents, games_per_perm)
        _accumulate(res["raw_results"], pool, ts,
                    vp_margin, vp_decomp_t, role_entropy, win_counts, gp,
                    total_apa, total_ppa)
        print(f" done", flush=True)

    elapsed = time.time() - t0
    print(f"  Elapsed: {elapsed:.1f}s  ({elapsed / total_games:.3f}s/game)")

    # ── Compile results ───────────────────────────────────────────────────────
    ts_ratings   = ts.get_ratings_dict()
    margins      = vp_margin.get_average_margins()
    vp_dec       = vp_decomp_t.get_averages()
    entropies    = role_entropy.get_entropies()
    role_dist    = role_entropy.get_distributions()

    results: dict[str, dict] = {}
    for name in pool:
        played = gp[name]
        wins   = win_counts[name]
        mu     = ts_ratings[name]["mu"]
        sigma  = ts_ratings[name]["sigma"]
        win_rate = wins / played if played > 0 else 0.0
        
        # Confidence intervals
        win_ci = _wilson_ci(wins, played, CONFIDENCE_LEVEL)
        ts_ci  = _trueskill_ci(mu, sigma, CONFIDENCE_LEVEL)
        
        results[name] = {
            "trueskill_mu":       mu,
            "trueskill_sigma":    sigma,
            "trueskill_ci":       ts_ci,
            "win_rate":           win_rate,
            "win_rate_ci":        win_ci,
            "wins":               wins,
            "games_played":       played,
            "avg_vp_margin":      margins[name],
            "avg_ship_vp":        vp_dec[name]["shipping"],
            "avg_bldg_vp":        vp_dec[name]["building"],
            "avg_apa":            total_apa[name] / max(1, played),
            "avg_ppa":            total_ppa[name] / max(1, played),
            "role_entropy":       entropies[name],
            "role_distribution": {
                ROLE_NAMES[r]: float(role_dist[name][r])
                for r in range(8)
            },
        }

    return {
        "scenario_name": scenario.name,
        "is_qualification": scenario.is_qualification,
        "games_per_perm": games_per_perm,
        "total_games": total_games,
        "elapsed_s": elapsed,
        "results": results,
        "focal_agents": list(scenario.focal),
    }


# ── Pretty-print a scenario summary ──────────────────────────────────────────
def print_scenario_summary(report: dict) -> None:
    qual_tag = " [QUALIFICATION]" if report.get("is_qualification") else ""
    print(f"\n{'═'*90}")
    print(f"  {report['scenario_name']}{qual_tag}")
    print(f"  Total games: {report['total_games']:,}  |  Time: {report['elapsed_s']:.1f}s")
    print(f"{'═'*90}")
    print(f"  {'Agent':<16} {'TrueSkill μ':>11} {'95% CI':>14} {'WinRate':>8} {'95% CI':>14} "
          f"{'APA':>7} {'PPA':>7}")
    print(f"  {'─'*90}")

    # Sort by TrueSkill μ descending
    sorted_names = sorted(report["results"].keys(),
                          key=lambda n: report["results"][n]["trueskill_mu"],
                          reverse=True)
    for name in sorted_names:
        r = report["results"][name]
        focal_tag = " ★" if name in report["focal_agents"] else "  "
        ts_ci = r.get("trueskill_ci", (0, 0))
        wr_ci = r.get("win_rate_ci", (0, 0))
        print(
            f"  {name:<16}{focal_tag} "
            f"{r['trueskill_mu']:>9.2f} "
            f"[{ts_ci[0]:>5.1f},{ts_ci[1]:>5.1f}] "
            f"{r['win_rate']:>8.1%} "
            f"[{wr_ci[0]:>5.1%},{wr_ci[1]:>5.1%}] "
            f"{r.get('avg_apa', 0):>+7.2f} "
            f"{r.get('avg_ppa', 0):>+7.2f}"
        )

    # VP decomposition
    print(f"\n  VP Decomposition:")
    print(f"  {'Agent':<16}  {'ΔVP':>8} {'ShipVP':>8} {'BldgVP':>8} {'RoleH':>7}")
    print(f"  {'─'*55}")
    for name in sorted_names:
        r = report["results"][name]
        print(f"  {name:<16}  {r['avg_vp_margin']:>+8.2f} {r['avg_ship_vp']:>8.1f} "
              f"{r['avg_bldg_vp']:>8.1f} {r['role_entropy']:>7.3f}")

    # Role distribution
    print(f"\n  Role Selection Distribution:")
    print(f"  {'Agent':<16}  " + "  ".join(f"{rn[:6]:>6}" for rn in ROLE_NAMES))
    print(f"  {'─'*80}")
    for name in sorted_names:
        rd = report["results"][name]["role_distribution"]
        row = "  ".join(f"{rd.get(rn, 0):>6.1%}" for rn in ROLE_NAMES)
        print(f"  {name:<16}  {row}")


# ── Qualification judgment ────────────────────────────────────────────────────
def evaluate_qualification(all_reports: list[dict]) -> dict:
    """
    Evaluate bot qualification based on vs-Random scenarios.
    Returns qualification results with pass/fail status.
    """
    qual_results = {}
    
    for report in all_reports:
        if not report.get("is_qualification"):
            continue
        
        # Find the focal agent (the bot being tested) and Random agents
        focal_name = None
        random_names = []
        for name in report["results"]:
            if "Random" in name:
                random_names.append(name)
            elif name in report["focal_agents"]:
                focal_name = name
        
        if focal_name is None:
            continue
        
        focal = report["results"][focal_name]
        
        # Get Random baseline (average of Random_A and Random_B)
        random_mu = np.mean([report["results"][rn]["trueskill_mu"] for rn in random_names])
        random_wr = np.mean([report["results"][rn]["win_rate"] for rn in random_names])
        random_ci_upper = max(report["results"][rn]["trueskill_ci"][1] for rn in random_names)
        
        # Qualification criteria
        wr_pass = focal["win_rate"] > QUAL_WIN_RATE_THRESHOLD
        ts_pass = focal["trueskill_mu"] > QUAL_TRUESKILL_THRESHOLD
        
        # Statistical significance: focal's lower CI bound > Random's upper CI bound
        focal_ci_lower = focal["trueskill_ci"][0]
        sig_pass = focal_ci_lower > random_ci_upper
        
        overall_pass = wr_pass and ts_pass and sig_pass
        
        qual_results[focal_name] = {
            "scenario": report["scenario_name"],
            "win_rate": focal["win_rate"],
            "win_rate_ci": focal["win_rate_ci"],
            "trueskill_mu": focal["trueskill_mu"],
            "trueskill_ci": focal["trueskill_ci"],
            "random_mu": random_mu,
            "random_ci_upper": random_ci_upper,
            "avg_apa": focal.get("avg_apa", 0),
            "avg_ppa": focal.get("avg_ppa", 0),
            "criteria": {
                "win_rate_pass": wr_pass,
                "trueskill_pass": ts_pass,
                "significance_pass": sig_pass,
            },
            "qualified": overall_pass,
        }
    
    return qual_results


def print_qualification_summary(qual_results: dict) -> None:
    """Print qualification summary table."""
    print(f"\n{'═'*90}")
    print("  QUALIFICATION SUMMARY — Bot Ecosystem Eligibility")
    print(f"  Criteria: Win Rate > {QUAL_WIN_RATE_THRESHOLD:.0%}, TrueSkill μ > {QUAL_TRUESKILL_THRESHOLD:.0f}, "
          f"95% CI no overlap with Random")
    print(f"{'═'*90}")
    
    if not qual_results:
        print("  No qualification scenarios were run.")
        return
    
    print(f"  {'Bot':<12} {'WinRate':>8} {'[95% CI]':>14} {'μ':>7} {'[95% CI]':>14} "
          f"{'vs Rand':>8} {'APA':>7} {'PPA':>7} {'Status':>10}")
    print(f"  {'─'*100}")
    
    for bot_name, result in qual_results.items():
        wr = result["win_rate"]
        wr_ci = result["win_rate_ci"]
        mu = result["trueskill_mu"]
        ts_ci = result["trueskill_ci"]
        rand_mu = result["random_mu"]
        apa = result["avg_apa"]
        ppa = result["avg_ppa"]
        
        status = "✓ PASS" if result["qualified"] else "✗ FAIL"
        status_detail = []
        if not result["criteria"]["win_rate_pass"]:
            status_detail.append("WR")
        if not result["criteria"]["trueskill_pass"]:
            status_detail.append("TS")
        if not result["criteria"]["significance_pass"]:
            status_detail.append("SIG")
        
        if status_detail:
            status = f"✗ FAIL ({','.join(status_detail)})"
        
        print(f"  {bot_name:<12} {wr:>8.1%} [{wr_ci[0]:>5.1%},{wr_ci[1]:>5.1%}] "
              f"{mu:>7.1f} [{ts_ci[0]:>5.1f},{ts_ci[1]:>5.1f}] "
              f"{mu - rand_mu:>+8.1f} {apa:>+7.2f} {ppa:>+7.2f} {status:>10}")
    
    print()
    
    # Final verdict
    all_pass = all(r["qualified"] for r in qual_results.values())
    if all_pass:
        print("  ✓ ALL BOTS QUALIFIED for PPO evaluation ecosystem")
    else:
        failed = [name for name, r in qual_results.items() if not r["qualified"]]
        print(f"  ✗ FAILED: {', '.join(failed)}")
        print("    These bots do not demonstrate statistically significant superiority over Random.")


# ── Cross-scenario comparison ─────────────────────────────────────────────────
def print_cross_comparison(all_reports: list[dict]) -> None:
    print(f"\n{'═'*90}")
    print("  CROSS-SCENARIO SUMMARY")
    print(f"{'═'*90}")
    print(f"  {'Agent Type':<16}  {'Scenario':<36}  {'TrueSkill μ':>11}  {'WinRate':>8}  {'APA':>7}  {'PPA':>7}")
    print(f"  {'─'*95}")

    for report in all_reports:
        for name in sorted(report["results"].keys()):
            r = report["results"][name]
            focal_tag = "★ " if name in report["focal_agents"] else "  "
            print(f"  {focal_tag}{name:<16}  {report['scenario_name']:<36}  "
                  f"{r['trueskill_mu']:>11.2f}  {r['win_rate']:>8.1%}  "
                  f"{r.get('avg_apa', 0):>+7.2f}  {r.get('avg_ppa', 0):>+7.2f}")
    print()


# ── Visualization generation ──────────────────────────────────────────────────
def generate_visualizations(all_reports: list[dict], output_dir: str) -> None:
    """Generate visual reports for benchmark results."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("  [WARN] matplotlib not installed, skipping visualizations")
        return
    
    plt.style.use('seaborn-v0_8-whitegrid')
    
    # Color scheme
    COLORS = {
        'ActionValue': '#2ecc71',      # Green
        'Shipping': '#3498db',    # Blue
        'Factory': '#e74c3c',     # Red
        'Random': '#95a5a6',      # Gray
    }
    
    def get_color(name: str) -> str:
        for key, color in COLORS.items():
            if key in name:
                return color
        return '#9b59b6'  # Purple for unknown
    
    # ═══ 1. TrueSkill Comparison Bar Chart ═══
    fig, axes = plt.subplots(len(all_reports), 1, figsize=(12, 4 * len(all_reports)))
    if len(all_reports) == 1:
        axes = [axes]
    
    for idx, report in enumerate(all_reports):
        ax = axes[idx]
        results = report["results"]
        names = list(results.keys())
        
        # Sort by TrueSkill μ
        names_sorted = sorted(names, key=lambda n: results[n]["trueskill_mu"], reverse=True)
        
        mus = [results[n]["trueskill_mu"] for n in names_sorted]
        sigmas = [results[n]["trueskill_sigma"] for n in names_sorted]
        colors = [get_color(n) for n in names_sorted]
        
        bars = ax.barh(names_sorted, mus, xerr=sigmas, color=colors, 
                       edgecolor='black', linewidth=1, capsize=5, alpha=0.85)
        
        # Add value labels
        for bar, mu, sigma in zip(bars, mus, sigmas):
            ax.text(mu + sigma + 1, bar.get_y() + bar.get_height()/2,
                   f'{mu:.1f}±{sigma:.1f}', va='center', fontsize=10)
        
        ax.set_xlabel('TrueSkill μ (with σ error bars)', fontsize=11)
        ax.set_title(f'Scenario: {report["scenario_name"]}', fontsize=12, fontweight='bold')
        ax.set_xlim(0, max(mus) + max(sigmas) + 15)
        ax.invert_yaxis()
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'trueskill_comparison.png'), dpi=150, bbox_inches='tight')
    plt.close()
    
    # ═══ 2. Win Rate Comparison ═══
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Collect all unique agent base names across scenarios
    all_agents = set()
    for report in all_reports:
        for name in report["results"].keys():
            # Extract base name (e.g., "ActionValue_A" -> "ActionValue")
            base = name.split('_')[0] if '_' in name else name
            all_agents.add(base)
    
    scenario_names = [r["scenario_name"][:25] + "..." if len(r["scenario_name"]) > 25 
                      else r["scenario_name"] for r in all_reports]
    x = np.arange(len(scenario_names))
    width = 0.2
    
    agent_bases = sorted(all_agents)
    
    for i, base in enumerate(agent_bases):
        win_rates = []
        for report in all_reports:
            # Find agents matching this base name
            matching = [n for n in report["results"].keys() if n.startswith(base)]
            if matching:
                # Average win rate if multiple (e.g., ActionValue_A, ActionValue_B)
                avg_wr = np.mean([report["results"][n]["win_rate"] for n in matching])
                win_rates.append(avg_wr * 100)
            else:
                win_rates.append(0)
        
        offset = (i - len(agent_bases)/2 + 0.5) * width
        bars = ax.bar(x + offset, win_rates, width, label=base, color=get_color(base),
                     edgecolor='black', linewidth=0.5)
        
        # Add value labels on bars
        for bar, wr in zip(bars, win_rates):
            if wr > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                       f'{wr:.0f}%', ha='center', va='bottom', fontsize=8, rotation=0)
    
    ax.set_ylabel('Win Rate (%)', fontsize=11)
    ax.set_xlabel('Scenario', fontsize=11)
    ax.set_title('Win Rate Comparison Across Scenarios', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(scenario_names, rotation=15, ha='right', fontsize=9)
    ax.legend(loc='upper right', fontsize=10)
    ax.set_ylim(0, 110)
    ax.axhline(y=33.3, color='gray', linestyle='--', alpha=0.5, label='Random baseline')
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'win_rate_comparison.png'), dpi=150, bbox_inches='tight')
    plt.close()
    
    # ═══ 3. VP Decomposition (Ship vs Building) ═══
    fig, axes = plt.subplots(1, len(all_reports), figsize=(5 * len(all_reports), 5))
    if len(all_reports) == 1:
        axes = [axes]
    
    for idx, report in enumerate(all_reports):
        ax = axes[idx]
        results = report["results"]
        names = sorted(results.keys(), key=lambda n: results[n]["trueskill_mu"], reverse=True)
        
        ship_vps = [results[n]["avg_ship_vp"] for n in names]
        bldg_vps = [results[n]["avg_bldg_vp"] for n in names]
        colors = [get_color(n) for n in names]
        
        y_pos = np.arange(len(names))
        
        ax.barh(y_pos, ship_vps, label='Shipping VP', color='#3498db', alpha=0.8)
        ax.barh(y_pos, bldg_vps, left=ship_vps, label='Building VP', color='#e67e22', alpha=0.8)
        
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names)
        ax.set_xlabel('Victory Points')
        ax.set_title(f'{report["scenario_name"][:20]}...', fontsize=10, fontweight='bold')
        ax.invert_yaxis()
        
        if idx == 0:
            ax.legend(loc='lower right', fontsize=9)
    
    plt.suptitle('VP Decomposition: Shipping vs Building', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'vp_decomposition.png'), dpi=150, bbox_inches='tight')
    plt.close()
    
    # ═══ 4. Role Selection Heatmap ═══
    for idx, report in enumerate(all_reports):
        fig, ax = plt.subplots(figsize=(10, 4))
        
        results = report["results"]
        names = sorted(results.keys(), key=lambda n: results[n]["trueskill_mu"], reverse=True)
        
        role_data = []
        for name in names:
            rd = results[name]["role_distribution"]
            role_data.append([rd.get(rn, 0) for rn in ROLE_NAMES])
        
        role_matrix = np.array(role_data) * 100  # Convert to percentage
        
        im = ax.imshow(role_matrix, cmap='YlOrRd', aspect='auto', vmin=0, vmax=40)
        
        ax.set_xticks(np.arange(len(ROLE_NAMES)))
        ax.set_yticks(np.arange(len(names)))
        ax.set_xticklabels(ROLE_NAMES, rotation=45, ha='right')
        ax.set_yticklabels(names)
        
        # Add text annotations
        for i in range(len(names)):
            for j in range(len(ROLE_NAMES)):
                val = role_matrix[i, j]
                color = 'white' if val > 20 else 'black'
                ax.text(j, i, f'{val:.0f}%', ha='center', va='center', 
                       color=color, fontsize=9)
        
        ax.set_title(f'Role Selection Distribution: {report["scenario_name"]}', 
                    fontsize=12, fontweight='bold')
        
        cbar = plt.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label('Selection %', fontsize=10)
        
        plt.tight_layout()
        safe_name = report["scenario_name"].replace(" ", "_").replace("/", "_")
        plt.savefig(os.path.join(output_dir, f'role_heatmap_{idx+1}_{safe_name[:20]}.png'), 
                   dpi=150, bbox_inches='tight')
        plt.close()
    
    # ═══ 5. Summary Dashboard ═══
    fig = plt.figure(figsize=(16, 10))
    
    # Header
    fig.suptitle('Heuristic Bot Benchmark Summary', fontsize=18, fontweight='bold', y=0.98)
    
    # Create grid
    gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
    
    # Top-left: Overall ranking
    ax1 = fig.add_subplot(gs[0, 0])
    
    # Aggregate stats across all scenarios
    agent_stats = {}
    for report in all_reports:
        for name, r in report["results"].items():
            base = name.split('_')[0] if '_' in name else name
            if base not in agent_stats:
                agent_stats[base] = {"wins": 0, "games": 0, "mu_sum": 0, "count": 0}
            agent_stats[base]["wins"] += r["wins"]
            agent_stats[base]["games"] += r["games_played"]
            agent_stats[base]["mu_sum"] += r["trueskill_mu"]
            agent_stats[base]["count"] += 1
    
    # Calculate aggregated metrics
    agg_data = []
    for base, stats in agent_stats.items():
        avg_wr = stats["wins"] / stats["games"] if stats["games"] > 0 else 0
        avg_mu = stats["mu_sum"] / stats["count"] if stats["count"] > 0 else 0
        agg_data.append((base, avg_wr, avg_mu, stats["games"]))
    
    agg_data.sort(key=lambda x: x[2], reverse=True)  # Sort by avg TrueSkill
    
    # Plot overall ranking
    bases = [d[0] for d in agg_data]
    avg_mus = [d[2] for d in agg_data]
    colors = [get_color(b) for b in bases]
    
    bars = ax1.barh(bases, avg_mus, color=colors, edgecolor='black', linewidth=1)
    ax1.set_xlabel('Average TrueSkill μ', fontsize=11)
    ax1.set_title('Overall Agent Ranking (All Scenarios)', fontsize=12, fontweight='bold')
    ax1.invert_yaxis()
    
    for bar, d in zip(bars, agg_data):
        ax1.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                f'WR: {d[1]*100:.1f}%', va='center', fontsize=10)
    
    # Top-right: Win rate by scenario type
    ax2 = fig.add_subplot(gs[0, 1])
    
    # Group scenarios
    av_scenarios = [r for r in all_reports if 'ActionValue' in r["scenario_name"]]
    other_scenarios = [r for r in all_reports if 'ActionValue' not in r["scenario_name"]]
    
    if av_scenarios:
        av_wr = []
        for r in av_scenarios:
            av_agents = [n for n in r["results"].keys() if 'ActionValue' in n]
            if av_agents:
                avg = np.mean([r["results"][n]["win_rate"] for n in av_agents])
                av_wr.append(avg * 100)
        
        ax2.bar(['ActionValue\n(avg across scenarios)'], [np.mean(av_wr)], 
               color=get_color('ActionValue'), edgecolor='black', width=0.5)
        ax2.axhline(y=33.3, color='gray', linestyle='--', alpha=0.7)
        ax2.text(0, 35, 'Random baseline (33.3%)', ha='center', fontsize=9, color='gray')
        ax2.set_ylabel('Win Rate (%)')
        ax2.set_title('ActionValue Agent Performance', fontsize=12, fontweight='bold')
        ax2.set_ylim(0, 110)
        ax2.text(0, np.mean(av_wr) + 3, f'{np.mean(av_wr):.1f}%', 
                ha='center', fontsize=12, fontweight='bold')
    
    # Bottom-left: VP comparison
    ax3 = fig.add_subplot(gs[1, 0])
    
    vp_by_agent = {}
    for report in all_reports:
        for name, r in report["results"].items():
            base = name.split('_')[0] if '_' in name else name
            if base not in vp_by_agent:
                vp_by_agent[base] = {"ship": [], "bldg": []}
            vp_by_agent[base]["ship"].append(r["avg_ship_vp"])
            vp_by_agent[base]["bldg"].append(r["avg_bldg_vp"])
    
    bases = sorted(vp_by_agent.keys(), key=lambda b: np.mean(vp_by_agent[b]["ship"]) + 
                                                      np.mean(vp_by_agent[b]["bldg"]), reverse=True)
    
    x_pos = np.arange(len(bases))
    ship_means = [np.mean(vp_by_agent[b]["ship"]) for b in bases]
    bldg_means = [np.mean(vp_by_agent[b]["bldg"]) for b in bases]
    
    ax3.bar(x_pos - 0.2, ship_means, 0.4, label='Shipping VP', color='#3498db')
    ax3.bar(x_pos + 0.2, bldg_means, 0.4, label='Building VP', color='#e67e22')
    ax3.set_xticks(x_pos)
    ax3.set_xticklabels(bases)
    ax3.set_ylabel('Average VP')
    ax3.set_title('VP Source Comparison', fontsize=12, fontweight='bold')
    ax3.legend(loc='upper right')
    
    # Bottom-right: Key metrics table
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.axis('off')
    
    table_data = []
    headers = ['Agent', 'Avg WR', 'Avg μ', 'Total Games']
    for base, wr, mu, games in agg_data:
        table_data.append([base, f'{wr*100:.1f}%', f'{mu:.1f}', str(games)])
    
    table = ax4.table(cellText=table_data, colLabels=headers, loc='center',
                     cellLoc='center', colColours=['#ecf0f1']*4)
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 1.8)
    
    # Color cells by agent
    for i, (base, _, _, _) in enumerate(agg_data):
        table[(i+1, 0)].set_facecolor(get_color(base))
        table[(i+1, 0)].set_text_props(color='white', fontweight='bold')
    
    ax4.set_title('Aggregated Statistics', fontsize=12, fontweight='bold', pad=20)
    
    plt.savefig(os.path.join(output_dir, 'summary_dashboard.png'), dpi=150, bbox_inches='tight')
    plt.close()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Heuristic Bot Benchmark — 7 scenarios × all permutations × TrueSkill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--games", type=int, default=300,
                        help="Games per seat permutation (default: 300)")
    parser.add_argument("--report_tag", type=str, default="",
                        help="Optional suffix for the report directory")
    parser.add_argument("--dry_run", action="store_true",
                        help="Run 1 game per permutation for sanity check")
    parser.add_argument("--scenarios", type=str, default="all",
                        help="Comma-separated scenario indices (1-7) or 'all' (default: all)")
    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN] Overriding --games → 1")
        args.games = 1

    # Shared environment (re-used across scenarios)
    env = PuertoRicoEnv(num_players=NUM_PLAYERS, max_game_steps=1500)
    obs_dim    = get_flattened_obs_dim(
        env.observation_space(env.possible_agents[0])["observation"]
    )
    action_dim = env.action_space(env.possible_agents[0]).n

    print(f"\n{'═'*70}")
    print(f"  HEURISTIC BENCHMARK SUITE")
    print(f"  obs_dim={obs_dim}  action_dim={action_dim}  games_per_perm={args.games}")
    print(f"{'═'*70}")

    all_scenarios = build_scenarios(action_dim, env)
    
    # Filter scenarios if specified
    if args.scenarios.lower() == "all":
        scenarios = all_scenarios
    else:
        indices = [int(i.strip()) - 1 for i in args.scenarios.split(",")]
        scenarios = [all_scenarios[i] for i in indices if 0 <= i < len(all_scenarios)]
    
    all_reports  = []

    for sc in scenarios:
        report = run_scenario(sc, args.games, env, obs_dim, action_dim)
        all_reports.append(report)
        print_scenario_summary(report)

    # ── Qualification evaluation ──────────────────────────────────────────────
    qual_results = evaluate_qualification(all_reports)
    print_qualification_summary(qual_results)

    print_cross_comparison(all_reports)

    # ── Save JSON report ──────────────────────────────────────────────────────
    tag  = f"_{args.report_tag}" if args.report_tag else ""
    rdir = f"report/Heuristic_Benchmark_{int(time.time())}{tag}"
    os.makedirs(rdir, exist_ok=True)

    class _NpEncoder(json.JSONEncoder):
        def default(self, obj):
            import numpy as np
            if isinstance(obj, (np.bool_,)): return bool(obj)
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            return super().default(obj)

    report_path = os.path.join(rdir, "results.json")
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": int(time.time()),
            "games_per_perm": args.games,
            "qualification_thresholds": {
                "win_rate": QUAL_WIN_RATE_THRESHOLD,
                "trueskill_mu": QUAL_TRUESKILL_THRESHOLD,
                "confidence_level": CONFIDENCE_LEVEL,
            },
            "qualification_results": qual_results,
            "scenarios": all_reports,
        }, f, indent=2, cls=_NpEncoder)

    print(f"  Report saved → {report_path}")
    
    # ── Generate visualizations ───────────────────────────────────────────────
    generate_visualizations(all_reports, rdir)
    print(f"  Visualizations saved → {rdir}/\n")


if __name__ == "__main__":
    main()
