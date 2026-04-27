"""
Semantic293TypeMayorAdapter — 현재 293-dim semantic obs + type mayor 모델용 adapter.

이 adapter는 pr_env.py의 semantic obs (3인 게임, 293 dims)와 200-dim
action space를 그대로 재현하여 backend canonical state/action에 매핑한다.

obs 구조 (sorted alphabetical, 3 players):
  global_state (74 dims):
    cargo_ships_good_onehot(18), cargo_ships_load(3), cargo_ships_space(3),
    colonists_ship(1), colonists_supply(1), current_phase_onehot(10),
    current_player(1), face_up_plantation_counts(6), game_progress(1),
    goods_supply(5), governor_idx(1), quarry_stack(1), role_doubloons(8),
    roles_available(8), trading_house_count(1), trading_house_has_good(5),
    vp_chips(1)
  per player (73 dims):
    building_colonists(23), doubloons(1), empty_city_spaces(1), goods(5),
    has_building(23), island_empty_spaces(1), island_tile_count(6),
    island_tile_occupied(6), production_capacity(5),
    unplaced_colonists(1), vp_chips(1)
  Total: 74 + 73*3 = 293
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from common.base_adapter import DecodeResult, PolicyAdapter

# Good enum (and tile-good) order: COFFEE=0, TOBACCO=1, CORN=2, SUGAR=3, INDIGO=4
GOOD_ENUM_ORDER = ["coffee", "tobacco", "corn", "sugar", "indigo"]
TILE_TYPES_FOR_COUNT = [0, 1, 2, 3, 4, 5]  # coffee, tobacco, corn, sugar, indigo, quarry

NUM_BUILDING_TYPES = 23
NUM_GOODS = 5
NUM_PHASES = 10  # 0-8 + index 9 = None/INIT
NUM_ROLES = 8
NUM_SHIPS = 3
GOOD_ONEHOT_CLASSES = 6  # 5 goods + 1 empty


def _to_int_key(d: Dict[Any, Any], key: int) -> Optional[Any]:
    """JSON round-trip 시 dict key가 str일 수도 있어 int/str 양쪽을 시도한다."""
    if key in d:
        return d[key]
    skey = str(key)
    if skey in d:
        return d[skey]
    return None


def _get_int_keyed(d: Dict[Any, Any], key: int, default: Any = 0) -> Any:
    val = _to_int_key(d, key)
    return default if val is None else val


class Semantic293TypeMayorAdapter(PolicyAdapter):
    """293-dim semantic + type-mayor 200-action adapter."""

    @property
    def adapter_id(self) -> str:
        return "puco.semantic293.type_mayor.v1"

    @property
    def canonical_state_version(self) -> str:
        return "castone.canonical-state.v1"

    @property
    def canonical_action_version(self) -> str:
        return "castone.canonical-action.v1"

    @property
    def obs_dim(self) -> int:
        return 293

    @property
    def action_dim(self) -> int:
        return 200

    # ── encode_obs ────────────────────────────────────────────────────────
    def encode_obs(self, state: Dict[str, Any], player_idx: int) -> np.ndarray:
        g = state["global"]
        meta = state["meta"]
        players = state["players"]
        num_players = int(meta["num_players"])

        obs: List[float] = []

        # cargo_ships_good_onehot (18)
        ships = g["cargo_ships"]
        for i in range(NUM_SHIPS):
            onehot = [0.0] * GOOD_ONEHOT_CLASSES
            if i < len(ships):
                good = ships[i]["good"]
                if good is not None and good in GOOD_ENUM_ORDER:
                    onehot[GOOD_ENUM_ORDER.index(good)] = 1.0
                else:
                    onehot[5] = 1.0  # empty class
            else:
                onehot[5] = 1.0
            obs.extend(onehot)

        # cargo_ships_load (3)
        for i in range(NUM_SHIPS):
            obs.append(float(ships[i]["load"]) if i < len(ships) else 0.0)

        # cargo_ships_space (3)
        for i in range(NUM_SHIPS):
            obs.append(float(ships[i]["space"]) if i < len(ships) else 0.0)

        # colonists_ship (1)
        obs.append(float(g["colonist_ship"]))

        # colonists_supply (1)
        obs.append(float(g["colonist_supply"]))

        # current_phase_onehot (10)
        phase_onehot = [0.0] * NUM_PHASES
        phase_id = int(meta["phase_id"])
        if 0 <= phase_id < NUM_PHASES:
            phase_onehot[phase_id] = 1.0
        else:
            phase_onehot[9] = 1.0
        obs.extend(phase_onehot)

        # current_player (1)
        obs.append(float(meta["current_player_idx"]))

        # face_up_plantation_counts (6) — count per tile_type 0..5, env skips EMPTY(=6)
        face_up_counts = [0.0] * 6
        for tile_type in g["face_up_plantations"]:
            if 0 <= tile_type < 6:
                face_up_counts[tile_type] += 1.0
        obs.extend(face_up_counts)

        # game_progress (1)
        obs.append(float(g["game_progress"]))

        # goods_supply (5) — env order: Good enum index 0..4
        for i in range(NUM_GOODS):
            obs.append(float(g["goods_supply"].get(GOOD_ENUM_ORDER[i], 0)))

        # governor_idx (1)
        obs.append(float(meta["governor_idx"]))

        # quarry_stack (1)
        obs.append(float(g["quarry_supply"]))

        # role_doubloons (8)
        for role_id in range(NUM_ROLES):
            obs.append(float(_get_int_keyed(g["role_doubloons"], role_id, 0)))

        # roles_available (8)
        available_set = set(int(r) for r in g["available_roles"])
        for role_id in range(NUM_ROLES):
            obs.append(1.0 if role_id in available_set else 0.0)

        # trading_house_count (1)
        obs.append(float(g["trading_house_count"]))

        # trading_house_has_good (5) — env order: Good enum index 0..4
        th_goods = set(g["trading_house"])
        for i in range(NUM_GOODS):
            obs.append(1.0 if GOOD_ENUM_ORDER[i] in th_goods else 0.0)

        # vp_chips (1)
        obs.append(float(g["vp_supply"]))

        # ── per-player features (73 × num_players) ──
        for pidx in range(num_players):
            p = players[pidx]

            # building_colonists (23)
            for bt in range(NUM_BUILDING_TYPES):
                obs.append(float(_get_int_keyed(p["building_colonists"], bt, 0)))

            # doubloons (1)
            obs.append(float(p["doubloons"]))

            # empty_city_spaces (1)
            obs.append(float(p["empty_city_spaces"]))

            # goods (5)
            for i in range(NUM_GOODS):
                obs.append(float(p["goods"].get(GOOD_ENUM_ORDER[i], 0)))

            # has_building (23)
            for bt in range(NUM_BUILDING_TYPES):
                val = _get_int_keyed(p["has_building"], bt, False)
                obs.append(1.0 if val else 0.0)

            # island_empty_spaces (1)
            obs.append(float(p["empty_island_spaces"]))

            # island_tile_count (6)
            for tt in TILE_TYPES_FOR_COUNT:
                obs.append(float(_get_int_keyed(p["island_tile_counts"], tt, 0)))

            # island_tile_occupied (6)
            for tt in TILE_TYPES_FOR_COUNT:
                obs.append(float(_get_int_keyed(p["island_tile_occupied"], tt, 0)))

            # production_capacity (5)
            for i in range(NUM_GOODS):
                obs.append(float(p["production_capacity"].get(GOOD_ENUM_ORDER[i], 0)))

            # unplaced_colonists (1)
            obs.append(float(p["unplaced_colonists"]))

            # vp_chips (1)
            obs.append(float(p["vp_chips"]))

        result = np.asarray(obs, dtype=np.float32)
        if result.shape != (293,):
            raise ValueError(f"Expected 293 dims, got {result.shape}")
        return result

    # ── encode_action_mask ────────────────────────────────────────────────
    def encode_action_mask(
        self,
        state: Dict[str, Any],
        legal_actions: List[Dict[str, Any]],
    ) -> np.ndarray:
        mask = np.zeros(self.action_dim, dtype=np.float32)
        for entry in legal_actions:
            action_idx = int(entry["engine_action"])
            if 0 <= action_idx < self.action_dim:
                mask[action_idx] = 1.0
        return mask

    # ── decode_action ─────────────────────────────────────────────────────
    def decode_action(
        self,
        model_action_idx: int,
        state: Dict[str, Any],
        legal_actions: List[Dict[str, Any]],
    ) -> DecodeResult:
        legal_engine_actions = {int(e["engine_action"]): e for e in legal_actions}

        if model_action_idx in legal_engine_actions:
            entry = legal_engine_actions[model_action_idx]
            return DecodeResult(
                engine_action=model_action_idx,
                canonical_id=entry.get("canonical_id", ""),
            )

        # fallback: same category 내 deterministic 선택 (lowest engine_action)
        target_category = self._infer_category(model_action_idx)
        same_category = [
            e for e in legal_actions if e["category"] == target_category
        ]
        if same_category:
            picked = min(same_category, key=lambda e: int(e["engine_action"]))
            return DecodeResult(
                engine_action=int(picked["engine_action"]),
                canonical_id=picked.get("canonical_id", ""),
                fallback_used=True,
                fallback_reason="exact_match_missing",
            )

        if legal_actions:
            first = min(legal_actions, key=lambda e: int(e["engine_action"]))
            return DecodeResult(
                engine_action=int(first["engine_action"]),
                canonical_id=first.get("canonical_id", ""),
                fallback_used=True,
                fallback_reason="illegal_model_action",
            )

        return DecodeResult(
            engine_action=15,
            canonical_id="pass",
            fallback_used=True,
            fallback_reason="adapter_guard_triggered",
        )

    @staticmethod
    def _infer_category(action_idx: int) -> str:
        if 0 <= action_idx <= 7:
            return "role"
        if 8 <= action_idx <= 14:
            return "settler"
        if action_idx == 15:
            return "pass"
        if 16 <= action_idx <= 38:
            return "builder"
        if 39 <= action_idx <= 43:
            return "trader"
        if 44 <= action_idx <= 63:
            return "captain"
        if 64 <= action_idx <= 68:
            return "store"
        if 93 <= action_idx <= 97:
            return "craftsman"
        if action_idx == 105:
            return "settler"
        if 106 <= action_idx <= 110:
            return "store"
        if 120 <= action_idx <= 125:
            return "mayor"
        if 140 <= action_idx <= 162:
            return "mayor"
        return "unknown"
