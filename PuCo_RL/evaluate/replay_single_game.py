"""
replay_single_game.py — Puerto Rico Single Game Replay & Analysis Tool

Replays a single game with configurable agents, providing detailed
terminal + JSON logs for strategy analysis.

Features:
  - 3 PPO self-play (--mode selfplay)
  - PPO vs heuristic bot (--mode vs_bot --bot_type shipping/actionvalue/tradebuilding)
  - Flexible PPO seat assignment (--ppo_seat 0/1/2)
  - Detailed per-step decision log with confidence/alternatives
  - Per-round state snapshots
  - Post-game analysis: VP timeline, role distribution, strategy profile
  - JSON log for offline analysis

Usage Examples:
  # PPO self-play (3 PPO agents)
  python evaluate/replay_single_game.py selfplay --model_path models/.../model.pth

  # PPO (seat 0,2) vs ShippingRush (seat 1)
  python evaluate/replay_single_game.py vs_bot --model_path models/.../model.pth \\
      --bot_type shipping --ppo_seat 0

  # PPO (seat 1) vs ActionValue (seats 0,2)
  python evaluate/replay_single_game.py vs_bot --model_path models/.../model.pth \\
      --bot_type actionvalue --ppo_seat 1

  # PPO vs TradeBuilding
  python evaluate/replay_single_game.py vs_bot --model_path models/.../model.pth \\
      --bot_type tradebuilding --ppo_seat 2
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import argparse
import io
import json
import re
import time
import torch
import numpy as np
from typing import Optional, Dict, List, Any, Tuple
from collections import defaultdict

from env.pr_env import PuertoRicoEnv
from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim
from agents.ppo_agent import PhasePPOAgent, Agent as PPOAgent
from agents.shipping_rush_agent import ShippingRushAgent
from agents.factory_rule_based_agent import FactoryRuleBasedAgent
from agents.action_value_agent import ActionValueAgent
from agents.trade_building_agent import TradeBuildingAgent
from agents.heuristic_bots import RandomBot
from configs.constants import (
    Phase, Role, Good, TileType, BuildingType, BUILDING_DATA, GOOD_PRICES,
    MayorStrategy, MAYOR_STRATEGY_BUILDINGS
)


# ──────────────────────── ANSI Color Helpers ────────────────────────
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return _ANSI_RE.sub('', text)


class TeeWriter:
    """Duplicates writes to both the real stdout and an in-memory buffer."""
    def __init__(self, original_stdout):
        self.terminal = original_stdout
        self.buffer = io.StringIO()

    def write(self, data: str):
        self.terminal.write(data)
        self.buffer.write(data)

    def flush(self):
        self.terminal.flush()

    def getvalue(self) -> str:
        return self.buffer.getvalue()


class C:
    """ANSI color codes for terminal output."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    # Foreground
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"
    # Bright
    BRED    = "\033[91m"
    BGREEN  = "\033[92m"
    BYELLOW = "\033[93m"
    BBLUE   = "\033[94m"
    BMAGENTA= "\033[95m"
    BCYAN   = "\033[96m"

# Player colors (for distinguishing 3 players)
PLAYER_COLORS = [C.BGREEN, C.BBLUE, C.BYELLOW]

# Bot type configurations
BOT_OPTIONS = ["shipping", "actionvalue", "tradebuilding", "factory", "random"]

