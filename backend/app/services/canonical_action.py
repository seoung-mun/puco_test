"""
CanonicalActionCatalog - legal actions를 의미 단위로 카탈로그화.

adapter가 semantic decode를 수행할 수 있도록
각 legal action에 canonical_id, category, detail을 부여한다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CANONICAL_ACTION_VERSION = "castone.canonical-action.v1"

# Good enum order: COFFEE=0, TOBACCO=1, CORN=2, SUGAR=3, INDIGO=4
GOOD_NAMES = {0: "coffee", 1: "tobacco", 2: "corn", 3: "sugar", 4: "indigo"}
ROLE_NAMES = {
    0: "settler", 1: "mayor", 2: "builder", 3: "craftsman",
    4: "trader", 5: "captain", 6: "prospector_1", 7: "prospector_2",
}
TILE_NAMES_WITH_QUARRY = {
    0: "coffee", 1: "tobacco", 2: "corn", 3: "sugar", 4: "indigo", 5: "quarry"
}


def _describe_action(action_idx: int, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """단일 action index를 canonical entry로 변환한다."""

    # Role selection: 0-7
    if 0 <= action_idx <= 7:
        role = ROLE_NAMES.get(action_idx, f"role_{action_idx}")
        return {
            "canonical_id": f"role:{role}",
            "engine_action": action_idx,
            "category": "role",
            "detail": {"role": role, "role_id": action_idx},
        }

    # Settler by tile type: 8-12 (8 + Good enum value)
    if 8 <= action_idx <= 12:
        tile_type = action_idx - 8
        tile_name = GOOD_NAMES.get(tile_type, f"tile_{tile_type}")
        return {
            "canonical_id": f"settler:tile_type:{tile_name}",
            "engine_action": action_idx,
            "category": "settler",
            "detail": {"tile_type": tile_type, "tile_name": tile_name},
        }

    # Settler quarry: 13 (8 + QUARRY=5) and 14 (legacy quarry)
    if action_idx in (13, 14):
        return {
            "canonical_id": "settler:quarry",
            "engine_action": action_idx,
            "category": "settler",
            "detail": {"quarry": True},
        }

    # Pass: 15
    if action_idx == 15:
        return {
            "canonical_id": "pass",
            "engine_action": 15,
            "category": "pass",
            "detail": {},
        }

    # Builder: 16-38
    if 16 <= action_idx <= 38:
        bt = action_idx - 16
        return {
            "canonical_id": f"builder:building:{bt}",
            "engine_action": action_idx,
            "category": "builder",
            "detail": {"building_type": bt},
        }

    # Trader: 39-43
    if 39 <= action_idx <= 43:
        good_id = action_idx - 39
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"trader:sell:{good}",
            "engine_action": action_idx,
            "category": "trader",
            "detail": {"good": good, "good_id": good_id},
        }

    # Captain load ship: 44-58
    if 44 <= action_idx <= 58:
        index = action_idx - 44
        ship_idx = index // 5
        good_id = index % 5
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"captain:load:{good}:ship:{ship_idx}",
            "engine_action": action_idx,
            "category": "captain",
            "detail": {
                "good": good, "good_id": good_id,
                "ship_idx": ship_idx, "wharf": False,
            },
        }

    # Captain wharf: 59-63
    if 59 <= action_idx <= 63:
        good_id = action_idx - 59
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"captain:wharf:{good}",
            "engine_action": action_idx,
            "category": "captain",
            "detail": {
                "good": good, "good_id": good_id,
                "ship_idx": -1, "wharf": True,
            },
        }

    # Store windrose: 64-68
    if 64 <= action_idx <= 68:
        good_id = action_idx - 64
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"store:windrose:{good}",
            "engine_action": action_idx,
            "category": "store",
            "detail": {"good": good, "good_id": good_id, "method": "windrose"},
        }

    # Craftsman privilege: 93-97
    if 93 <= action_idx <= 97:
        good_id = action_idx - 93
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"craftsman:privilege:{good}",
            "engine_action": action_idx,
            "category": "craftsman",
            "detail": {"good": good, "good_id": good_id},
        }

    # Hacienda: 105
    if action_idx == 105:
        return {
            "canonical_id": "settler:hacienda",
            "engine_action": 105,
            "category": "settler",
            "detail": {"hacienda": True},
        }

    # Store warehouse: 106-110
    if 106 <= action_idx <= 110:
        good_id = action_idx - 106
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"store:warehouse:{good}",
            "engine_action": action_idx,
            "category": "store",
            "detail": {"good": good, "good_id": good_id, "method": "warehouse"},
        }

    # Mayor island: 120 + TileType.value (120-125)
    if 120 <= action_idx <= 125:
        tile_type = action_idx - 120
        tile_name = TILE_NAMES_WITH_QUARRY.get(tile_type, f"tile_{tile_type}")
        return {
            "canonical_id": f"mayor:island:tile_type:{tile_name}",
            "engine_action": action_idx,
            "category": "mayor",
            "detail": {
                "target": "island", "tile_type": tile_type,
                "tile_name": tile_name,
            },
        }

    # Mayor city: 140 + BuildingType.value (140-162)
    if 140 <= action_idx <= 162:
        building_type = action_idx - 140
        return {
            "canonical_id": f"mayor:city:building_type:{building_type}",
            "engine_action": action_idx,
            "category": "mayor",
            "detail": {"target": "city", "building_type": building_type},
        }

    # Unknown / reserved
    return {
        "canonical_id": f"unknown:{action_idx}",
        "engine_action": action_idx,
        "category": "unknown",
        "detail": {},
    }


def build_canonical_action_catalog(
    action_mask: List[int],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """action mask와 canonical state로부터 legal action catalog를 생성한다."""
    legal_actions = []
    for idx, valid in enumerate(action_mask):
        if valid > 0.5:
            entry = _describe_action(idx, state)
            if entry is not None:
                legal_actions.append(entry)

    return {
        "schema_version": CANONICAL_ACTION_VERSION,
        "legal_actions": legal_actions,
        "total_legal": len(legal_actions),
    }
