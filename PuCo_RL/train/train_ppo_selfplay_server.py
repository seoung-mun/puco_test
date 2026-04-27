import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import copy
import time
import random
import subprocess
import argparse
import threading

import torch
import torch.nn as nn
import torch.optim as optim
import torch.multiprocessing as mp
import numpy as np
try:
    from torch.utils.tensorboard import SummaryWriter
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    SummaryWriter = None

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
from agents.ppo_agent import Agent
from agents.shipping_rush_agent import ShippingRushAgent
from configs.constants import Role, BuildingType
from common.bundle import write_bundle

# ── 하이퍼파라미터 ─────────────────────────────────────────────────────────────
NUM_PLAYERS = 3
NUM_ENVS = 64
STEPS_PER_ENV = 1024
BATCH_SIZE = NUM_ENVS * STEPS_PER_ENV
MINIBATCH_SIZE = 1024
UPDATE_EPOCHS = 10
LEARNING_RATE = 3e-4
GAMMA = 0.99
GAE_LAMBDA = 0.95
CLIP_COEF = 0.2
INITIAL_ENT_COEF = 0.05
MIN_ENT_COEF = 0.015
VF_COEF = 0.5
MAX_GRAD_NORM = 0.5

TOTAL_TIMESTEPS = 100_000_000
SNAPSHOT_INTERVAL = 25
OPPONENT_POOL_SIZE = 100
MAX_GAME_STEPS = 1200

# Pipe command constants
CMD_STEP = 0
CMD_SET_WEIGHTS = 1
CMD_CLOSE = 2


class NoOpSummaryWriter:
    def add_scalar(self, *_args, **_kwargs):
        return None

    def close(self):
        return None


# ── Experiment config saver ───────────────────────────────────────────────────
def resolve_runtime_config(args: argparse.Namespace) -> dict[str, int]:
    if args.local_smoke:
        config = {
            "num_envs": 1,
            "steps_per_env": 4,
            "minibatch_size": 4,
            "update_epochs": 1,
            "total_timesteps": 4,
            "snapshot_interval": 1,
            "opponent_pool_size": 4,
            "max_game_steps": MAX_GAME_STEPS,
            "use_threads": True,
        }
    else:
        config = {
            "num_envs": NUM_ENVS,
            "steps_per_env": STEPS_PER_ENV,
            "minibatch_size": MINIBATCH_SIZE,
            "update_epochs": UPDATE_EPOCHS,
            "total_timesteps": TOTAL_TIMESTEPS,
            "snapshot_interval": SNAPSHOT_INTERVAL,
            "opponent_pool_size": OPPONENT_POOL_SIZE,
            "max_game_steps": MAX_GAME_STEPS,
            "use_threads": False,
        }

    overrides = {
        "num_envs": args.num_envs,
        "steps_per_env": args.steps_per_env,
        "minibatch_size": args.minibatch_size,
        "update_epochs": args.update_epochs,
        "total_timesteps": args.total_timesteps,
        "snapshot_interval": args.snapshot_interval,
        "opponent_pool_size": args.opponent_pool_size,
        "max_game_steps": args.max_game_steps,
    }
    for key, value in overrides.items():
        if value is not None:
            config[key] = value

    config["batch_size"] = config["num_envs"] * config["steps_per_env"]

    if config["num_envs"] <= 0:
        raise ValueError("--num_envs must be >= 1")
    if config["steps_per_env"] <= 0:
        raise ValueError("--steps_per_env must be >= 1")
    if config["update_epochs"] <= 0:
        raise ValueError("--update_epochs must be >= 1")
    if config["minibatch_size"] <= 0:
        raise ValueError("--minibatch_size must be >= 1")
    if config["total_timesteps"] < config["batch_size"]:
        raise ValueError(
            f"--total_timesteps ({config['total_timesteps']}) must be >= batch_size ({config['batch_size']})."
        )
    if config["snapshot_interval"] <= 0:
        raise ValueError("--snapshot_interval must be >= 1")
    if config["opponent_pool_size"] <= 0:
        raise ValueError("--opponent_pool_size must be >= 1")
    if config["max_game_steps"] <= 0:
        raise ValueError("--max_game_steps must be >= 1")

    return config


