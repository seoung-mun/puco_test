import os
import copy
import time
import random
import torch
import torch.nn as nn
import torch.optim as optim
import torch.multiprocessing as mp
import numpy as np
from torch.utils.tensorboard import SummaryWriter
from collections import defaultdict

# Project modules
from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
from agents.ppo_agent import PhasePPOAgent, PHASE_TO_HEAD
from configs.constants import Role, BuildingType

# --- Server / Distributed Hyperparameters ---
NUM_PLAYERS = 3
NUM_ENVS = 32
STEPS_PER_ENV = 512 
BATCH_SIZE = NUM_ENVS * STEPS_PER_ENV 
MINIBATCH_SIZE = 512 
UPDATE_EPOCHS = 10
LEARNING_RATE = 3e-4
GAMMA = 0.99
GAE_LAMBDA = 0.95
CLIP_COEF = 0.2
INITIAL_ENT_COEF = 0.03
VF_COEF = 0.5
MAX_GRAD_NORM = 0.5

TOTAL_TIMESTEPS = 15_000_000
SNAPSHOT_INTERVAL = 50 
OPPONENT_POOL_SIZE = 10
LATEST_POLICY_PROB = 0.7 

# --- Resume Settings ---
RESUME_MODEL_PATH = None # Set to None to start a new training run

# Pipeline CMDs
CMD_STEP = 0
CMD_SET_WEIGHTS = 1
CMD_CLOSE = 2

def extract_phase_id(obs_dict) -> int:
    return int(obs_dict["global_state"]["current_phase"])

def rollout_worker(rank, conn, shared_bufs, obs_dim, action_dim, opponent_pool):
    """
    Persistent environment worker for PhasePPO.
    Receives commands from main process, pushes transitions to shared memory.
    """
    env = PuertoRicoEnv(num_players=NUM_PLAYERS, max_game_steps=1200)
    obs_space = env.observation_space(env.possible_agents[0])["observation"]
    
    local_agent = PhasePPOAgent(obs_dim=obs_dim, action_dim=action_dim)
    local_opponent = PhasePPOAgent(obs_dim=obs_dim, action_dim=action_dim)
    local_agent.eval()
    local_opponent.eval()

    s_obs, s_mask, s_act, s_logp, s_rew, s_done, s_val, s_phase, s_next_val = shared_bufs

    env_initialized = False
    agent_generator = None
    agent_name = None
    learning_player_idx = 0
    opp_weights = None

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
                learning_player_idx = random.randint(0, NUM_PLAYERS - 1)
                
                if not opponent_pool or random.random() < LATEST_POLICY_PROB:
                    opp_weights = None
                else:
                    opp_weights = random.choice(opponent_pool)
                    local_opponent.load_state_dict(opp_weights)
                
                agent_name = None
                env_initialized = True

            stats = {
                "games": 0, "wins": 0, "total_score": 0.0,
                "vp_chips": 0.0, "building_vp": 0.0,
                "role_counts": np.zeros(8),
                "building_counts": np.zeros(23),
                "end_reason_shipping": 0, "end_reason_building": 0, "end_reason_colonists": 0
            }
            
            step_idx = 0
            
            while True:
                if agent_name is None:
                    try:
                        agent_name = next(agent_generator)
                    except StopIteration:
                        stats["games"] += 1
                        
                        final_scores = env.game.get_scores()
                        learner_score = final_scores[learning_player_idx][0]
                        stats["total_score"] += learner_score
                        
                        max_opp = max([final_scores[j][0] for j in range(NUM_PLAYERS) if j != learning_player_idx])
                        if learner_score >= max_opp: stats["wins"] += 1
                        
                        p_obj = env.game.players[learning_player_idx]
                        stats["vp_chips"] += p_obj.vp_chips
                        stats["building_vp"] += (learner_score - p_obj.vp_chips)
                        for b in p_obj.city_board:
                            if b.building_type.value < 23: stats["building_counts"][b.building_type.value] += 1
                        
                        if env.game.vp_chips <= 0: stats["end_reason_shipping"] += 1
                        elif any(p.empty_city_spaces == 0 for p in env.game.players): stats["end_reason_building"] += 1
                        elif getattr(env.game, '_colonists_ship_underfilled', False): stats["end_reason_colonists"] += 1

                        env.reset()
                        agent_generator = iter(env.agent_iter())
                        learning_player_idx = random.randint(0, NUM_PLAYERS - 1)
                        
                        if not opponent_pool or random.random() < LATEST_POLICY_PROB:
                            opp_weights = None
                        else:
                            opp_weights = random.choice(opponent_pool)
                            local_opponent.load_state_dict(opp_weights)
                            
                        agent_name = next(agent_generator)

                obs, reward, termination, truncation, info = env.last()
                p_idx = int(agent_name.split("_")[1])
                is_learner = (p_idx == learning_player_idx)

                if termination or truncation:
                    if is_learner:
                        if step_idx > 0:
                            s_rew[rank, step_idx - 1] = reward
                            s_done[rank, step_idx - 1] = 1.0
                            
                        if step_idx == STEPS_PER_ENV:
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
                    mask = obs["action_mask"]
                    phase_id = extract_phase_id(obs["observation"])
                    
                    obs_t = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
                    mask_t = torch.as_tensor(mask, dtype=torch.float32).unsqueeze(0)
                    phase_t = torch.tensor([phase_id], dtype=torch.long)
                    
                    if step_idx == STEPS_PER_ENV:
                        with torch.no_grad():
                            _, _, _, val = local_agent.get_action_and_value(obs_t, mask_t, phase_ids=phase_t)
                        s_next_val[rank] = val.item()
                        conn.send({"stats": stats})
                        break

                    with torch.no_grad():
                        action, logp, _, val = local_agent.get_action_and_value(obs_t, mask_t, phase_ids=phase_t)
                        
                    s_obs[rank, step_idx] = torch.from_numpy(flat_obs)
                    s_mask[rank, step_idx] = torch.from_numpy(mask)
                    s_act[rank, step_idx] = action.item()
                    s_logp[rank, step_idx] = logp.item()
                    s_val[rank, step_idx] = val.item()
                    s_phase[rank, step_idx] = phase_id
                    
                    try:
                        if action.item() < 8 and mask[action.item()] == 1:
                            stats["role_counts"][action.item()] += 1
                    except Exception:
                        pass
                    
                    env.step(action.item())
                    agent_name = None
                    step_idx += 1
                    
                else:
                    flat_obs = flatten_dict_observation(obs["observation"], obs_space)
                    mask = obs["action_mask"]
                    phase_id = extract_phase_id(obs["observation"])
                    
                    obs_t = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
                    mask_t = torch.as_tensor(mask, dtype=torch.float32).unsqueeze(0)
                    phase_t = torch.tensor([phase_id], dtype=torch.long)
                    
                    agent_to_use = local_opponent if (opp_weights is not None) else local_agent
                    with torch.no_grad():
                        action, _, _, _ = agent_to_use.get_action_and_value(obs_t, mask_t, phase_ids=phase_t)
                        
                    env.step(action.item())
                    agent_name = None

