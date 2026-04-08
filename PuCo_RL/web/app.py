import sys
import os
import torch
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import contextlib

# Add root dir to sys path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
from agents.ppo_agent import PhasePPOAgent, Agent as PPOAgent, PHASE_TO_HEAD
from agents.heuristic_bots import RandomBot
from agents.shipping_rush_agent import ShippingRushAgent
from web.action_mapping import get_action_text

app = FastAPI(title="Puerto Rico AI Interface")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

class GameState:
    def __init__(self):
        self.env = None
        self.agent_instances = {}
        self.seat_map = {} # f"player_{i}" -> "Human", "PPO", "Random", "Shipping"
        self.human_player = None
        self.ppo_insights = {"value": 0.0, "probabilities": []}
        self.last_action_log = []
        self.round_number = 1
        self.last_governor = None

global_state = GameState()

# Ensure we have the model path right
MODEL_PATH = "/home/daehan/PuertoRico_RL/models/ppo_checkpoints/근본잠재함수사용_룰베이스없음/PPO_PR_Server_20260331_163417_step_99942400.pth"
_loaded_ppo_model = None
def get_ppo_model(obs_dim, action_dim):
    global _loaded_ppo_model
    if _loaded_ppo_model is None:
        state_dict = torch.load(MODEL_PATH, map_location='cpu')
        is_phase_ppo = any(k.startswith('phase_heads.') or k.startswith('phase_embed.') for k in state_dict.keys())
        if is_phase_ppo:
            agent = PhasePPOAgent(obs_dim=obs_dim, action_dim=action_dim)
        else:
            agent = PPOAgent(obs_dim=obs_dim, action_dim=action_dim)
        agent.load_state_dict(state_dict)
        agent.eval()
        _loaded_ppo_model = agent
    return _loaded_ppo_model

class StartRequest(BaseModel):
    seat_0: str
    seat_1: str
    seat_2: str

class ActionRequest(BaseModel):
    action: int

@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r") as f:
        return f.read()

@app.post("/api/start")
def start_game(req: StartRequest):
    global_state.env = PuertoRicoEnv(num_players=3, max_game_steps=2000)
    obs_space = global_state.env.observation_space(global_state.env.possible_agents[0])["observation"]
    obs_dim = get_flattened_obs_dim(obs_space)
    action_dim = global_state.env.action_space(global_state.env.possible_agents[0]).n
    
    seats = [req.seat_0, req.seat_1, req.seat_2]
    global_state.agent_instances = {}
    global_state.seat_map = {}
    global_state.last_action_log = []
    global_state.ppo_insights = {"value": 0.0, "probabilities": []}
    global_state.round_number = 1
    global_state.last_governor = None
    
    for i, stype in enumerate(seats):
        pname = f"player_{i}"
        global_state.seat_map[pname] = stype
        if stype == "Human":
            global_state.human_player = pname
        elif stype == "PPO":
            global_state.agent_instances[pname] = get_ppo_model(obs_dim, action_dim)
        elif stype == "Random":
            global_state.agent_instances[pname] = RandomBot(action_dim).eval()
        elif stype.startswith("Shipping"):
            # Shipping Rush Agent strategy 0
            global_state.agent_instances[pname] = ShippingRushAgent(action_dim, fixed_strategy=0).eval()
            
    global_state.env.reset()
    
    # Progress game until it's human's turn
    progress_until_human()
    return {"status": "ok"}

def handle_ppo_inference(model, obs_dict, action_mask, pname):
    # Flatten observation
    flat_obs = flatten_dict_observation(obs_dict["observation"], global_state.env.observation_space("player_0")["observation"])
    obs_t = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
    mask_t = torch.as_tensor(action_mask, dtype=torch.float32).unsqueeze(0)
    
    with torch.no_grad():
        if isinstance(model, PhasePPOAgent):
            phase_id = int(obs_dict["observation"]["global_state"]["current_phase"])
            phase_t = torch.tensor([phase_id], dtype=torch.long)
            
            # Reconstruct what the model does to get probabilities
            features = model._shared_features(obs_t, phase_t)
            value = model.critic_head(features).item()
            
            head_key = PHASE_TO_HEAD.get(phase_id, "role_select")
            head_logits = model.phase_heads[head_key](features)
            
            action, _, _, _ = model.get_action_and_value(obs_t, mask_t, phase_ids=phase_t)
        else: # Regular PPO
            features = model._shared_features(obs_t)
            value = model.critic_head(features).item()
            head_logits = model.actor_head(features)
            action, _, _, _ = model.get_action_and_value(obs_t, mask_t)

        huge_negative = torch.tensor(-1e8, dtype=head_logits.dtype, device=head_logits.device)
        masked_logits = torch.where(mask_t > 0.5, head_logits, huge_negative)
        probs = torch.softmax(masked_logits, dim=-1)[0].numpy()
        
    action_idx = action.item()
    
    # Extract prob
    valid_actions = np.where(action_mask == 1)[0]
    prob_list = []
    for a in valid_actions:
        prob_list.append({
            "action": int(a),
            "text": get_action_text(a),
            "prob": float(probs[a])
        })
        
    prob_list.sort(key=lambda x: x["prob"], reverse=True)
    
    global_state.ppo_insights = {
        "value": round(value, 3),
        "probabilities": prob_list
    }
    return action_idx