def save_experiment_config(
    run_name: str,
    log_dir: str,
    args: argparse.Namespace,
    config: dict[str, int],
) -> None:
    """
    Serialize all experiment parameters to JSON at training start.
    Enables reproducibility without manual note-taking.
    """
    try:
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
    except Exception:
        git_hash = "unknown"

    if args.rule_based_prob > 0:
        selfplay_type = "league"
        selfplay_desc = (
            f"Shipping Rush bot (fixed_strategy=0) "
            f"with prob={args.rule_based_prob:.2f}; "
            f"past-self with prob={1 - args.rule_based_prob:.2f}"
        )
    else:
        selfplay_type = "pure_self_play"
        selfplay_desc = (
            "opp1=latest_agent, opp2=past_agent_from_pool "
            "(fallback: latest_agent when pool empty)"
        )

    config = {
        "run_name": run_name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_hash": git_hash,

        "model_architecture": {
            "type": "PPOAgent (ResidualMLP)",
            "hidden_dim": 512,
            "num_res_blocks": 3,
            "actor_head": "Linear(512 → 200, std=0.01)",
            "critic_head": "Linear(512 → 1, std=1.0)",
        },

        "environment": {
            "num_players": NUM_PLAYERS,
            "max_game_steps": config["max_game_steps"],
        },

        "hyperparameters": {
            "num_envs": config["num_envs"],
            "steps_per_env": config["steps_per_env"],
            "total_timesteps": config["total_timesteps"],
            "batch_size": config["batch_size"],
            "minibatch_size": config["minibatch_size"],
            "update_epochs": config["update_epochs"],
            "learning_rate_initial": LEARNING_RATE,
            "learning_rate_min": 1e-5,
            "learning_rate_schedule": "linear_decay",
            "gamma": GAMMA,
            "gae_lambda": GAE_LAMBDA,
            "clip_coef": CLIP_COEF,
            "initial_ent_coef": INITIAL_ENT_COEF,
            "min_ent_coef": MIN_ENT_COEF,
            "vf_coef": VF_COEF,
            "max_grad_norm": MAX_GRAD_NORM,
        },

        "self_play": {
            "type": selfplay_type,
            "description": selfplay_desc,
            "snapshot_interval_updates": config["snapshot_interval"],
            "opponent_pool_size": config["opponent_pool_size"],
            "rule_based_prob": args.rule_based_prob,
            "rule_based_strategy": "Shipping Rush (index=0)" if args.rule_based_prob > 0 else "none",
            "opp1_role": "latest_agent (always)",
            "opp2_role": (
                f"rule_based Shipping(p={args.rule_based_prob:.2f}) "
                f"| pool past-self(p={1-args.rule_based_prob:.2f})"
                if args.rule_based_prob > 0
                else "pool past-self | latest_agent (when pool empty)"
            ),
        },

        "pbrs": {
            "enabled": True,
            "shaping_gamma": 0.99,
            "potential_function": "VP_chip + Building_VP + Large_Building_Bonus",
            "note": "Rule-based VP only — no heuristic components",
            "scale_factor": 0.01,
        },

        "cli_args": vars(args),
    }

    config_path = os.path.join(log_dir, "experiment_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"[Config] Saved → {config_path}")
    print(f"[Config] Self-play mode : {selfplay_type}")
    print(f"[Config] Rule-based prob: {args.rule_based_prob:.2f}")


# ── Rollout worker ────────────────────────────────────────────────────────────
def rollout_worker(rank, conn, shared_bufs, obs_dim, action_dim,
                   opponent_pool, rule_based_prob: float,
                   steps_per_env: int, max_game_steps: int):
    """
    Persistent worker process.
    PBRS is always enabled (no flag needed).
    Opponent 2 selection:
      - rule_based_prob > 0: Shipping Rush bot with that probability
      - otherwise: random draw from opponent_pool
      - fallback (empty pool, rule_based_prob=0): latest agent
    """
    env = PuertoRicoEnv(num_players=NUM_PLAYERS, max_game_steps=max_game_steps, use_pbrs=True)
    obs_space = env.observation_space(env.possible_agents[0])["observation"]

    local_agent       = Agent(obs_dim=obs_dim, action_dim=action_dim)
    local_old_opp     = Agent(obs_dim=obs_dim, action_dim=action_dim)
    # Always Shipping Rush — proven above-random; Fusion was sub-random
    local_rule_based  = ShippingRushAgent(action_dim=action_dim, fixed_strategy=0)

    local_agent.eval()
    local_old_opp.eval()
    local_rule_based.eval()

    s_obs, s_mask, s_act, s_logp, s_rew, s_done, s_val, s_next_val = shared_bufs

    env_initialized    = False
    agent_generator    = None
    agent_name         = None
    learning_player_idx = 0
    opp1_idx = 1
    opp2_idx = 2
    use_rule_based     = False
    use_latest_as_opp2 = False

    def _select_opp2():
        """Determine opp2 strategy for the upcoming game."""
        nonlocal use_rule_based, use_latest_as_opp2
        if opponent_pool and random.random() >= rule_based_prob:
            use_rule_based     = False
            use_latest_as_opp2 = False
            local_old_opp.load_state_dict(random.choice(opponent_pool))
        elif rule_based_prob > 0:
            use_rule_based     = True
            use_latest_as_opp2 = False
            local_rule_based.reset_strategy()
        else:
            # Pure self-play with empty pool: fall back to latest agent
            use_rule_based     = False
            use_latest_as_opp2 = True

    while True:
        cmd, data = conn.recv()

        if cmd == CMD_SET_WEIGHTS:
            local_agent.load_state_dict(data)
            continue
        elif cmd == CMD_CLOSE:
            break
        elif cmd == CMD_STEP:
            if not env_initialized:
                env.reset()
                agent_generator = iter(env.agent_iter())
                indices = list(range(NUM_PLAYERS))
                random.shuffle(indices)
                learning_player_idx, opp1_idx, opp2_idx = indices
                _select_opp2()
                agent_name = None
                env_initialized = True

            stats = {
                "games": 0, "wins": 0, "total_score": 0.0,
                "vp_chips": 0.0, "building_vp": 0.0,
                "role_counts": np.zeros(8),
                "building_counts": np.zeros(23),
                "end_reason_shipping": 0,
                "end_reason_building": 0,
                "end_reason_colonists": 0,
            }
            step_idx = 0

            while True:
                # ── Advance to next agent turn ──────────────────────────
                if agent_name is None:
                    try:
                        agent_name = next(agent_generator)
                    except StopIteration:
                        # Game finished — collect stats
                        stats["games"] += 1
                        final_scores = env.game.get_scores()
                        learner_score = final_scores[learning_player_idx][0]
                        stats["total_score"] += learner_score
                        max_opp = max(
                            final_scores[j][0]
                            for j in range(NUM_PLAYERS)
                            if j != learning_player_idx
                        )
                        if learner_score >= max_opp:
                            stats["wins"] += 1
                        p_obj = env.game.players[learning_player_idx]
                        stats["vp_chips"]    += p_obj.vp_chips
                        stats["building_vp"] += learner_score - p_obj.vp_chips
                        for b in p_obj.city_board:
                            if b.building_type.value < 23:
                                stats["building_counts"][b.building_type.value] += 1
                        if env.game.vp_chips <= 0:
                            stats["end_reason_shipping"] += 1
                        elif any(p.empty_city_spaces == 0 for p in env.game.players):
                            stats["end_reason_building"] += 1
                        elif getattr(env.game, '_colonists_ship_underfilled', False):
                            stats["end_reason_colonists"] += 1

                        # Reset for next game
                        env.reset()
                        agent_generator = iter(env.agent_iter())
                        indices = list(range(NUM_PLAYERS))
                        random.shuffle(indices)
                        learning_player_idx, opp1_idx, opp2_idx = indices
                        _select_opp2()
                        agent_name = next(agent_generator)

                # ── Observe & act ───────────────────────────────────────
                obs, reward, termination, truncation, info = env.last()
                p_idx = int(agent_name.split("_")[1])
                is_learner = (p_idx == learning_player_idx)

                if termination or truncation:
                    if is_learner:
                        if step_idx > 0:
                            s_rew[rank, step_idx - 1] = reward
                            s_done[rank, step_idx - 1] = 1.0
                        if step_idx == steps_per_env:
                            s_next_val[rank] = 0.0
                            conn.send({"stats": stats})
                            break
                    env.step(None)
                    agent_name = None
                    continue

                if is_learner:
                    if step_idx > 0:
                        s_rew[rank, step_idx - 1] = reward
                        s_done[rank, step_idx - 1] = 0.0

                    flat_obs = flatten_dict_observation(obs["observation"], obs_space)
                    mask     = obs["action_mask"]
                    obs_t    = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
                    mask_t   = torch.as_tensor(mask,    dtype=torch.float32).unsqueeze(0)

                    if step_idx == steps_per_env:
                        with torch.no_grad():
                            _, _, _, val = local_agent.get_action_and_value(obs_t, mask_t)
                        s_next_val[rank] = val.item()
                        conn.send({"stats": stats})
                        break

                    with torch.no_grad():
                        action, logp, _, val = local_agent.get_action_and_value(obs_t, mask_t)

                    s_obs[rank, step_idx]  = torch.from_numpy(flat_obs)
                    s_mask[rank, step_idx] = torch.from_numpy(mask)
                    s_act[rank, step_idx]  = action.item()
                    s_logp[rank, step_idx] = logp.item()
                    s_val[rank, step_idx]  = val.item()

                    try:
                        if action.item() < 8 and mask[action.item()] == 1:
                            stats["role_counts"][action.item()] += 1
                    except Exception:
                        pass

                    env.step(action.item())
                    agent_name = None
                    step_idx  += 1

                else:
                    # Opponent turn
                    obs_dict = obs["observation"]
                    flat_obs = flatten_dict_observation(obs_dict, obs_space)
                    mask     = obs["action_mask"]
                    obs_t    = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
                    mask_t   = torch.as_tensor(mask,    dtype=torch.float32).unsqueeze(0)

                    if p_idx == opp1_idx:
                        # opp1: always latest agent
                        with torch.no_grad():
                            action, _, _, _ = local_agent.get_action_and_value(obs_t, mask_t)
                    else:
                        # opp2: rule-based | past-self | latest-self
                        if use_rule_based:
                            with torch.no_grad():
                                action, _, _, _ = local_rule_based.get_action_and_value(
                                    obs_t, mask_t, obs_dict=obs_dict, player_idx=p_idx
                                )
                        elif use_latest_as_opp2:
                            with torch.no_grad():
                                action, _, _, _ = local_agent.get_action_and_value(obs_t, mask_t)
                        else:
                            with torch.no_grad():
                                action, _, _, _ = local_old_opp.get_action_and_value(obs_t, mask_t)

                    env.step(action.item())
                    agent_name = None


# ── Training entry point ──────────────────────────────────────────────────────
def train():
    parser = argparse.ArgumentParser(
        description="Puerto Rico PPO Self-Play Trainer",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--run_prefix", type=str, default="self_play",
        help="Human-readable prefix for this experiment run"
    )
    parser.add_argument(
        "--rule_based_prob", type=float, default=0.0,
        help=(
            "Probability that opp2 is a Shipping Rush rule-based bot. "
            "0.0 = pure self-play (recommended). "
            "Only Shipping Rush (strategy=0) is used — Fusion was sub-random."
        )
    )
    parser.add_argument(
        "--load_ckpt", type=str, default="",
        help="Path to an existing .pth checkpoint to resume/finetune from."
    )
    parser.add_argument(
        "--local_smoke", action="store_true",
        help="M1/로컬 smoke 검증용으로 매우 작은 batch/update 설정을 사용한다."
    )
    parser.add_argument("--num_envs", type=int, default=None)
    parser.add_argument("--steps_per_env", type=int, default=None)
    parser.add_argument("--minibatch_size", type=int, default=None)
    parser.add_argument("--update_epochs", type=int, default=None)
    parser.add_argument("--total_timesteps", type=int, default=None)
    parser.add_argument("--snapshot_interval", type=int, default=None)
    parser.add_argument("--opponent_pool_size", type=int, default=None)
    parser.add_argument("--max_game_steps", type=int, default=None)
    parser.add_argument(
        "--write_bundle", action=argparse.BooleanOptionalAction, default=True,
        help="Snapshot마다 .pth 옆에 web 서빙용 bundle directory(manifest+checkpoint)를 함께 작성한다."
    )
    args = parser.parse_args()
    runtime = resolve_runtime_config(args)

    try:
        mp.set_start_method('spawn', force=True)
    except RuntimeError:
        pass

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    run_name = f"PPO_PR_Server_{args.run_prefix}_{time.strftime('%Y%m%d_%H%M%S')}"

    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "runs", run_name
    )
    os.makedirs(log_dir, exist_ok=True)
    writer = SummaryWriter(log_dir) if SummaryWriter is not None else NoOpSummaryWriter()
    if SummaryWriter is None:
        print("[Runtime] tensorboard not installed; metrics will not be written to event files.")

    # Save experiment config immediately — no manual note-taking needed
    save_experiment_config(run_name, log_dir, args, runtime)
    print(
        "[Runtime] num_envs={num_envs} steps_per_env={steps_per_env} "
        "batch_size={batch_size} updates={updates} snapshot_interval={snapshot_interval}".format(
            num_envs=runtime["num_envs"],
            steps_per_env=runtime["steps_per_env"],
            batch_size=runtime["batch_size"],
            updates=runtime["total_timesteps"] // runtime["batch_size"],
            snapshot_interval=runtime["snapshot_interval"],
        )
    )
    print(f"[Runtime] worker_mode={'threads' if runtime['use_threads'] else 'processes'}")

    # Environment metadata
    temp_env   = PuertoRicoEnv(num_players=NUM_PLAYERS, max_game_steps=runtime["max_game_steps"])
    obs_dim    = get_flattened_obs_dim(temp_env.observation_space(temp_env.possible_agents[0])["observation"])
    action_dim = temp_env.action_space(temp_env.possible_agents[0]).n
    del temp_env

    # Shared memory buffers (zero-copy IPC)
    shared_bufs = (
        torch.zeros((runtime["num_envs"], runtime["steps_per_env"], obs_dim)).share_memory_(),
        torch.zeros((runtime["num_envs"], runtime["steps_per_env"], action_dim)).share_memory_(),
        torch.zeros((runtime["num_envs"], runtime["steps_per_env"])).share_memory_(),
        torch.zeros((runtime["num_envs"], runtime["steps_per_env"])).share_memory_(),
        torch.zeros((runtime["num_envs"], runtime["steps_per_env"])).share_memory_(),
        torch.zeros((runtime["num_envs"], runtime["steps_per_env"])).share_memory_(),
        torch.zeros((runtime["num_envs"], runtime["steps_per_env"])).share_memory_(),
        torch.zeros(runtime["num_envs"]).share_memory_(),
    )

    agent     = Agent(obs_dim=obs_dim, action_dim=action_dim).to(device)
    
    if args.load_ckpt:
        print(f"[Init] Loading weights from {args.load_ckpt} ...")
        agent.load_state_dict(torch.load(args.load_ckpt, map_location=device, weights_only=True))

    optimizer = optim.Adam(agent.parameters(), lr=LEARNING_RATE, eps=1e-5)

    opponent_pool = [] if runtime["use_threads"] else mp.Manager().list()
    processes, conns = [], []
    for i in range(runtime["num_envs"]):
        parent_conn, child_conn = mp.Pipe()
        worker_kwargs = {
            "target": rollout_worker,
            "args": (
                i, child_conn, shared_bufs, obs_dim, action_dim,
                opponent_pool, args.rule_based_prob,
                runtime["steps_per_env"], runtime["max_game_steps"],
            ),
        }
        if runtime["use_threads"]:
            p = threading.Thread(**worker_kwargs, daemon=True)
        else:
            p = mp.Process(**worker_kwargs)
        p.start()
        processes.append(p)
        conns.append(parent_conn)

    global_step  = 0
    batch_size = runtime["batch_size"]
    total_updates = runtime["total_timesteps"] // batch_size
    train_start   = time.time()

    try:
        for update in range(1, total_updates + 1):
            # Annealed LR and entropy coef
            frac = 1.0 - (update - 1.0) / total_updates
            optimizer.param_groups[0]["lr"] = max(1e-5, frac * LEARNING_RATE)
            current_ent_coef = max(MIN_ENT_COEF, INITIAL_ENT_COEF * frac)

            # Broadcast latest weights and request rollouts
            shared_weights = {k: v.cpu() for k, v in agent.state_dict().items()}
            for conn in conns:
                conn.send((CMD_SET_WEIGHTS, shared_weights))
                conn.send((CMD_STEP, None))

            results = [conn.recv() for conn in conns]

            obs_b, mask_b, act_b, logp_b, rew_b, done_b, val_b, next_val_arr = [
                b.clone() for b in shared_bufs
            ]

            # GAE
            advantages   = torch.zeros_like(rew_b)
            lastgaelam   = 0
            for t in reversed(range(runtime["steps_per_env"])):
                nextnonterminal = 1.0 - done_b[:, t]
                nextvalues      = next_val_arr if t == runtime["steps_per_env"] - 1 else val_b[:, t + 1]
                delta = rew_b[:, t] + GAMMA * nextvalues * nextnonterminal - val_b[:, t]
                advantages[:, t] = lastgaelam = delta + GAMMA * GAE_LAMBDA * nextnonterminal * lastgaelam
            returns_b = advantages + val_b

            obs_t  = obs_b.reshape(-1, obs_dim).to(device)
            mask_t = mask_b.reshape(-1, action_dim).to(device)
            act_t  = act_b.reshape(-1).to(device)
            logp_t = logp_b.reshape(-1).to(device)
            adv_t  = advantages.reshape(-1).to(device)
            ret_t  = returns_b.reshape(-1).to(device)

            losses_pg, losses_v, losses_ent = [], [], []
            b_inds = np.arange(batch_size)
            for epoch in range(runtime["update_epochs"]):
                np.random.shuffle(b_inds)
                for start in range(0, batch_size, runtime["minibatch_size"]):
                    mb = b_inds[start:start + runtime["minibatch_size"]]
                    _, newlogp, entropy, newval = agent.get_action_and_value(
                        obs_t[mb], mask_t[mb], act_t[mb]
                    )
                    ratio   = (newlogp - logp_t[mb]).exp()
                    mb_adv  = (adv_t[mb] - adv_t[mb].mean()) / (adv_t[mb].std() + 1e-8)
                    pg_loss = torch.max(
                        -mb_adv * ratio,
                        -mb_adv * torch.clamp(ratio, 1 - CLIP_COEF, 1 + CLIP_COEF)
                    ).mean()
                    v_loss  = 0.5 * ((newval.view(-1) - ret_t[mb]) ** 2).mean()
                    loss    = pg_loss - current_ent_coef * entropy.mean() + v_loss * VF_COEF

                    optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(agent.parameters(), MAX_GRAD_NORM)
                    optimizer.step()

                    losses_pg.append(pg_loss.item())
                    losses_v.append(v_loss.item())
                    losses_ent.append(entropy.mean().item())

            global_step += batch_size
            total_games  = sum(r["stats"]["games"] for r in results)

            # TensorBoard logging
            writer.add_scalar("Loss/PolicyLoss",  np.mean(losses_pg),  global_step)
            writer.add_scalar("Loss/ValueLoss",   np.mean(losses_v),   global_step)
            writer.add_scalar("Loss/Entropy",     np.mean(losses_ent), global_step)
            writer.add_scalar("Hyperparameters/Ent_Coef", current_ent_coef, global_step)
            writer.add_scalar("Hyperparameters/LR", optimizer.param_groups[0]["lr"], global_step)

            if total_games > 0:
                writer.add_scalar("Performance/WinRate",
                                  sum(r["stats"]["wins"] for r in results) / total_games, global_step)
                writer.add_scalar("Strategy/VP_Shipping",
                                  sum(r["stats"]["vp_chips"] for r in results) / total_games, global_step)
                writer.add_scalar("Strategy/VP_Building",
                                  sum(r["stats"]["building_vp"] for r in results) / total_games, global_step)
                writer.add_scalar("End_Reason/Shipping_Limit",
                                  sum(r["stats"]["end_reason_shipping"] for r in results) / total_games, global_step)
                writer.add_scalar("End_Reason/Building_Full",
                                  sum(r["stats"]["end_reason_building"] for r in results) / total_games, global_step)
                writer.add_scalar("End_Reason/Colonist_Empty",
                                  sum(r["stats"]["end_reason_colonists"] for r in results) / total_games, global_step)

                bldg_dist = np.sum([r["stats"]["building_counts"] for r in results], axis=0)
                for i in range(0, 6):
                    writer.add_scalar(f"Buildings_Production/{BuildingType(i).name}", bldg_dist[i] / total_games, global_step)
                for i in range(6, 18):
                    writer.add_scalar(f"Buildings_Commercial/{BuildingType(i).name}", bldg_dist[i] / total_games, global_step)
                for i in range(18, 23):
                    writer.add_scalar(f"Buildings_Large/{BuildingType(i).name}",      bldg_dist[i] / total_games, global_step)
                for i in range(8):
                    writer.add_scalar(f"Role_Selection/{Role(i).name}",
                                      sum(r["stats"]["role_counts"][i] for r in results) / total_games, global_step)

            # Terminal progress
            elapsed = time.time() - train_start
            fps     = global_step / elapsed if elapsed > 0 else 1
            eta_remaining = max(0, runtime["total_timesteps"] - global_step)
            eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_remaining / fps))
            print(f"[Update {update}/{total_updates}] Step {global_step:,} | FPS {int(fps):,} | ETA {eta_str}")
            if total_games > 0:
                win_rate = sum(r["stats"]["wins"] for r in results) / total_games
                print(f" └─ WinRate: {win_rate:.2f} | Loss(P/V/E): "
                      f"{np.mean(losses_pg):.3f}/{np.mean(losses_v):.3f}/{np.mean(losses_ent):.3f}\n")

            if update % runtime["snapshot_interval"] == 0:
                opponent_pool.append(copy.deepcopy(shared_weights))
                if len(opponent_pool) > runtime["opponent_pool_size"]:
                    opponent_pool.pop(0)
                ckpt_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "models", "ppo_checkpoints", args.run_prefix
                )
                os.makedirs(ckpt_dir, exist_ok=True)
                ckpt_path = os.path.join(ckpt_dir, f"{run_name}_step_{global_step}.pth")
                torch.save(agent.state_dict(), ckpt_path)

                if args.write_bundle:
                    bundle_id = f"{run_name}_step_{global_step}"
                    bundle_dir = os.path.join(ckpt_dir, f"{bundle_id}_bundle")
                    try:
                        write_bundle(
                            output_dir=bundle_dir,
                            checkpoint_path=ckpt_path,
                            bundle_id=bundle_id,
                            obs_dim=int(obs_dim),
                            action_dim=int(action_dim),
                            num_players=int(NUM_PLAYERS),
                            extra_metadata={
                                "trainer": "train_ppo_selfplay_server",
                                "training_run": run_name,
                                "training_step": int(global_step),
                            },
                        )
                        print(f"[Bundle] Wrote → {bundle_dir}")
                    except Exception as exc:  # noqa: BLE001
                        print(f"[Bundle] WARN: write_bundle failed: {exc}")

    finally:
        for conn in conns:
            conn.send((CMD_CLOSE, None))
        for p in processes:
            p.join()
        writer.close()


if __name__ == "__main__":
    train()
