import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
import json
import copy
import time
import random
import subprocess
import argparse

import torch
import torch.nn as nn
import torch.optim as optim
import torch.multiprocessing as mp
import numpy as np
from torch.utils.tensorboard import SummaryWriter

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
from agents.ppo_agent import Agent
from agents.shipping_rush_agent import ShippingRushAgent
from agents.action_value_agent import ActionValueAgent
from configs.constants import Role, BuildingType

# ── 하이퍼파라미터 ─────────────────────────────────────────────────────────────
NUM_PLAYERS = 3
TOTAL_TRAJECTORIES = 192
PURE_WORKERS = 48
HYBRID_WORKERS = 48
NUM_WORKERS = PURE_WORKERS + HYBRID_WORKERS
STEPS_PER_ENV = 1024
BATCH_SIZE = TOTAL_TRAJECTORIES * STEPS_PER_ENV
MINIBATCH_SIZE = 8192
UPDATE_EPOCHS = 10
LEARNING_RATE = 3e-4
GAMMA = 0.99
GAE_LAMBDA = 0.95
CLIP_COEF = 0.2
INITIAL_ENT_COEF = 0.05
MIN_ENT_COEF = 0.015
VF_COEF = 0.5
MAX_GRAD_NORM = 0.5

TOTAL_TIMESTEPS = 500_000_000
SNAPSHOT_INTERVAL = 25
OPPONENT_POOL_SIZE = 50

# Pipe command constants
CMD_STEP = 0
CMD_SET_WEIGHTS = 1
CMD_CLOSE = 2


