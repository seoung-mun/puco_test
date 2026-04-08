"""
replay_single_game.py – Detailed single-game replay with human-readable log.

Plays 1 game with 3 copies of a PPO agent and outputs a turn-by-turn play log
so researchers can inspect whether the agent understands Puerto Rico strategy.

Usage:
    source venv/bin/activate
    python evaluate/replay_single_game.py \
        --model_path models/ppo_checkpoints/PPO_PR_Server_Option3_QV_Split_option3_S1.0_B1.0_D1.0_1774587128_step_14745600.pth \
        --seed 42
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
import json
import time
import torch
import numpy as np
from typing import Optional, Dict, List, Any

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
from agents.ppo_agent import PhasePPOAgent, Agent as PPOAgent
from agents.shipping_rush_agent import ShippingRushAgent
from agents.factory_rule_based_agent import FactoryRuleBasedAgent
from agents.heuristic_bots import RandomBot
from configs.constants import (
    Phase, Role, Good, TileType, BuildingType, BUILDING_DATA, GOOD_PRICES,
    MayorStrategy, MAYOR_STRATEGY_BUILDINGS
)

# Available bot names → label
BOT_OPTIONS = ["ppo", "shipping", "factory", "random"]

BOT_LABELS = {
    "ppo":      "PPO Agent",
    "shipping": "AdvRule Shipping",
    "factory":  "Factory Bot",
    "random":   "Random Bot",
}

# ──────────────────────── Human-readable Name Maps ────────────────────────
ROLE_NAMES = {
    Role.SETTLER: "Settler", Role.MAYOR: "Mayor", Role.BUILDER: "Builder",
    Role.CRAFTSMAN: "Craftsman", Role.TRADER: "Trader", Role.CAPTAIN: "Captain",
    Role.PROSPECTOR_1: "Prospector", Role.PROSPECTOR_2: "Prospector2",
}

GOOD_NAMES = {
    Good.COFFEE: "Coffee", Good.TOBACCO: "Tobacco", Good.CORN: "Corn",
    Good.SUGAR: "Sugar", Good.INDIGO: "Indigo",
}

TILE_NAMES = {
    TileType.COFFEE_PLANTATION: "Coffee Plantation",
    TileType.TOBACCO_PLANTATION: "Tobacco Plantation",
    TileType.CORN_PLANTATION: "Corn Plantation",
    TileType.SUGAR_PLANTATION: "Sugar Plantation",
    TileType.INDIGO_PLANTATION: "Indigo Plantation",
    TileType.QUARRY: "Quarry",
    TileType.EMPTY: "(empty)",
}

BUILDING_NAMES = {bt: bt.name.replace("_", " ").title() for bt in BuildingType}

SHIP_SIZE_LABELS = {0: "Small Ship", 1: "Medium Ship", 2: "Large Ship"}

# ──────────────────────── Action Decoder ────────────────────────
def decode_action(action: int, game) -> str:
    """Translate action int to human-readable string."""
    if 0 <= action <= 7:
        role = Role(action)
        bonus = game.role_doubloons.get(role, 0)
        bonus_str = f" (+{bonus} doubloon{'s' if bonus != 1 else ''})" if bonus > 0 else ""
        return f"Select Role: {ROLE_NAMES.get(role, str(role))}{bonus_str}"
    elif 8 <= action <= 13:
        idx = action - 8
        if idx < len(game.face_up_plantations):
            tile = game.face_up_plantations[idx]
            return f"Settler: Take {TILE_NAMES.get(tile, str(tile))} (face-up #{idx})"
        return f"Settler: Take face-up plantation #{idx}"
    elif action == 14:
        return "Settler: Take Quarry"
    elif action == 15:
        phase = game.current_phase
        return f"Pass ({phase.name if phase else 'N/A'})"
    elif 16 <= action <= 38:
        bt = BuildingType(action - 16)
        cost = BUILDING_DATA[bt][0]
        vp = BUILDING_DATA[bt][1]
        return f"Builder: Build {BUILDING_NAMES[bt]} (cost {cost}, VP {vp})"
    elif 39 <= action <= 43:
        g = Good(action - 39)
        base_price = GOOD_PRICES[g]
        return f"Trader: Sell {GOOD_NAMES[g]} (base price {base_price})"
    elif 44 <= action <= 58:
        idx = action - 44
        ship_idx = idx // 5
        g = Good(idx % 5)
        return f"Captain: Load {GOOD_NAMES[g]} onto {SHIP_SIZE_LABELS.get(ship_idx, f'Ship #{ship_idx}')}"
    elif 59 <= action <= 63:
        g = Good(action - 59)
        return f"Captain: Load {GOOD_NAMES[g]} via Wharf"
    elif 64 <= action <= 68:
        g = Good(action - 64)
        return f"Store (Windrose): Keep 1 {GOOD_NAMES[g]}"
    elif 69 <= action <= 71:
        strategy = MayorStrategy(action - 69)          # 69=CAPTAIN_FOCUS, 70=TRADE_FACTORY_FOCUS, 71=BUILDING_FOCUS
        strategy_labels = {
            MayorStrategy.CAPTAIN_FOCUS:       "Shipping Focus",
            MayorStrategy.TRADE_FACTORY_FOCUS: "Trade/Factory Focus",
            MayorStrategy.BUILDING_FOCUS:      "Building Focus",
        }
        # Show top-2 priority buildings for this strategy
        priority_bldgs = MAYOR_STRATEGY_BUILDINGS.get(strategy, [])
        priority_str = ", ".join(
            b.name.replace("_", " ").title() for b in priority_bldgs[:2]
        )
        label = strategy_labels.get(strategy, strategy.name)
        return f"Mayor: [{label}] — priority: {priority_str}..."
    elif 93 <= action <= 97:
        g = Good(action - 93)
        return f"Craftsman Privilege: Take 1 extra {GOOD_NAMES[g]}"
    elif action == 105:
        return "Settler: Hacienda draw (face-down plantation)"
    elif 106 <= action <= 110:
        g = Good(action - 106)
        return f"Store (Warehouse): Keep all {GOOD_NAMES[g]}"
    return f"Unknown action {action}"


# ──────────────────────── State Snapshot ────────────────────────
def snapshot_player(player, player_idx: int) -> Dict[str, Any]:
    """Capture a readable snapshot of a player's state."""
    island = []
    for t in player.island_board:
        island.append({
            "tile": TILE_NAMES.get(t.tile_type, str(t.tile_type)),
            "occupied": t.is_occupied
        })
    buildings = []
    for b in player.city_board:
        if b.building_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
            continue
        buildings.append({
            "building": BUILDING_NAMES[b.building_type],
            "colonists": b.colonists,
            "max_colonists": BUILDING_DATA[b.building_type][2],
            "active": b.colonists > 0
        })
    goods = {GOOD_NAMES[g]: amt for g, amt in player.goods.items() if amt > 0}
    return {
        "player_idx": player_idx,
        "doubloons": player.doubloons,
        "vp_chips": player.vp_chips,
        "unplaced_colonists": player.unplaced_colonists,
        "goods": goods if goods else "(none)",
        "island_tiles": len(player.island_board),
        "island": island,
        "buildings": buildings,
        "empty_city_spaces": player.empty_city_spaces,
    }