BOT_LABELS = {
    "ppo":           "PPO Agent",
    "shipping":      "ShippingRush",
    "actionvalue":   "ActionValue",
    "tradebuilding": "TradeBuilding",
    "factory":       "FactoryBot",
    "random":        "Random",
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
def decode_action(action: int, game, player_idx: int | None = None) -> str:
    """Translate action int to human-readable string.
    
    Args:
        action: Action integer.
        game: Game state object.
        player_idx: Current player index (needed for Mayor slot resolution).
    """
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
        strategy = MayorStrategy(action - 69)
        strategy_labels = {
            MayorStrategy.CAPTAIN_FOCUS:       "Shipping Focus",
            MayorStrategy.TRADE_FACTORY_FOCUS: "Trade/Factory Focus",
            MayorStrategy.BUILDING_FOCUS:      "Building Focus",
        }
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
    # Mayor colonist placement actions (island: 120-131, city: 140-151)
    elif 120 <= action <= 131:
        slot = action - 120
        if player_idx is not None:
            p = game.players[player_idx]
            if slot < len(p.island_board):
                tile = p.island_board[slot]
                tname = TILE_NAMES.get(tile.tile_type, str(tile.tile_type))
                return f"Mayor: Colonist → {tname} (island #{slot})"
        return f"Mayor: Colonist → island slot {slot}"
    elif 140 <= action <= 151:
        slot = action - 140
        if player_idx is not None:
            p = game.players[player_idx]
            if slot < len(p.city_board):
                b = p.city_board[slot]
                if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                    bname = BUILDING_NAMES[b.building_type]
                    return f"Mayor: Colonist → {bname} (city #{slot})"
        return f"Mayor: Colonist → building slot {slot}"
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
    building_vp = 0
    for b in player.city_board:
        if b.building_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
            continue
        bdata = BUILDING_DATA[b.building_type]
        buildings.append({
            "building": BUILDING_NAMES[b.building_type],
            "colonists": b.colonists,
            "max_colonists": bdata[2],
            "active": b.colonists > 0,
            "vp": bdata[1],
        })
        building_vp += bdata[1]
    goods = {GOOD_NAMES[g]: amt for g, amt in player.goods.items() if amt > 0}
    total_goods = sum(player.goods.values())
    return {
        "player_idx": player_idx,
        "doubloons": player.doubloons,
        "vp_chips": player.vp_chips,
        "building_vp": building_vp,
        "total_vp_estimate": player.vp_chips + building_vp,
        "unplaced_colonists": player.unplaced_colonists,
        "goods": goods if goods else {},
        "total_goods": total_goods,
        "island_tiles": len([t for t in player.island_board if t.tile_type != TileType.EMPTY]),
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
        "trading_house": trading_house if trading_house else [],
        "face_up_plantations": face_up,
        "quarries_left": game.quarry_stack,
        "available_roles": avail_roles,
        "role_bonuses": role_bonus if role_bonus else {},
        "governor": f"Player {game.governor_idx}",
    }


def player_state_bar(player, player_idx: int, label: str, is_ppo: bool) -> str:
    """One-line compact player state for round headers."""
    pc = PLAYER_COLORS[player_idx]
    ppo_tag = f"{C.BOLD}★{C.RESET}" if is_ppo else " "
    goods_parts = []
    for g in Good:
        amt = player.goods[g]
        if amt > 0:
            goods_parts.append(f"{GOOD_NAMES[g][:3]}:{amt}")
    goods_str = ", ".join(goods_parts) if goods_parts else "—"
    bldg_count = sum(1 for b in player.city_board
                     if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE))
    island_count = sum(1 for t in player.island_board if t.tile_type != TileType.EMPTY)
    return (f"  {ppo_tag} {pc}P{player_idx}({label:<14s}){C.RESET} "
            f"VP:{player.vp_chips:<3d} ${player.doubloons:<3d} "
            f"Goods:[{goods_str}] "
            f"Island:{island_count}/12 City:{bldg_count}/12")


# ──────────────────────── Strategic Commentary ────────────────────────
def comment_role_selection(role: Role, player, game) -> str:
    """Provide strategic commentary on role selection."""
    comments = []
    if role == Role.CRAFTSMAN:
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


def build_bot(bot_type: str, action_dim: int, env=None, ppo_model=None, is_phase: bool = False):
    """Return (agent_obj, is_ppo_flag, is_phase_flag, label)."""
    if bot_type == "ppo":
        assert ppo_model is not None
        return ppo_model, True, is_phase, BOT_LABELS["ppo"]
    elif bot_type == "shipping":
        return ShippingRushAgent(action_dim, fixed_strategy=0).eval(), False, False, BOT_LABELS["shipping"]
    elif bot_type == "actionvalue":
        agent = ActionValueAgent(action_dim).eval()
        if env is not None:
            agent.set_env(env)
        return agent, False, False, BOT_LABELS["actionvalue"]
    elif bot_type == "tradebuilding":
        agent = TradeBuildingAgent(action_dim).eval()
        if env is not None:
            agent.set_env(env)
        return agent, False, False, BOT_LABELS["tradebuilding"]
    elif bot_type == "factory":
        return FactoryRuleBasedAgent(action_dim).eval(), False, False, BOT_LABELS["factory"]
    elif bot_type == "random":
        return RandomBot(action_dim).eval(), False, False, BOT_LABELS["random"]
    else:
        raise ValueError(f"Unknown bot type: '{bot_type}'. Choose from: {BOT_OPTIONS}")