# ── Experiment config saver ───────────────────────────────────────────────────
def save_experiment_config(run_name: str, log_dir: str, args: argparse.Namespace) -> None:
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

    if args.rule_based_prob_start > 0 or args.rule_based_prob_end > 0:
        selfplay_type = "league"
        selfplay_desc = (
            f"Heuristic bot Dynamic Curriculum "
            f"({args.rule_based_prob_start:.2f} -> {args.rule_based_prob_end:.2f}); "
            f"past-self with remaining prob"
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
            "max_game_steps": 1200,
        },

        "hyperparameters": {
            "num_trajectories": TOTAL_TRAJECTORIES,
            "steps_per_env": STEPS_PER_ENV,
            "total_timesteps": TOTAL_TIMESTEPS,
            "batch_size": BATCH_SIZE,
            "minibatch_size": MINIBATCH_SIZE,
            "update_epochs": UPDATE_EPOCHS,
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
            "snapshot_interval_updates": SNAPSHOT_INTERVAL,
            "opponent_pool_size": OPPONENT_POOL_SIZE,
            "rule_based_prob_start": args.rule_based_prob_start,
            "rule_based_prob_end": args.rule_based_prob_end,
            "rule_based_strategy": "Shipping 50% / ActionValue 50%" if args.rule_based_prob_end > 0 else "none",
            "opp1_role": "latest_agent (always)",
            "opp2_role": (
                f"dynamic heuristic | pool past-self (exponential PFSP weights)"
                if args.rule_based_prob_end > 0
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
    if args.rule_based_prob_start > 0 or args.rule_based_prob_end > 0:
        print(f"[Config] Rule-based prob: {args.rule_based_prob_start:.2f} -> {args.rule_based_prob_end:.2f}")


# ── Rollout worker ────────────────────────────────────────────────────────────
def rollout_worker(worker_id, buffer_indices, worker_type, conn, shared_bufs, obs_dim, action_dim,
                   opponent_pool, shared_rule_prob):
    """
    Persistent worker process.
    PBRS is always enabled (no flag needed).
    Opponent 2 selection:
      - dynamic prob: Heuristic bot with shared_rule_prob
      - otherwise: PFSP exponential draw from opponent_pool
      - fallback (empty pool, rule_based_prob=0): latest agent
    """
    env = PuertoRicoEnv(num_players=NUM_PLAYERS, max_game_steps=1200, use_pbrs=True)
    obs_space = env.observation_space(env.possible_agents[0])["observation"]

    local_agent       = Agent(obs_dim=obs_dim, action_dim=action_dim)
    local_old_opp     = Agent(obs_dim=obs_dim, action_dim=action_dim)
    local_shipping    = ShippingRushAgent(action_dim=action_dim, fixed_strategy=0)
    local_action_val  = ActionValueAgent(action_dim=action_dim)
    local_action_val.set_env(env)

    local_agent.eval()
    local_old_opp.eval()
    local_shipping.eval()
    local_action_val.eval()

    s_obs, s_mask, s_act, s_logp, s_rew, s_done, s_val, s_next_val = shared_bufs

    env_initialized    = False
    agent_generator    = None
    agent_name         = None
    learning_player_idx = 0
    opp1_idx = 1
    opp2_idx = 2
    active_rule_based  = None
    use_rule_based     = False
    use_latest_as_opp2 = False

    def _select_opp2():
        """Determine opp2 strategy for the upcoming game."""
        nonlocal use_rule_based, use_latest_as_opp2, active_rule_based
        
        current_prob = shared_rule_prob.value
        
        if opponent_pool and random.random() >= current_prob:
            use_rule_based     = False
            use_latest_as_opp2 = False
            n = len(opponent_pool)
            # Prioritized Fictitious Self-Play (PFSP) with exponential weight
            alpha = 3.0
            weights = np.exp(alpha * np.arange(n) / max(1, n - 1))
            weights = weights / weights.sum()
            idx = np.random.choice(n, p=weights)
            local_old_opp.load_state_dict(opponent_pool[idx])
        elif current_prob > 0:
            use_rule_based     = True
            use_latest_as_opp2 = False
            if random.random() < 0.5:
                active_rule_based = local_shipping
                active_rule_based.reset_strategy()
            else:
                active_rule_based = local_action_val
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
                if worker_type == "pure":
                    learning_players = [0, 1, 2]
                    traj_mapping = {0: buffer_indices[0], 1: buffer_indices[1], 2: buffer_indices[2]}
                else:
                    indices = list(range(NUM_PLAYERS))
                    random.shuffle(indices)
                    learning_players = [indices[0]]
                    traj_mapping = {indices[0]: buffer_indices[0]}
                    opp1_idx, opp2_idx = indices[1], indices[2]
                    _select_opp2()
                agent_name = None
                env_initialized = True

            stats = {
                "games": 0, "agent_games": 0, "wins": 0, "total_score": 0.0,
                "vp_chips": 0.0, "building_vp": 0.0,
                "role_counts": np.zeros(8),
                "building_counts": np.zeros(23),
                "end_reason_shipping": 0,
                "end_reason_building": 0,
                "end_reason_colonists": 0,
            }
            step_idx_array = {b_id: 0 for b_id in buffer_indices}
            finished_buffers = 0

            while True:
                # ── Advance to next agent turn ──────────────────────────
                if agent_name is None:
                    try:
                        agent_name = next(agent_generator)
                    except StopIteration:
                        # Game finished — collect stats
                        stats["games"] += 1
                        stats["agent_games"] += len(learning_players)
                        final_scores = env.game.get_scores()
                        for p_idx in learning_players:
                            learner_score = final_scores[p_idx][0]
                            stats["total_score"] += learner_score
                            max_opp = max(final_scores[j][0] for j in range(NUM_PLAYERS) if j != p_idx)
                            if learner_score >= max_opp:
                                stats["wins"] += 1
                            p_obj = env.game.players[p_idx]
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
                        if worker_type == "pure":
                            learning_players = [0, 1, 2]
                            traj_mapping = {0: buffer_indices[0], 1: buffer_indices[1], 2: buffer_indices[2]}
                        else:
                            indices = list(range(NUM_PLAYERS))
                            random.shuffle(indices)
                            learning_players = [indices[0]]
                            traj_mapping = {indices[0]: buffer_indices[0]}
                            opp1_idx, opp2_idx = indices[1], indices[2]
                            _select_opp2()
                        agent_name = next(agent_generator)

                # ── Observe & act ───────────────────────────────────────
                obs, reward, termination, truncation, info = env.last()
                p_idx = int(agent_name.split("_")[1])
                is_learner = (p_idx in learning_players)
                
                b_idx = traj_mapping.get(p_idx, -1)
                s_idx = step_idx_array.get(b_idx, -1)

                if termination or truncation:
                    if is_learner and s_idx != -1 and s_idx <= STEPS_PER_ENV:
                        if s_idx > 0:
                            s_rew[b_idx, s_idx - 1] = reward
                            s_done[b_idx, s_idx - 1] = 1.0
                        if s_idx == STEPS_PER_ENV:
                            s_next_val[b_idx] = 0.0
                            finished_buffers += 1
                            step_idx_array[b_idx] = STEPS_PER_ENV + 1 # prevent triggering again
                            if finished_buffers == len(buffer_indices):
                                conn.send({"stats": stats})
                                break
                    env.step(None)
                    agent_name = None
                    continue

                if is_learner and s_idx != -1 and s_idx <= STEPS_PER_ENV:
                    if s_idx > 0:
                        s_rew[b_idx, s_idx - 1] = reward
                        s_done[b_idx, s_idx - 1] = 0.0

                    flat_obs = flatten_dict_observation(obs["observation"], obs_space)
                    mask     = obs["action_mask"]
                    obs_t    = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
                    mask_t   = torch.as_tensor(mask,    dtype=torch.float32).unsqueeze(0)

                    if s_idx == STEPS_PER_ENV:
                        with torch.no_grad():
                            _, _, _, val = local_agent.get_action_and_value(obs_t, mask_t)
                        s_next_val[b_idx] = val.item()
                        finished_buffers += 1
                        step_idx_array[b_idx] = STEPS_PER_ENV + 1
                        if finished_buffers == len(buffer_indices):
                            conn.send({"stats": stats})
                            break
                        # If not all buffers finished, this agent must still act to advance game
                        with torch.no_grad():
                            action, _, _, _ = local_agent.get_action_and_value(obs_t, mask_t)
                        env.step(action.item())
                        agent_name = None
                        continue

                    # normal collection step
                    with torch.no_grad():
                        action, logp, _, val = local_agent.get_action_and_value(obs_t, mask_t)
                    
                    s_obs[b_idx, s_idx]  = torch.from_numpy(flat_obs)
                    s_mask[b_idx, s_idx] = torch.from_numpy(mask)
                    s_act[b_idx, s_idx]  = action.item()
                    s_logp[b_idx, s_idx] = logp.item()
                    s_val[b_idx, s_idx]  = val.item()

                    try:
                        if action.item() < 8 and mask[action.item()] == 1:
                            stats["role_counts"][action.item()] += 1
                    except Exception:
                        pass

                    env.step(action.item())
                    agent_name = None
                    step_idx_array[b_idx] += 1

                else:
                    # Opponent turn (or Learner turn past STEPS_PER_ENV waiting for others)
                    obs_dict = obs["observation"]
                    flat_obs = flatten_dict_observation(obs_dict, obs_space)
                    mask     = obs["action_mask"]
                    obs_t    = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
                    mask_t   = torch.as_tensor(mask,    dtype=torch.float32).unsqueeze(0)

                    if worker_type == "pure":
                        # In pure mode, if it's an opponent turn, it means it's a learner that has already hit STEPS_PER_ENV
                        with torch.no_grad():
                            action, _, _, _ = local_agent.get_action_and_value(obs_t, mask_t)
                    else:
                        if p_idx == opp1_idx:
                            # opp1: always latest agent
                            with torch.no_grad():
                                action, _, _, _ = local_agent.get_action_and_value(obs_t, mask_t)
                        else:
                            # opp2: rule-based | past-self | latest-self
                            if use_rule_based:
                                with torch.no_grad():
                                    action, _, _, _ = active_rule_based.get_action_and_value(
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
        "--rule_based_prob_start", type=float, default=0.1,
        help="Initial probability that opp2 is a heuristic bot (ShippingRush or ActionValue)."
    )
    parser.add_argument(
        "--rule_based_prob_end", type=float, default=0.4,
        help="Final probability that opp2 is a heuristic bot at the end of training."
    )
    parser.add_argument(
        "--load_ckpt", type=str, default="",
        help="Path to an existing .pth checkpoint to resume/finetune from."
    )
    args = parser.parse_args()

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
    writer = SummaryWriter(log_dir)

    # Save experiment config immediately — no manual note-taking needed
    save_experiment_config(run_name, log_dir, args)

    # Environment metadata
    temp_env   = PuertoRicoEnv(num_players=NUM_PLAYERS)
    obs_dim    = get_flattened_obs_dim(temp_env.observation_space(temp_env.possible_agents[0])["observation"])
    action_dim = temp_env.action_space(temp_env.possible_agents[0]).n
    del temp_env

    # Shared memory buffers (zero-copy IPC)
    shared_bufs = (
        torch.zeros((TOTAL_TRAJECTORIES, STEPS_PER_ENV, obs_dim)).share_memory_(),
        torch.zeros((TOTAL_TRAJECTORIES, STEPS_PER_ENV, action_dim)).share_memory_(),
        torch.zeros((TOTAL_TRAJECTORIES, STEPS_PER_ENV)).share_memory_(),
        torch.zeros((TOTAL_TRAJECTORIES, STEPS_PER_ENV)).share_memory_(),
        torch.zeros((TOTAL_TRAJECTORIES, STEPS_PER_ENV)).share_memory_(),
        torch.zeros((TOTAL_TRAJECTORIES, STEPS_PER_ENV)).share_memory_(),
        torch.zeros((TOTAL_TRAJECTORIES, STEPS_PER_ENV)).share_memory_(),
        torch.zeros(TOTAL_TRAJECTORIES).share_memory_(),
    )

    agent     = Agent(obs_dim=obs_dim, action_dim=action_dim).to(device)
    
    if args.load_ckpt:
        print(f"[Init] Loading weights from {args.load_ckpt} ...")
        agent.load_state_dict(torch.load(args.load_ckpt, map_location=device, weights_only=True))

    optimizer = optim.Adam(agent.parameters(), lr=LEARNING_RATE, eps=1e-5)

    opponent_pool = mp.Manager().list()
    shared_rule_prob = mp.Value('d', args.rule_based_prob_start)
    processes, conns = [], []
    for i in range(NUM_WORKERS):
        parent_conn, child_conn = mp.Pipe()
        if i < PURE_WORKERS:
            worker_type = "pure"
            b_idx_list = [i * 3, i * 3 + 1, i * 3 + 2]
        else:
            worker_type = "hybrid"
            base_offset = PURE_WORKERS * 3
            b_idx_list = [base_offset + (i - PURE_WORKERS)]
            
        p = mp.Process(
            target=rollout_worker,
            args=(i, b_idx_list, worker_type, child_conn, shared_bufs, obs_dim, action_dim,
                  opponent_pool, shared_rule_prob)
        )
        p.start()
        processes.append(p)
        conns.append(parent_conn)

    global_step  = 0
    total_updates = TOTAL_TIMESTEPS // BATCH_SIZE
    train_start   = time.time()

    try:
        for update in range(1, total_updates + 1):
            # Annealed LR, entropy coef, and rule based prob
            frac = 1.0 - (update - 1.0) / total_updates
            optimizer.param_groups[0]["lr"] = max(1e-5, frac * LEARNING_RATE)
            current_ent_coef = max(MIN_ENT_COEF, INITIAL_ENT_COEF * frac)
            
            # Dynamic Curriculum update
            current_rule_prob = args.rule_based_prob_end + frac * (args.rule_based_prob_start - args.rule_based_prob_end)
            shared_rule_prob.value = current_rule_prob

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
            for t in reversed(range(STEPS_PER_ENV)):
                nextnonterminal = 1.0 - done_b[:, t]
                nextvalues      = next_val_arr if t == STEPS_PER_ENV - 1 else val_b[:, t + 1]
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
            b_inds = np.arange(BATCH_SIZE)
            for epoch in range(UPDATE_EPOCHS):
                np.random.shuffle(b_inds)
                for start in range(0, BATCH_SIZE, MINIBATCH_SIZE):
                    mb = b_inds[start:start + MINIBATCH_SIZE]
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

            global_step += BATCH_SIZE
            total_games  = sum(r["stats"]["games"] for r in results)
            total_agent_games = sum(r["stats"]["agent_games"] for r in results)

            # TensorBoard logging
            writer.add_scalar("Loss/PolicyLoss",  np.mean(losses_pg),  global_step)
            writer.add_scalar("Loss/ValueLoss",   np.mean(losses_v),   global_step)
            writer.add_scalar("Loss/Entropy",     np.mean(losses_ent), global_step)
            writer.add_scalar("Hyperparameters/Ent_Coef", current_ent_coef, global_step)
            writer.add_scalar("Hyperparameters/LR", optimizer.param_groups[0]["lr"], global_step)
            writer.add_scalar("Hyperparameters/Rule_Based_Prob", current_rule_prob, global_step)

            if total_agent_games > 0:
                writer.add_scalar("Performance/WinRate",
                                  sum(r["stats"]["wins"] for r in results) / total_agent_games, global_step)
                writer.add_scalar("Strategy/VP_Shipping",
                                  sum(r["stats"]["vp_chips"] for r in results) / total_agent_games, global_step)
                writer.add_scalar("Strategy/VP_Building",
                                  sum(r["stats"]["building_vp"] for r in results) / total_agent_games, global_step)

            if total_games > 0:
                writer.add_scalar("End_Reason/Shipping_Limit",
                                  sum(r["stats"]["end_reason_shipping"] for r in results) / total_games, global_step)
                writer.add_scalar("End_Reason/Building_Full",
                                  sum(r["stats"]["end_reason_building"] for r in results) / total_games, global_step)
                writer.add_scalar("End_Reason/Colonist_Empty",
                                  sum(r["stats"]["end_reason_colonists"] for r in results) / total_games, global_step)

            if total_agent_games > 0:
                bldg_dist = np.sum([r["stats"]["building_counts"] for r in results], axis=0) / total_agent_games
                for i in range(0, 6):
                    writer.add_scalar(f"Buildings_Production/{BuildingType(i).name}", bldg_dist[i], global_step)
                for i in range(6, 18):
                    writer.add_scalar(f"Buildings_Commercial/{BuildingType(i).name}", bldg_dist[i], global_step)
                for i in range(18, 23):
                    writer.add_scalar(f"Buildings_Large/{BuildingType(i).name}",      bldg_dist[i], global_step)
                for i in range(8):
                    writer.add_scalar(f"Role_Selection/{Role(i).name}",
                                      sum(r["stats"]["role_counts"][i] for r in results) / total_agent_games, global_step)

            # Terminal progress
            elapsed = time.time() - train_start
            fps     = global_step / elapsed if elapsed > 0 else 1
            eta_str = time.strftime("%H:%M:%S", time.gmtime((TOTAL_TIMESTEPS - global_step) / fps))
            print(f"[Update {update}/{total_updates}] Step {global_step:,} | FPS {int(fps):,} | ETA {eta_str}")
            if total_games > 0:
                win_rate = sum(r["stats"]["wins"] for r in results) / total_games
                print(f" └─ WinRate: {win_rate:.2f} | Loss(P/V/E): "
                      f"{np.mean(losses_pg):.3f}/{np.mean(losses_v):.3f}/{np.mean(losses_ent):.3f}\n")

            if update % SNAPSHOT_INTERVAL == 0:
                opponent_pool.append(copy.deepcopy(shared_weights))
                if len(opponent_pool) > OPPONENT_POOL_SIZE:
                    opponent_pool.pop(0)
                ckpt_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "models", "ppo_checkpoints", args.run_prefix
                )
                os.makedirs(ckpt_dir, exist_ok=True)
                torch.save(agent.state_dict(),
                           os.path.join(ckpt_dir, f"{run_name}_step_{global_step}.pth"))

    finally:
        for conn in conns:
            conn.send((CMD_CLOSE, None))
        for p in processes:
            p.join()
        writer.close()


if __name__ == "__main__":
    train()