def snapshot_global(game) -> Dict[str, Any]:
    """Capture a readable snapshot of global game state."""
    ships = []
    for i, s in enumerate(game.cargo_ships):
        ships.append({
            "label": SHIP_SIZE_LABELS.get(i, f"Ship {i}"),
            "capacity": s.capacity,
            "load": s.current_load,
            "good": GOOD_NAMES.get(s.good_type, "Empty") if s.good_type is not None else "Empty"
        })
    trading_house = [GOOD_NAMES.get(g, str(g)) for g in game.trading_house]
    face_up = [TILE_NAMES.get(t, str(t)) for t in game.face_up_plantations]
    avail_roles = [ROLE_NAMES.get(r, str(r)) for r in game.available_roles]
    role_bonus = {ROLE_NAMES.get(r, str(r)): d for r, d in game.role_doubloons.items() if d > 0}
    return {
        "vp_pool": game.vp_chips,
        "colonist_supply": game.colonists_supply,
        "colonist_ship": game.colonists_ship,
        "cargo_ships": ships,
        "trading_house": trading_house if trading_house else "(empty)",
        "face_up_plantations": face_up,
        "quarries_left": game.quarry_stack,
        "available_roles": avail_roles,
        "role_bonuses": role_bonus if role_bonus else "(none)",
        "governor": f"Player {game.governor_idx}",
    }