def handle_shipping_rush_inference(model, obs_dict, action_mask, pname):
    flat_obs = flatten_dict_observation(obs_dict["observation"], global_state.env.observation_space("player_0")["observation"])
    obs_t = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
    mask_t = torch.as_tensor(action_mask, dtype=torch.float32).unsqueeze(0)
    player_idx = int(pname.split("_")[1])
    with torch.no_grad():
        action_t, _, _, _ = model.get_action_and_value(obs_t, mask_t, obs_dict=obs_dict["observation"], player_idx=player_idx)
    return action_t.item()

def progress_until_human():
    while True:
        agent = global_state.env.agent_selection
        obs_dict = global_state.env.observe(agent)
        
        if global_state.env.terminations[agent] or global_state.env.truncations[agent]:
            global_state.env.step(None)
            if all(global_state.env.terminations.values()) or all(global_state.env.truncations.values()):
                break # Game over
            continue
            
        if global_state.seat_map[agent] == "Human":
            break # Waiting for human
            
        # It's AI turn
        model = global_state.agent_instances[agent]
        mask = obs_dict["action_mask"]
        
        stype = global_state.seat_map[agent]
        if stype == "PPO":
            action = handle_ppo_inference(model, obs_dict, mask, agent)
        elif stype.startswith("Shipping"):
            action = handle_shipping_rush_inference(model, obs_dict, mask, agent)
        else: # Random
            valid_actions = np.where(mask == 1)[0]
            action = int(np.random.choice(valid_actions))
            
        global_state.last_action_log.append(f"{agent} ({stype}): {get_action_text(action)}")
        global_state.env.step(action)
        
@app.post("/api/step")
def human_step(req: ActionRequest):
    if not global_state.env:
        return {"error": "Game not started"}
        
    human_agent = global_state.env.agent_selection
    if global_state.seat_map.get(human_agent) != "Human":
        return {"error": "Not human turn"}
        
    global_state.last_action_log.append(f"{human_agent} (Human): {get_action_text(req.action)}")
    global_state.env.step(req.action)
    
    # Keep last 10 actions to avoid massive payload
    global_state.last_action_log = global_state.last_action_log[-10:]
    
    progress_until_human()
    return {"status": "ok"}

@app.get("/api/state")
def get_state():
    if not global_state.env:
        return {"started": False}
        
    agent = global_state.env.agent_selection
    obs_dict = global_state.env.observe(agent)
    
    is_game_over = all(global_state.env.terminations.values()) or all(global_state.env.truncations.values())
    
    current_gov = int(global_state.env.game.governor_idx)
    if global_state.last_governor is None:
        global_state.last_governor = current_gov
    elif current_gov != global_state.last_governor:
        global_state.round_number += 1
        global_state.last_governor = current_gov
        
    error_msg = None
    if is_game_over:
        for info in global_state.env.infos.values():
            if "error" in info:
                error_msg = info["error"]
                break
    
    # Generate action list for human if it's their turn
    human_actions = []
    if not is_game_over and global_state.seat_map.get(agent) == "Human":
        valid_actions = np.where(obs_dict["action_mask"] == 1)[0]
        for a in valid_actions:
            human_actions.append({
                "id": int(a),
                "text": get_action_text(a)
            })
            
    # Serialize observation recursively
    def serialize_np(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: serialize_np(v) for k, v in obj.items()}
        return obj

    global_obs = serialize_np(obs_dict["observation"]["global_state"])
    players_obs = serialize_np(obs_dict["observation"]["players"])

    return {
        "started": True,
        "is_game_over": is_game_over,
        "current_player": agent,
        "is_human_turn": global_state.seat_map.get(agent) == "Human" and not is_game_over,
        "round_number": global_state.round_number,
        "governor": f"player_{global_state.last_governor}",
        "global_state": global_obs,
        "players": players_obs,
        "human_actions": human_actions,
        "ppo_insights": global_state.ppo_insights,
        "action_log": global_state.last_action_log,
        "seat_map": global_state.seat_map,
        "error_msg": error_msg
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