def get_bot_action(agent, is_ppo: bool, is_phase: bool, obs, env) -> tuple:
    """
    Unified action getter.
    Returns (action_int, top_k_list, value_float, entropy_float).
    top_k, value, and entropy are only meaningful for PPO agents.
    """
    flat_obs = flatten_dict_observation(
        obs["observation"],
        env.observation_space("player_0")["observation"]
    )
    mask = obs["action_mask"]
    phase_id = int(np.argmax(obs["observation"]["global_state"]["current_phase_onehot"]))
    player_idx = int(obs["observation"]["global_state"]["current_player"][0])
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

            # Entropy of the valid action distribution
            valid_probs = probs[mask_bool > 0.5]
            entropy = -torch.sum(valid_probs * torch.log(valid_probs + 1e-8)).item()

            valid_indices = np.where(mask == 1)[0]
            top_k = sorted([(int(i), probs[i].item()) for i in valid_indices],
                           key=lambda x: x[1], reverse=True)[:5]
            return action, top_k, value, entropy

        else:
            # Rule-based / heuristic bots
            if isinstance(agent, (ActionValueAgent, TradeBuildingAgent)):
                act_t, _, _, _ = agent.get_action_and_value(
                    obs_t, mask_t,
                    obs_dict=obs["observation"], player_idx=int(player_idx)
                )
            elif isinstance(agent, (ShippingRushAgent, FactoryRuleBasedAgent)):
                act_t, _, _, _ = agent.get_action_and_value(
                    obs_t, mask_t,
                    obs_dict=obs["observation"], player_idx=int(player_idx)
                )
            else:
                act_t, _, _, _ = agent.get_action_and_value(obs_t, mask_t)
            return int(act_t.item()), [], 0.0, 0.0


# ──────────────────────── Analysis Helpers ────────────────────────
def compute_game_analysis(log_entries: List[Dict], labels: List[str],
                         is_ppo_flags: List[bool], scores: list,
                         game) -> Dict[str, Any]:
    """Compute post-game analysis metrics."""
    analysis = {}
    num_players = 3

    # 1. Role selection distribution per player
    role_counts: Dict[int, Dict[str, int]] = {i: defaultdict(int) for i in range(num_players)}
    for entry in log_entries:
        if "role_selected" in entry:
            role_counts[entry["player"]][entry["role_selected"]] += 1

    role_distributions = {}
    for i in range(num_players):
        total = sum(role_counts[i].values())
        dist = {}
        for role_name in ["Settler", "Mayor", "Builder", "Craftsman", "Trader", "Captain", "Prospector", "Prospector2"]:
            cnt = role_counts[i].get(role_name, 0)
            dist[role_name] = {"count": cnt, "pct": f"{cnt / max(total, 1) * 100:.1f}%"}
        role_distributions[f"P{i}({labels[i]})"] = dist
    analysis["role_selection"] = role_distributions

    # 2. VP timeline (track VP chip gains per round)
    vp_timeline: Dict[int, Dict[int, int]] = defaultdict(lambda: {i: 0 for i in range(num_players)})
    # We can approximate from final VP chips
    analysis["final_vp_chips"] = {f"P{i}({labels[i]})": game.players[i].vp_chips for i in range(num_players)}

    # 3. VP decomposition
    vp_decomp = {}
    for i in range(num_players):
        p = game.players[i]
        chip_vp = p.vp_chips
        building_vp = sum(BUILDING_DATA[b.building_type][1]
                         for b in p.city_board
                         if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE))
        # Large building bonus estimation
        large_bonus = 0
        for b in p.city_board:
            bt = b.building_type
            if bt in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                continue
            if not BUILDING_DATA[bt][4]:  # not is_large
                continue
            if b.colonists == 0:
                continue
            if bt == BuildingType.CUSTOMS_HOUSE:
                large_bonus += chip_vp // 4
            elif bt == BuildingType.FORTRESS:
                total_col = (p.unplaced_colonists +
                            sum(1 for tb in p.island_board if tb.is_occupied) +
                            sum(cb.colonists for cb in p.city_board
                                if cb.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)))
                large_bonus += total_col // 3
            elif bt == BuildingType.GUILDHALL:
                num_small_prod = sum(1 for bb in p.city_board if bb.building_type.value in (0, 1))
                num_large_prod = sum(1 for bb in p.city_board if bb.building_type.value in (2, 3, 4, 5))
                large_bonus += num_small_prod + num_large_prod * 2
            elif bt == BuildingType.RESIDENCE:
                n_tiles = sum(1 for tb in p.island_board if tb.tile_type != TileType.EMPTY)
                if n_tiles <= 9:
                    large_bonus += 4
                elif n_tiles == 10:
                    large_bonus += 5
                elif n_tiles == 11:
                    large_bonus += 6
                else:
                    large_bonus += 7
            elif bt == BuildingType.CITY_HALL:
                num_violet = sum(1 for bb in p.city_board
                                if bb.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
                                and bb.building_type.value >= 6)
                large_bonus += num_violet

        total_vp = scores[i][0]
        vp_decomp[f"P{i}({labels[i]})"] = {
            "total_vp": total_vp,
            "shipping_vp (chips)": chip_vp,
            "building_base_vp": building_vp,
            "large_building_bonus": large_bonus,
            "tiebreaker": scores[i][1],
            "ship_pct": f"{chip_vp / max(total_vp, 1) * 100:.1f}%",
            "bldg_pct": f"{(building_vp + large_bonus) / max(total_vp, 1) * 100:.1f}%",
        }
    analysis["vp_decomposition"] = vp_decomp

    # 4. Phase action counts per player (how often each player acted in each phase)
    phase_counts: Dict[int, Dict[str, int]] = {i: defaultdict(int) for i in range(num_players)}
    for entry in log_entries:
        phase_counts[entry["player"]][entry["phase"]] += 1
    analysis["phase_action_counts"] = {
        f"P{i}({labels[i]})": dict(phase_counts[i]) for i in range(num_players)
    }

    # 5. PPO-specific: Average confidence & value estimate
    for i in range(num_players):
        if not is_ppo_flags[i]:
            continue
        ppo_entries = [e for e in log_entries if e["player"] == i and e.get("top_actions")]
        if ppo_entries:
            confs = [e["top_actions"][0]["prob"] for e in ppo_entries if e["top_actions"]]
            vals = [e["value_estimate"] for e in ppo_entries]
            analysis[f"ppo_P{i}_metrics"] = {
                "avg_confidence": round(np.mean(confs), 4),
                "min_confidence": round(np.min(confs), 4),
                "avg_value": round(np.mean(vals), 4),
                "value_trend_start": round(np.mean(vals[:5]), 4) if len(vals) >= 5 else round(np.mean(vals), 4),
                "value_trend_end": round(np.mean(vals[-5:]), 4) if len(vals) >= 5 else round(np.mean(vals), 4),
                "total_decisions": len(ppo_entries),
            }

    # 6. Key decision points (low-confidence PPO decisions)
    key_decisions = []
    for entry in log_entries:
        if entry.get("top_actions") and len(entry["top_actions"]) >= 2:
            top_prob = entry["top_actions"][0]["prob"]
            second_prob = entry["top_actions"][1]["prob"]
            # Flag decisions where PPO was uncertain (top choice < 60% or close alternatives)
            if top_prob < 0.60 or (top_prob - second_prob) < 0.20:
                key_decisions.append({
                    "step": entry["step"],
                    "round": entry["round"],
                    "phase": entry["phase"],
                    "chosen": entry["action"],
                    "confidence": round(top_prob, 4),
                    "alternative": entry["top_actions"][1]["action"],
                    "alt_prob": round(second_prob, 4),
                    "value": entry["value_estimate"],
                })
    analysis["key_decision_points"] = key_decisions[:20]  # Limit to top 20

    return analysis