# ──────────────────────── Strategic Commentary ────────────────────────
def comment_role_selection(role: Role, player, game) -> str:
    """Provide strategic commentary on role selection."""
    comments = []
    if role == Role.CRAFTSMAN:
        # Check production capacity
        corn = sum(1 for t in player.island_board if t.tile_type == TileType.CORN_PLANTATION and t.is_occupied)
        indigo_f = sum(1 for t in player.island_board if t.tile_type == TileType.INDIGO_PLANTATION and t.is_occupied)
        indigo_c = sum(b.colonists for b in player.city_board if b.building_type in (BuildingType.SMALL_INDIGO_PLANT, BuildingType.INDIGO_PLANT))
        sugar_f = sum(1 for t in player.island_board if t.tile_type == TileType.SUGAR_PLANTATION and t.is_occupied)
        sugar_c = sum(b.colonists for b in player.city_board if b.building_type in (BuildingType.SMALL_SUGAR_MILL, BuildingType.SUGAR_MILL))
        tobacco_f = sum(1 for t in player.island_board if t.tile_type == TileType.TOBACCO_PLANTATION and t.is_occupied)
        tobacco_c = sum(b.colonists for b in player.city_board if b.building_type == BuildingType.TOBACCO_STORAGE)
        coffee_f = sum(1 for t in player.island_board if t.tile_type == TileType.COFFEE_PLANTATION and t.is_occupied)
        coffee_c = sum(b.colonists for b in player.city_board if b.building_type == BuildingType.COFFEE_ROASTER)
        prod = corn + min(indigo_f, indigo_c) + min(sugar_f, sugar_c) + min(tobacco_f, tobacco_c) + min(coffee_f, coffee_c)
        comments.append(f"Production capacity: {prod} goods")
        if player.is_building_occupied(BuildingType.FACTORY):
            comments.append("Has Factory → extra doubloons from diverse production")
    elif role == Role.CAPTAIN:
        total_goods = sum(player.goods.values())
        comments.append(f"Holding {total_goods} goods")
        if player.is_building_occupied(BuildingType.HARBOR):
            comments.append("Has Harbor → +1 VP per shipment")
        if player.is_building_occupied(BuildingType.WHARF):
            comments.append("Has Wharf → can ship any good privately")
    elif role == Role.TRADER:
        valuable = [(GOOD_NAMES[g], GOOD_PRICES[g]) for g in Good if player.goods[g] > 0]
        if valuable:
            best = max(valuable, key=lambda x: x[1])
            comments.append(f"Best sellable: {best[0]} (base {best[1]})")
        if player.is_building_occupied(BuildingType.SMALL_MARKET):
            comments.append("Has Small Market → +1 doubloon")
        if player.is_building_occupied(BuildingType.LARGE_MARKET):
            comments.append("Has Large Market → +2 doubloons")
    elif role == Role.BUILDER:
        comments.append(f"Has {player.doubloons} doubloons")
        quarries = sum(1 for t in player.island_board if t.tile_type == TileType.QUARRY and t.is_occupied)
        if quarries > 0:
            comments.append(f"Active quarries: {quarries} → discount")
    elif role == Role.MAYOR:
        comments.append(f"Unplaced colonists: {player.unplaced_colonists}")
        empty_capacity = 0
        for b in player.city_board:
            if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                empty_capacity += BUILDING_DATA[b.building_type][2] - b.colonists
        for t in player.island_board:
            if t.tile_type != TileType.EMPTY and not t.is_occupied:
                empty_capacity += 1
        comments.append(f"Empty placeable slots: {empty_capacity}")
    elif role == Role.SETTLER:
        comments.append(f"Empty island spaces: {player.empty_island_spaces}")
    if comments:
        return " | ".join(comments)
    return ""