def train():
    try: mp.set_start_method('spawn', force=True)
    except RuntimeError: pass
    
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    run_name = f"PhasePPO_PR_Server_{int(time.time())}"
    writer = SummaryWriter(f"runs/{run_name}")

    # Env Info Extraction
    temp_env = PuertoRicoEnv(num_players=NUM_PLAYERS)
    obs_dim = get_flattened_obs_dim(temp_env.observation_space(temp_env.possible_agents[0])["observation"])
    action_dim = temp_env.action_space(temp_env.possible_agents[0]).n
    del temp_env

    # Vectorized Shared Memory Buffers
    shared_bufs = (
        torch.zeros((NUM_ENVS, STEPS_PER_ENV, obs_dim)).share_memory_(),
        torch.zeros((NUM_ENVS, STEPS_PER_ENV, action_dim)).share_memory_(),
        torch.zeros((NUM_ENVS, STEPS_PER_ENV)).share_memory_(),
        torch.zeros((NUM_ENVS, STEPS_PER_ENV)).share_memory_(),
        torch.zeros((NUM_ENVS, STEPS_PER_ENV)).share_memory_(),
        torch.zeros((NUM_ENVS, STEPS_PER_ENV)).share_memory_(),
        torch.zeros((NUM_ENVS, STEPS_PER_ENV)).share_memory_(),
        torch.zeros((NUM_ENVS, STEPS_PER_ENV), dtype=torch.long).share_memory_(), # Phase ID buffer
        torch.zeros(NUM_ENVS).share_memory_(),                                 # Next value buffer
    )

    agent = PhasePPOAgent(obs_dim=obs_dim, action_dim=action_dim).to(device)
    optimizer = optim.Adam(agent.parameters(), lr=LEARNING_RATE, eps=1e-5)
    
    opponent_pool = mp.Manager().list()

    # Pre-load checkpoint and populate initial opponent pool
    if RESUME_MODEL_PATH is not None and os.path.exists(RESUME_MODEL_PATH):
        print(f"[*] Resuming from checkpoint: {RESUME_MODEL_PATH}")
        agent.load_state_dict(torch.load(RESUME_MODEL_PATH, map_location=device))
        opponent_pool.append({k: v.cpu() for k, v in agent.state_dict().items()})
        print(f"[*] Loaded weights and prepopulated opponent pool.")

    processes = []
    conns = []
    for i in range(NUM_ENVS):
        parent_conn, child_conn = mp.Pipe()
        p = mp.Process(target=rollout_worker, args=(i, child_conn, shared_bufs, obs_dim, action_dim, opponent_pool))
        p.start()
        processes.append(p)
        conns.append(parent_conn)

    global_step = 0
    total_updates = TOTAL_TIMESTEPS // BATCH_SIZE
    train_start_time = time.time()

    print(f"===============================================")
    print(f"🚀 Starting PhasePPO Multiprocessing Train Server")
    print(f"Device: {device} | Total Params: {sum(p.numel() for p in agent.parameters()):,}")
    print(f"Envs: {NUM_ENVS} | Steps/Env: {STEPS_PER_ENV} | Batch: {BATCH_SIZE}")
    print(f"===============================================")

    try:
        for update in range(1, total_updates + 1):
            update_start = time.time()
            
            # LR Drop and Entropy Decay
            frac = 1.0 - (update - 1.0) / total_updates
            optimizer.param_groups[0]["lr"] = frac * LEARNING_RATE
            # 하한선(0.005)을 두어 막바지에 Exploration이 0이 되어 Deterministic하게 굳는 현상 방지
            current_ent_coef = max(0.005, INITIAL_ENT_COEF * frac)

            # Send weights and trigger step collection
            shared_weights = {k: v.cpu() for k, v in agent.state_dict().items()}
            for conn in conns:
                conn.send((CMD_SET_WEIGHTS, shared_weights))
                conn.send((CMD_STEP, None))
            
            # Wait for all workers across network
            results = [conn.recv() for conn in conns]

            # Read shared memory buffers
            obs_b, mask_b, act_b, logp_b, rew_b, done_b, val_b, phase_b, next_val_arr = [b.clone() for b in shared_bufs]

            # Compute GAE
            advantages = torch.zeros_like(rew_b)
            lastgaelam = 0
            for t in reversed(range(STEPS_PER_ENV)):
                nextnonterminal = 1.0 - done_b[:, t]
                nextvalues = next_val_arr if t == STEPS_PER_ENV - 1 else val_b[:, t+1]
                delta = rew_b[:, t] + GAMMA * nextvalues * nextnonterminal - val_b[:, t]
                advantages[:, t] = lastgaelam = delta + GAMMA * GAE_LAMBDA * nextnonterminal * lastgaelam
            returns_b = advantages + val_b

            # Flatten batch for GPU training
            obs_t = obs_b.reshape(-1, obs_dim).to(device)
            mask_t = mask_b.reshape(-1, action_dim).to(device)
            act_t = act_b.reshape(-1).to(device)
            logp_t = logp_b.reshape(-1).to(device)
            phase_t = phase_b.reshape(-1).to(device)
            adv_t = advantages.reshape(-1).to(device)
            ret_t = returns_b.reshape(-1).to(device)

            # PPO Head Updates
            losses_pg, losses_v, losses_ent = [], [], []
            phase_entropies = defaultdict(list)
            
            b_inds = np.arange(BATCH_SIZE)
            target_kl = 0.015
            early_stop = False
            
            for epoch in range(UPDATE_EPOCHS):
                if early_stop:
                    break
                    
                np.random.shuffle(b_inds)
                for start in range(0, BATCH_SIZE, MINIBATCH_SIZE):
                    mb = b_inds[start:start+MINIBATCH_SIZE]
                    
                    _, newlogp, entropy, newval = agent.get_action_and_value(
                        obs_t[mb], mask_t[mb], phase_ids=phase_t[mb], action=act_t[mb]
                    )
                    
                    logratio = newlogp - logp_t[mb]
                    ratio = logratio.exp()
                    
                    # KL 발산 모니터링
                    with torch.no_grad():
                        approx_kl = ((ratio - 1) - logratio).mean().item()
                    
                    # Target KL 초과 시 업데이트 조기 종료 (Catastrophic Forgetting 방지)
                    if approx_kl > target_kl:
                        early_stop = True
                        break
                        
                    mb_adv = (adv_t[mb] - adv_t[mb].mean()) / (adv_t[mb].std() + 1e-8)
                    pg_loss = torch.max(-mb_adv * ratio, -mb_adv * torch.clamp(ratio, 1-CLIP_COEF, 1+CLIP_COEF)).mean()
                    v_loss = 0.5 * ((newval.view(-1) - ret_t[mb])**2).mean()
                    
                    loss = pg_loss - current_ent_coef * entropy.mean() + v_loss * VF_COEF
                    
                    optimizer.zero_grad()
                    loss.backward()
                    nn.utils.clip_grad_norm_(agent.parameters(), MAX_GRAD_NORM)
                    optimizer.step()
                    
                    losses_pg.append(pg_loss.item())
                    losses_v.append(v_loss.item())
                    losses_ent.append(entropy.mean().item())
                    
                    # Track breakdown of entropy per Phase
                    if epoch == 0: 
                        mb_phase_cpu = phase_t[mb].cpu().numpy()
                        mb_ent_cpu = entropy.detach().cpu().numpy()
                        for i in range(len(mb)):
                            hk = PHASE_TO_HEAD.get(mb_phase_cpu[i], "role_select")
                            phase_entropies[hk].append(mb_ent_cpu[i])

            global_step += BATCH_SIZE
            total_games = sum(r["stats"]["games"] for r in results)
            
            # Record base metrics
            writer.add_scalar("Loss/PolicyLoss", np.mean(losses_pg), global_step)
            writer.add_scalar("Loss/ValueLoss", np.mean(losses_v), global_step)
            writer.add_scalar("Loss/Entropy", np.mean(losses_ent), global_step)
            writer.add_scalar("Hyperparameters/Ent_Coef", current_ent_coef, global_step)
            
            for hk, evals in phase_entropies.items():
                if evals: writer.add_scalar(f"Entropy_Phase/{hk}", np.mean(evals), global_step)

            # Record Game Stats
            if total_games > 0:
                writer.add_scalar("Performance/WinRate", sum(r["stats"]["wins"] for r in results) / total_games, global_step)
                writer.add_scalar("Strategy/VP_Shipping", sum(r["stats"]["vp_chips"] for r in results) / total_games, global_step)
                writer.add_scalar("Strategy/VP_Building", sum(r["stats"]["building_vp"] for r in results) / total_games, global_step)
                
                writer.add_scalar("End_Reason/Shipping_Limit", sum(r["stats"]["end_reason_shipping"] for r in results) / total_games, global_step)
                writer.add_scalar("End_Reason/Building_Full", sum(r["stats"]["end_reason_building"] for r in results) / total_games, global_step)
                writer.add_scalar("End_Reason/Colonist_Empty", sum(r["stats"]["end_reason_colonists"] for r in results) / total_games, global_step)

                bldg_dist = np.sum([r["stats"]["building_counts"] for r in results], axis=0)
                for i in range(0, 6): writer.add_scalar(f"Buildings_Production/{BuildingType(i).name}", bldg_dist[i] / total_games, global_step)
                for i in range(6, 18): writer.add_scalar(f"Buildings_Commercial/{BuildingType(i).name}", bldg_dist[i] / total_games, global_step)
                for i in range(18, 23): writer.add_scalar(f"Buildings_Large/{BuildingType(i).name}", bldg_dist[i] / total_games, global_step)
                for i in range(8): writer.add_scalar(f"Role_Selection/{Role(i).name}", sum(r["stats"]["role_counts"][i] for r in results) / total_games, global_step)

            # Terminal Print
            elapsed_time = time.time() - train_start_time
            fps = global_step / elapsed_time if elapsed_time > 0 else 1
            remaining_steps = TOTAL_TIMESTEPS - global_step
            eta_str = time.strftime("%H:%M:%S", time.gmtime(remaining_steps / fps))
            
            print(f"[Update {update}/{total_updates}] Step: {global_step}/{TOTAL_TIMESTEPS} | FPS: {int(fps)} | ETA: {eta_str}")
            if total_games > 0:
                win_rate = sum(r["stats"]["wins"] for r in results) / total_games
                print(f" └─ WinRate: {win_rate:.2f} | Loss(P/V/E): {np.mean(losses_pg):.3f}/{np.mean(losses_v):.3f}/{np.mean(losses_ent):.3f}\n")

            if update % SNAPSHOT_INTERVAL == 0:
                opponent_pool.append(copy.deepcopy(shared_weights))
                if len(opponent_pool) > OPPONENT_POOL_SIZE: opponent_pool.pop(0)
                os.makedirs("models", exist_ok=True)
                torch.save(agent.state_dict(), f"models/{run_name}_step_{global_step}.pth")

    finally:
        for conn in conns: conn.send((CMD_CLOSE, None))
        for p in processes: p.join()
        writer.close()

if __name__ == "__main__":
    train()