# ──────────────────────── Main Replay Loop ────────────────────────
def run_replay(model_path: str, seed: int = 42,
               mode: str = "selfplay",
               bot_type: str = "shipping",
               ppo_seat: int = 0):
    # Tee stdout to capture terminal log for .txt file output
    tee = TeeWriter(sys.stdout)
    sys.stdout = tee

    env = PuertoRicoEnv(num_players=3, max_game_steps=1500)
    obs_space = env.observation_space("player_0")["observation"]
    obs_dim   = get_flattened_obs_dim(obs_space)
    action_dim = env.action_space("player_0").n

    ppo_model, is_phase = load_model(model_path, obs_dim, action_dim)
    arch_name = "PhasePPOAgent" if is_phase else "PPOAgent"

    agents: list = [None, None, None]
    is_ppo_flags: list[bool]   = [False, False, False]
    is_phase_flags: list[bool] = [False, False, False]
    labels: list[str]          = ["", "", ""]

    if mode == "selfplay":
        # All 3 seats are PPO
        for i in range(3):
            agents[i], is_ppo_flags[i], is_phase_flags[i], labels[i] = build_bot(
                "ppo", action_dim, env=env, ppo_model=ppo_model, is_phase=is_phase
            )
            labels[i] = f"PPO_{i}"
    elif mode == "vs_bot":
        # PPO occupies ppo_seat, bot fills the other two seats
        for i in range(3):
            if i == ppo_seat:
                agents[i], is_ppo_flags[i], is_phase_flags[i], labels[i] = build_bot(
                    "ppo", action_dim, env=env, ppo_model=ppo_model, is_phase=is_phase
                )
            else:
                agents[i], is_ppo_flags[i], is_phase_flags[i], labels[i] = build_bot(
                    bot_type, action_dim, env=env, ppo_model=ppo_model, is_phase=is_phase
                )
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # ── Print Header ──────────────────────────────────────────────────────
    print(f"\n{C.BOLD}{'═' * 80}{C.RESET}")
    print(f"  {C.BOLD}{C.CYAN}PUERTO RICO — SINGLE GAME REPLAY LOG{C.RESET}")
    print(f"  {C.DIM}PPO Model : {os.path.basename(model_path)}  ({arch_name}){C.RESET}")
    print(f"  {C.DIM}Mode      : {mode.upper()}{C.RESET}")
    if mode == "vs_bot":
        print(f"  {C.DIM}Bot Type  : {bot_type}{C.RESET}")
    for i in range(3):
        pc = PLAYER_COLORS[i]
        ppo_tag = f" {C.BOLD}← PPO{C.RESET}" if is_ppo_flags[i] else ""
        print(f"  {pc}Player {i}  : {labels[i]}{ppo_tag}{C.RESET}")
    print(f"  {C.DIM}Seed      : {seed}{C.RESET}")
    print(f"{C.BOLD}{'═' * 80}{C.RESET}\n")

    env.reset(seed=seed)
    game = env.game

    # Update env reference for ActionValueAgent/TradeBuildingAgent after reset
    for a in agents:
        if isinstance(a, ActionValueAgent):
            a.set_env(env)
        if callable(getattr(a, "reset_strategy", None)):
            a.reset_strategy()

    log_entries: List[Dict[str, Any]] = []
    round_snapshots: List[Dict[str, Any]] = []
    step_count = 0
    round_num = 0
    last_governor_idx = game.governor_idx

    # Tracking
    role_selection_tracker: Dict[int, Dict[str, int]] = {i: defaultdict(int) for i in range(3)}
    vp_timeline: List[Dict[str, Any]] = []

    # ── Initial Setup ─────────────────────────────────────────────────────
    print(f"  {C.DIM}{'─' * 76}{C.RESET}")
    print(f"  {C.BOLD}INITIAL SETUP{C.RESET}")
    print(f"  {C.DIM}{'─' * 76}{C.RESET}")
    print(f"  Governor: Player {game.governor_idx}")
    for i in range(3):
        p = game.players[i]
        tiles = [TILE_NAMES.get(t.tile_type, "?") for t in p.island_board if t.tile_type != TileType.EMPTY]
        pc = PLAYER_COLORS[i]
        print(f"  {pc}P{i}({labels[i]:<14s}){C.RESET}: "
              f"${p.doubloons} doubloons, Island: {', '.join(tiles)}")
    print()

    for agent_id in env.agent_iter():
        obs, reward, termination, truncation, info = env.last()

        if termination or truncation:
            env.step(None)
            continue

        player_idx = int(agent_id.split("_")[1])
        current_phase = game.current_phase

        # ── Round boundary detection ─────────────────────────────────────
        current_governor = game.governor_idx
        if current_governor != last_governor_idx:
            round_num += 1
            last_governor_idx = current_governor

            # Capture round snapshot
            g_snap = snapshot_global(game)
            p_snaps = [snapshot_player(game.players[i], i) for i in range(3)]
            round_snapshots.append({
                "round": round_num,
                "global": g_snap,
                "players": p_snaps,
            })

            # VP timeline
            vp_timeline.append({
                "round": round_num,
                "vp_chips": [game.players[i].vp_chips for i in range(3)],
            })

            # Print round header
            print(f"\n{C.BOLD}{'═' * 80}{C.RESET}")
            print(f"  {C.BOLD}{C.WHITE}ROUND {round_num}{C.RESET}")
            print(f"{C.BOLD}{'═' * 80}{C.RESET}")
            print(f"  {C.DIM}Governor: {g_snap['governor']}  │  "
                  f"VP Pool: {g_snap['vp_pool']}  │  "
                  f"Colonist Supply: {g_snap['colonist_supply']}  │  "
                  f"Colonist Ship: {g_snap['colonist_ship']}{C.RESET}")
            for s in g_snap['cargo_ships']:
                load_bar = "█" * s['load'] + "░" * (s['capacity'] - s['load'])
                print(f"    {s['label']}: [{load_bar}] {s['load']}/{s['capacity']} ({s['good']})")
            if g_snap['role_bonuses']:
                bonus_str = ", ".join([f"{r}: +{d}" for r, d in g_snap['role_bonuses'].items()])
                print(f"  {C.YELLOW}Role Bonuses: {bonus_str}{C.RESET}")
            # Player state bars
            print(f"  {C.DIM}{'─' * 76}{C.RESET}")
            for i in range(3):
                print(player_state_bar(game.players[i], i, labels[i], is_ppo_flags[i]))
            print()

        # ── Dispatch to correct agent ────────────────────────────────────
        action, top_k, value, entropy = get_bot_action(
            agents[player_idx], is_ppo_flags[player_idx], is_phase_flags[player_idx], obs, env
        )
        action_str = decode_action(action, game, player_idx)
        player_label = labels[player_idx]

        # Build log entry
        entry = {
            "step": step_count,
            "round": round_num,
            "player": player_idx,
            "player_label": player_label,
            "is_ppo": is_ppo_flags[player_idx],
            "phase": current_phase.name if current_phase else "INIT",
            "action_id": action,
            "action": action_str,
            "value_estimate": round(value, 4),
            "entropy": round(entropy, 4),
            "top_actions": [
                {"action_id": a, "action": decode_action(a, game, player_idx), "prob": round(p, 4)}
                for a, p in top_k
            ],
        }

        # Phase-specific context
        commentary = ""
        if 0 <= action <= 7:
            role = Role(action)
            commentary = comment_role_selection(role, game.players[player_idx], game)
            entry["role_selected"] = ROLE_NAMES.get(role, str(role))
            role_selection_tracker[player_idx][ROLE_NAMES.get(role, str(role))] += 1

        # ── Print formatted log ──────────────────────────────────────────
        phase_label = current_phase.name if current_phase else "INIT"
        is_ppo_player = is_ppo_flags[player_idx]
        pc = PLAYER_COLORS[player_idx]

        if is_ppo_player:
            marker = f"{C.BOLD}{pc}▶{C.RESET}"
            action_color = C.BOLD
        else:
            marker = f" "
            action_color = C.DIM

        print(f"  {marker}[{step_count:4d}] {pc}P{player_idx}({player_label:<14s}){C.RESET} "
              f"│ {phase_label:15s} │ {action_color}{action_str}{C.RESET}")

        # Show top alternatives only for PPO agent
        if is_ppo_player and len(top_k) > 1:
            chosen_prob = top_k[0][1]
            alts = []
            for a_id, p in top_k[1:4]:
                alts.append(f"{decode_action(a_id, game, player_idx)} ({p:.1%})")
            conf_color = C.GREEN if chosen_prob >= 0.7 else (C.YELLOW if chosen_prob >= 0.4 else C.RED)
            print(f"         {C.DIM}↳ Confidence: {conf_color}{chosen_prob:.1%}{C.RESET}  "
                  f"{C.DIM}│  Alternatives: {', '.join(alts)}{C.RESET}")

        if commentary:
            print(f"         {C.DIM}↳ Context: {commentary}{C.RESET}")

        # Show value estimate for PPO player at key decisions
        if is_ppo_flags[player_idx] and current_phase in (
            Phase.END_ROUND, Phase.BUILDER, Phase.CAPTAIN, Phase.TRADER
        ):
            # Color value by optimism
            v_color = C.GREEN if value > 0.55 else (C.YELLOW if value > 0.45 else C.RED)
            print(f"         {C.DIM}↳ V(s) = {v_color}{value:.4f}{C.RESET}  "
                  f"{C.DIM}H = {entropy:.3f}{C.RESET}")

        # ── Capture state before step to detect auto-actions ─────
        pre_state = {}
        for i in range(3):
            p_obj = game.players[i]
            pre_state[i] = {
                "city_col": {
                    b.building_type: b.colonists for b in p_obj.city_board
                    if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE)
                },
                "island_occ": [t.is_occupied for t in p_obj.island_board],
                "island_tiles": [t.tile_type for t in p_obj.island_board]
            }

        entry["commentary"] = commentary
        log_entries.append(entry)
        step_count += 1

        env.step(action)

        # ── Detect silent auto-actions (Mayor placement, Hacienda) ─────
        for i in range(3):
            p_obj = game.players[i]
            old_s = pre_state[i]
            
            # Detect Colonist Placements
            gained_bldg = []
            for b in p_obj.city_board:
                bt = b.building_type
                if bt in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                    continue
                before = old_s["city_col"].get(bt, 0)
                after  = b.colonists
                if after > before:
                    bname = BUILDING_NAMES[bt]
                    gained_bldg.append(f"{bname} (+{after - before})")

            gained_tile = []
            for t_idx, t in enumerate(p_obj.island_board):
                if t_idx < len(old_s["island_occ"]) and not old_s["island_occ"][t_idx] and t.is_occupied:
                    tname = TILE_NAMES.get(t.tile_type, "?")
                    gained_tile.append(tname)

            parts = []
            if gained_bldg:
                parts.append("City: " + ", ".join(gained_bldg))
            if gained_tile:
                parts.append("Island: " + ", ".join(gained_tile))
            
            if parts:
                pc = PLAYER_COLORS[i]
                print(f"         {C.DIM}↳ {pc}P{i}{C.DIM} (Auto-Mayor) Colonists placed → {C.CYAN}{' │ '.join(parts)}{C.RESET}")

            # Detect Hacienda Draws
            old_tiles = old_s["island_tiles"]
            for t_idx, t in enumerate(p_obj.island_board):
                if t_idx < len(old_tiles):
                    if old_tiles[t_idx] == TileType.EMPTY and t.tile_type != TileType.EMPTY:
                        drawn_name = TILE_NAMES.get(t.tile_type, str(t.tile_type))
                        pc = PLAYER_COLORS[i]
                        print(f"         {C.DIM}↳ {pc}P{i}{C.DIM} (Auto-Hacienda) drew: {C.CYAN}{drawn_name}{C.RESET}")
                else:
                    drawn_name = TILE_NAMES.get(t.tile_type, str(t.tile_type))
                    pc = PLAYER_COLORS[i]
                    print(f"         {C.DIM}↳ {pc}P{i}{C.DIM} (Auto-Hacienda) drew: {C.CYAN}{drawn_name}{C.RESET}")


    # ──────────────────────── GAME END ────────────────────────
    scores = game.get_scores()
    winner_idx = max(range(3), key=lambda i: scores[i][0] + scores[i][1] * 0.0001)

    print(f"\n{C.BOLD}{'═' * 80}{C.RESET}")
    print(f"  {C.BOLD}{C.MAGENTA}GAME OVER — FINAL RESULTS{C.RESET}")
    print(f"{C.BOLD}{'═' * 80}{C.RESET}")

    for i in range(3):
        vp, tb = scores[i]
        pc = PLAYER_COLORS[i]
        winner_tag = f" {C.BOLD}{C.BYELLOW}★ WINNER{C.RESET}" if i == winner_idx else ""
        ppo_tag = f" {C.BOLD}[PPO]{C.RESET}" if is_ppo_flags[i] else ""
        print(f"\n  {pc}{C.BOLD}Player {i} — {labels[i]}{C.RESET}{ppo_tag}{winner_tag}")
        print(f"    {C.BOLD}Total VP: {vp}{C.RESET}  (Tiebreaker: {tb})")
        p = game.players[i]
        print(f"    Doubloons: {p.doubloons}")
        goods_str = ", ".join([f"{GOOD_NAMES[g]}: {a}" for g, a in p.goods.items() if a > 0])
        print(f"    Goods: {goods_str if goods_str else '(none)'}")
        print(f"    VP Chips earned: {p.vp_chips}")

        # Island
        island_summary = {}
        for t in p.island_board:
            if t.tile_type == TileType.EMPTY:
                continue
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

    # ──────────────────────── POST-GAME ANALYSIS ────────────────────────
    analysis = compute_game_analysis(log_entries, labels, is_ppo_flags, scores, game)

    print(f"\n{C.BOLD}{'═' * 80}{C.RESET}")
    print(f"  {C.BOLD}{C.CYAN}POST-GAME ANALYSIS{C.RESET}")
    print(f"{C.BOLD}{'═' * 80}{C.RESET}")

    # VP Decomposition
    print(f"\n  {C.BOLD}VP Decomposition:{C.RESET}")
    print(f"  {'Player':<28s} {'Total':>6s} {'Ship':>6s} {'Bldg':>6s} {'LgBon':>6s} {'Ship%':>6s} {'Bldg%':>6s}")
    print(f"  {'─' * 68}")
    for pkey, vd in analysis["vp_decomposition"].items():
        print(f"  {pkey:<28s} {vd['total_vp']:>6d} {vd['shipping_vp (chips)']:>6d} "
              f"{vd['building_base_vp']:>6d} {vd['large_building_bonus']:>6d} "
              f"{vd['ship_pct']:>6s} {vd['bldg_pct']:>6s}")

    # Role Selection Distribution
    print(f"\n  {C.BOLD}Role Selection Distribution:{C.RESET}")
    roles_header = ["Stlr", "Myr", "Bldr", "Cft", "Trd", "Capt", "Prs1", "Prs2"]
    role_full = ["Settler", "Mayor", "Builder", "Craftsman", "Trader", "Captain", "Prospector", "Prospector2"]
    print(f"  {'Player':<28s} " + "  ".join(f"{r:>5s}" for r in roles_header))
    print(f"  {'─' * 78}")
    for pkey, rd in analysis["role_selection"].items():
        row = "  ".join(f"{rd.get(rn, {}).get('count', 0):>5d}" for rn in role_full)
        print(f"  {pkey:<28s} {row}")

    # PPO-specific metrics
    for i in range(3):
        key = f"ppo_P{i}_metrics"
        if key in analysis:
            m = analysis[key]
            print(f"\n  {C.BOLD}PPO Agent P{i} Decision Metrics:{C.RESET}")
            print(f"    Total decisions: {m['total_decisions']}")
            print(f"    Avg confidence:  {m['avg_confidence']:.1%}  (min: {m['min_confidence']:.1%})")
            print(f"    Value estimate:  start={m['value_trend_start']:.4f} → end={m['value_trend_end']:.4f}")

    # Key Decision Points
    if analysis.get("key_decision_points"):
        print(f"\n  {C.BOLD}{C.YELLOW}Key Decision Points (uncertain/close calls):{C.RESET}")
        for kdp in analysis["key_decision_points"][:10]:
            print(f"    [{kdp['step']:4d}] R{kdp['round']} {kdp['phase']:15s} "
                  f"| {kdp['chosen']}")
            print(f"           {C.DIM}chose {kdp['confidence']:.1%} vs alt {kdp['alt_prob']:.1%}: "
                  f"{kdp['alternative']}  V(s)={kdp['value']:.4f}{C.RESET}")

    print(f"\n{C.BOLD}{'═' * 80}{C.RESET}\n")

    # ──────────────────────── Save JSON Log ────────────────────────
    timestamp = int(time.time())
    log_dir = "logs/replay"
    os.makedirs(log_dir, exist_ok=True)

    mode_tag = "selfplay" if mode == "selfplay" else f"vs_{bot_type}"
    log_path = f"{log_dir}/replay_{mode_tag}_seed{seed}_{timestamp}.json"

    output = {
        "metadata": {
            "ppo_model": os.path.basename(model_path),
            "architecture": arch_name,
            "seed": seed,
            "mode": mode,
            "bot_type": bot_type if mode == "vs_bot" else None,
            "ppo_seat": ppo_seat if mode == "vs_bot" else "all",
            "timestamp": timestamp,
        },
        "players": [
            {"seat": i, "label": labels[i], "is_ppo": is_ppo_flags[i]}
            for i in range(3)
        ],
        "total_steps": step_count,
        "total_rounds": round_num,
        "final_scores": [
            {"player": i, "label": labels[i], "vp": scores[i][0],
             "tiebreaker": scores[i][1], "winner": i == winner_idx}
            for i in range(3)
        ],
        "analysis": analysis,
        "round_snapshots": round_snapshots,
        "vp_timeline": vp_timeline,
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
    print(f"  {C.GREEN}JSON log saved to: {log_path}{C.RESET}")

    # ──────────────────────── Save Terminal Log (.txt) ────────────────────
    txt_path = log_path.replace(".json", ".txt")
    terminal_text = strip_ansi(tee.getvalue())
    sys.stdout = tee.terminal  # Restore original stdout before final print
    with open(txt_path, "w") as f:
        f.write(terminal_text)
    print(f"  {C.GREEN}Terminal log saved to: {txt_path}{C.RESET}")

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Puerto Rico Single Game Replay — PPO Strategy Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Modes:
  selfplay   3 PPO agents play against each other (PPO self-play analysis)
  vs_bot     PPO vs 2 heuristic bots of the same type

Available bot types: {', '.join(BOT_OPTIONS)}

Examples:
  # PPO self-play
  python evaluate/replay_single_game.py selfplay \\
      --model_path models/.../model.pth

  # PPO (seat 0) vs 2 ShippingRush bots
  python evaluate/replay_single_game.py vs_bot \\
      --model_path models/.../model.pth --bot_type shipping --ppo_seat 0

  # PPO (seat 1) vs 2 ActionValue bots
  python evaluate/replay_single_game.py vs_bot \\
      --model_path models/.../model.pth --bot_type actionvalue --ppo_seat 1

  # PPO (seat 2) vs 2 TradeBuilding bots
  python evaluate/replay_single_game.py vs_bot \\
      --model_path models/.../model.pth --bot_type tradebuilding --ppo_seat 2
"""
    )

    subparsers = parser.add_subparsers(dest="mode", required=True)

    # ── selfplay mode ─────────────────────────────────────────────────────
    p_self = subparsers.add_parser("selfplay", help="3 PPO agents self-play")
    p_self.add_argument("--model_path", type=str, required=True,
                        help="Path to PPO agent .pth checkpoint")
    p_self.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")

    # ── vs_bot mode ───────────────────────────────────────────────────────
    p_bot = subparsers.add_parser("vs_bot", help="PPO vs 2 heuristic bots")
    p_bot.add_argument("--model_path", type=str, required=True,
                       help="Path to PPO agent .pth checkpoint")
    p_bot.add_argument("--bot_type", type=str, default="shipping",
                       choices=BOT_OPTIONS,
                       help="Type of heuristic bot to play against (default: shipping)")
    p_bot.add_argument("--ppo_seat", type=int, default=0, choices=[0, 1, 2],
                       help="Seat index for the PPO agent (default: 0)")
    p_bot.add_argument("--seed", type=int, default=42,
                       help="Random seed (default: 42)")

    args = parser.parse_args()

    if args.mode == "selfplay":
        run_replay(args.model_path, args.seed, mode="selfplay")
    elif args.mode == "vs_bot":
        run_replay(args.model_path, args.seed, mode="vs_bot",
                   bot_type=args.bot_type, ppo_seat=args.ppo_seat)