# ──────────────────────── Model Loading ────────────────────────
def load_model(path: str, obs_dim: int, action_dim: int):
    """Auto-detect architecture and load model."""
    state_dict = torch.load(path, map_location='cpu', weights_only=True)
    is_phase = any(k.startswith('phase_heads.') or k.startswith('phase_embed.') for k in state_dict.keys())
    if is_phase:
        model = PhasePPOAgent(obs_dim=obs_dim, action_dim=action_dim)
    else:
        model = PPOAgent(obs_dim=obs_dim, action_dim=action_dim)
    model.load_state_dict(state_dict)
    model.eval()
    return model, is_phase


def build_bot(bot_type: str, action_dim: int, ppo_model=None, is_phase: bool = False):
    """Return (agent_obj, is_ppo_flag, is_phase_flag, label)."""
    if bot_type == "ppo":
        assert ppo_model is not None
        return ppo_model, True, is_phase, BOT_LABELS["ppo"]
    elif bot_type == "shipping":
        return ShippingRushAgent(action_dim, fixed_strategy=0).eval(), False, False, BOT_LABELS["shipping"]
    elif bot_type == "factory":
        return FactoryRuleBasedAgent(action_dim).eval(), False, False, BOT_LABELS["factory"]
    elif bot_type == "random":
        return RandomBot(action_dim).eval(), False, False, BOT_LABELS["random"]
    else:
        raise ValueError(f"Unknown bot type: '{bot_type}'. Choose from: {BOT_OPTIONS}")


def get_bot_action(agent, is_ppo: bool, is_phase: bool, obs, env) -> tuple:
    """
    Unified action getter.
    Returns (action_int, top_k_list, value_float).
    top_k and value are only meaningful for PPO agents.
    """
    flat_obs = flatten_dict_observation(
        obs["observation"],
        env.observation_space("player_0")["observation"]
    )
    mask = obs["action_mask"]
    phase_id = int(obs["observation"]["global_state"]["current_phase"])
    player_idx = int(obs["observation"]["global_state"]["current_player"])
    if hasattr(player_idx, "item"):
        player_idx = player_idx.item()

    obs_t  = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
    mask_t = torch.as_tensor(mask,    dtype=torch.float32).unsqueeze(0)

    with torch.no_grad():
        if is_ppo:
            if is_phase:
                phase_t  = torch.tensor([phase_id], dtype=torch.long)
                features = agent._shared_features(obs_t, phase_t)
                value    = agent.critic_head(features).item()
                from agents.ppo_agent import PHASE_TO_HEAD
                head_key = PHASE_TO_HEAD.get(phase_id, "role_select")
                logits   = agent.phase_heads[head_key](features).squeeze(0)
            else:
                features = agent._shared_features(obs_t)
                value    = agent.critic_head(features).item()
                logits   = agent.actor_head(features).squeeze(0)

            huge_neg    = torch.tensor(-1e8)
            mask_bool   = torch.as_tensor(mask, dtype=torch.float32)
            masked_logits = torch.where(mask_bool > 0.5, logits, huge_neg)
            probs       = torch.softmax(masked_logits, dim=-1)
            action      = int(torch.argmax(probs).item())

            valid_indices = np.where(mask == 1)[0]
            top_k = sorted([(int(i), probs[i].item()) for i in valid_indices],
                           key=lambda x: x[1], reverse=True)[:5]
            return action, top_k, value

        else:
            # Rule-based / heuristic bots
            from agents.shipping_rush_agent import ShippingRushAgent
            from agents.factory_rule_based_agent import FactoryRuleBasedAgent
            if isinstance(agent, (ShippingRushAgent, FactoryRuleBasedAgent)):
                act_t, _, _, _ = agent.get_action_and_value(
                    obs_t, mask_t,
                    obs_dict=obs["observation"], player_idx=int(player_idx)
                )
            else:
                act_t, _, _, _ = agent.get_action_and_value(obs_t, mask_t)
            return int(act_t.item()), [], 0.0


# ──────────────────────── Main Replay Loop ────────────────────────
def run_replay(model_path: str, seed: int = 42,
               bot1: str = "shipping", bot2: str = "factory"):
    env = PuertoRicoEnv(num_players=3, max_game_steps=1500)
    obs_space = env.observation_space("player_0")["observation"]
    obs_dim   = get_flattened_obs_dim(obs_space)
    action_dim = env.action_space("player_0").n

    # PPO Agent is always Player 0
    ppo_model, is_phase = load_model(model_path, obs_dim, action_dim)
    arch_name = "PhasePPOAgent" if is_phase else "PPOAgent"

    agents: list = [None, None, None]  # indexed by player seat
    is_ppo_flags: list[bool]   = [False, False, False]
    is_phase_flags: list[bool] = [False, False, False]
    labels: list[str]          = ["", "", ""]

    agents[0], is_ppo_flags[0], is_phase_flags[0], labels[0] = build_bot(
        "ppo", action_dim, ppo_model, is_phase
    )
    agents[1], is_ppo_flags[1], is_phase_flags[1], labels[1] = build_bot(
        bot1, action_dim, ppo_model, is_phase
    )
    agents[2], is_ppo_flags[2], is_phase_flags[2], labels[2] = build_bot(
        bot2, action_dim, ppo_model, is_phase
    )

    print(f"{'='*80}")
    print(f"  PUERTO RICO — SINGLE GAME REPLAY LOG")
    print(f"  PPO Model : {os.path.basename(model_path)}  ({arch_name})")
    print(f"  Player 0  : {labels[0]}  ← PPO (you are watching this player)")
    print(f"  Player 1  : {labels[1]}  [--bot1]")
    print(f"  Player 2  : {labels[2]}  [--bot2]")
    print(f"  Seed      : {seed}")
    print(f"{'='*80}\n")

    env.reset(seed=seed)
    game = env.game

    # Reset strategy for rule-based bots
    for a in agents:
        if callable(getattr(a, "reset_strategy", None)):
            a.reset_strategy()

    log_entries: List[Dict[str, Any]] = []
    step_count = 0
    round_num = 0
    roles_selected_this_round = 0
    last_phase = None
    last_governor_idx = game.governor_idx  # Track governor changes for real round boundaries

    print(f"{'─'*80}")
    print(f"  INITIAL SETUP")
    print(f"{'─'*80}")
    print(f"  Governor: Player {game.governor_idx}")
    for i in range(3):
        p = game.players[i]
        tiles = [TILE_NAMES.get(t.tile_type, "?") for t in p.island_board]
        print(f"  Player {i}: {p.doubloons} doubloons, Island: {', '.join(tiles)}")
    print()

    for agent_id in env.agent_iter():
        obs, reward, termination, truncation, info = env.last()

        if termination or truncation:
            env.step(None)
            continue

        player_idx = int(agent_id.split("_")[1])
        current_phase = game.current_phase

        # Round boundary detection
        current_governor = game.governor_idx
        if current_governor != last_governor_idx:
            round_num += 1
            roles_selected_this_round = 0
            last_governor_idx = current_governor
            print(f"\n{'═'*80}")
            print(f"  ROUND {round_num}")
            print(f"{'═'*80}")
            g_snap = snapshot_global(game)
            print(f"  Governor: {g_snap['governor']}  |  VP Pool: {g_snap['vp_pool']}  |  "
                  f"Colonist Supply: {g_snap['colonist_supply']}  |  Colonist Ship: {g_snap['colonist_ship']}")
            for s in g_snap['cargo_ships']:
                print(f"    {s['label']}: {s['load']}/{s['capacity']} ({s['good']})")
            if g_snap['role_bonuses'] and g_snap['role_bonuses'] != "(none)":
                bonus_str = ", ".join([f"{r}: +{d}" for r, d in g_snap['role_bonuses'].items()])
                print(f"  Role Bonuses: {bonus_str}")
            print()

        last_phase = current_phase

        # Dispatch to correct agent
        action, top_k, value = get_bot_action(
            agents[player_idx], is_ppo_flags[player_idx], is_phase_flags[player_idx], obs, env
        )
        action_str = decode_action(action, game)
        player_label = labels[player_idx]

        # Build log entry
        entry = {
            "step": step_count,
            "round": round_num,
            "player": player_idx,
            "phase": current_phase.name if current_phase else "INIT",
            "action_id": action,
            "action": action_str,
            "value_estimate": round(value, 4),
            "top_actions": [
                {"action_id": a, "action": decode_action(a, game), "prob": round(p, 4)}
                for a, p in top_k
            ],
        }

        # Phase-specific context
        commentary = ""
        if 0 <= action <= 7:
            role = Role(action)
            commentary = comment_role_selection(role, game.players[player_idx], game)
            entry["role_selected"] = ROLE_NAMES.get(role, str(role))
            roles_selected_this_round += 1

        # Print formatted log
        phase_label = current_phase.name if current_phase else "INIT"
        is_ppo_player = is_ppo_flags[player_idx]
        marker = "▶" if is_ppo_player else " "
        print(f"  {marker}[{step_count:4d}] P{player_idx}({player_label:<16s}) | {phase_label:15s} | {action_str}")

        # Show top alternatives only for PPO agent
        if is_ppo_player and len(top_k) > 1:
            chosen_prob = top_k[0][1]
            alts = []
            for a_id, p in top_k[1:4]:
                alts.append(f"{decode_action(a_id, game)} ({p:.1%})")
            print(f"         ↳ Confidence: {chosen_prob:.1%}  |  Alternatives: {', '.join(alts)}")

        if commentary:
            print(f"         ↳ Context: {commentary}")

        # Show value estimate only for PPO player at key decisions
        if is_ppo_flags[player_idx] and current_phase in (
            Phase.END_ROUND, Phase.BUILDER, Phase.CAPTAIN
        ):
            print(f"         ↳ V(s) = {value:.4f}")

        # ── Mayor: capture state before step, then show diff after ─────────
        _pre_city_col: dict | None = None
        _pre_island_occ: list | None = None
        if 69 <= action <= 71:
            p_obj = game.players[player_idx]
            _pre_city_col = {
                b.building_type: b.colonists for b in p_obj.city_board
                if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
            }
            _pre_island_occ = [t.is_occupied for t in p_obj.island_board]

        entry["commentary"] = commentary
        log_entries.append(entry)
        step_count += 1

        env.step(action)

        # Show Mayor colonist placement result
        if _pre_city_col is not None:
            p_obj = game.players[player_idx]
            gained_bldg = []
            for b in p_obj.city_board:
                bt = b.building_type
                if bt in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                    continue
                before = _pre_city_col.get(bt, 0)
                after  = b.colonists
                if after > before:
                    bname = BUILDING_NAMES[bt]
                    gained_bldg.append(f"{bname} (+{after - before})")

            gained_tile = []
            for i, t in enumerate(p_obj.island_board):
                if not _pre_island_occ[i] and t.is_occupied:
                    tname = TILE_NAMES.get(t.tile_type, "?")
                    gained_tile.append(tname)

            parts = []
            if gained_bldg:
                parts.append("Buildings: " + ", ".join(gained_bldg))
            if gained_tile:
                parts.append("Tiles: " + ", ".join(gained_tile))
            if parts:
                print(f"         ↳ Colonists placed → {' | '.join(parts)}")
            else:
                print(f"         ↳ Colonists placed → (none placed or already recalled)")


    # ──────────────────────── GAME END ────────────────────────
    print(f"\n{'═'*80}")
    print(f"  GAME OVER — FINAL RESULTS")
    print(f"{'═'*80}")
    scores = game.get_scores()
    winner_idx = max(range(3), key=lambda i: scores[i][0] + scores[i][1] * 0.0001)

    for i in range(3):
        vp, tb = scores[i]
        winner_tag = " ★ WINNER" if i == winner_idx else ""
        print(f"\n  Player {i}{winner_tag}")
        print(f"    Total VP: {vp}  (Tiebreaker: {tb})")
        p = game.players[i]
        print(f"    Doubloons: {p.doubloons}")
        goods_str = ", ".join([f"{GOOD_NAMES[g]}: {a}" for g, a in p.goods.items() if a > 0])
        print(f"    Goods: {goods_str if goods_str else '(none)'}")
        print(f"    VP Chips earned: {p.vp_chips}")

        # Island
        island_summary = {}
        for t in p.island_board:
            name = TILE_NAMES.get(t.tile_type, "?")
            occupied = "✓" if t.is_occupied else "✗"
            key = f"{name} [{occupied}]"
            island_summary[key] = island_summary.get(key, 0) + 1
        island_str = ", ".join([f"{k}×{v}" if v > 1 else k for k, v in island_summary.items()])
        print(f"    Island: {island_str}")

        # Buildings
        building_list = []
        building_vp = 0
        for b in p.city_board:
            if b.building_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                continue
            bname = BUILDING_NAMES[b.building_type]
            active = "✓" if b.colonists > 0 else "✗"
            building_vp += BUILDING_DATA[b.building_type][1]
            building_list.append(f"{bname} [{active}]")
        print(f"    Buildings ({building_vp} base VP): {', '.join(building_list) if building_list else '(none)'}")

    print(f"\n  Total game steps: {step_count}")
    print(f"{'═'*80}\n")

    # ──────────────────────── Save JSON Log ────────────────────────
    timestamp = int(time.time())
    log_dir = "logs/replay"
    os.makedirs(log_dir, exist_ok=True)
    log_path = f"{log_dir}/replay_seed{seed}_{timestamp}.json"

    output = {
        "ppo_model": os.path.basename(model_path),
        "architecture": arch_name,
        "seed": seed,
        "players": [
            {"seat": i, "label": labels[i], "is_ppo": is_ppo_flags[i]}
            for i in range(3)
        ],
        "num_players": 3,
        "total_steps": step_count,
        "final_scores": [
            {"player": i, "label": labels[i], "vp": scores[i][0],
             "tiebreaker": scores[i][1], "winner": i == winner_idx}
            for i in range(3)
        ],
        "entries": log_entries,
    }
    class NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    with open(log_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, cls=NumpyEncoder)
    print(f"  JSON log saved to: {log_path}")

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Puerto Rico Single Game Replay — PPO vs configurable bots",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Player seats are fixed:
  Player 0 = PPO Agent (always)
  Player 1 = --bot1  (default: shipping)
  Player 2 = --bot2  (default: factory)

Available bot types: {', '.join(BOT_OPTIONS)}

Examples:
  # PPO vs Shipping vs Factory (default)
  python evaluate/replay_single_game.py --model_path models/.../model.pth

  # PPO vs two random bots
  python evaluate/replay_single_game.py --model_path models/.../model.pth --bot1 random --bot2 random

  # PPO vs Factory vs Shipping
  python evaluate/replay_single_game.py --model_path models/.../model.pth --bot1 factory --bot2 shipping
"""
    )
    parser.add_argument("--model_path", type=str, required=True,
                        help="Path to PPO agent .pth checkpoint")
    parser.add_argument("--bot1", type=str, default="shipping",
                        choices=BOT_OPTIONS,
                        help="Opponent in seat 1 (default: shipping)")
    parser.add_argument("--bot2", type=str, default="factory",
                        choices=BOT_OPTIONS,
                        help="Opponent in seat 2 (default: factory)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    args = parser.parse_args()

    run_replay(args.model_path, args.seed, bot1=args.bot1, bot2=args.bot2)
