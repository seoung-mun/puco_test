"""
Bundle + Adapter 통합 테스트.

핵심 검증:
- Semantic293TypeMayorAdapter encode/decode 동작
- **obs parity**: adapter encode_obs == env flatten (학습/서빙 obs 동치성)
- bundle runtime smoke/parity/fallback 검증
"""
import os
from pathlib import Path

import numpy as np
import pytest
import torch

from app.engine_wrapper.wrapper import EngineWrapper
from app.services.adapter_runtime import AdapterRuntime
from app.services.agents.wrappers import PPOWrapper
from app.services.canonical_action import build_canonical_action_catalog
from app.services.canonical_state import build_canonical_state
from app.services.engine_gateway.bootstrap import ensure_puco_rl_path
from app.services.engine_gateway.constants import BuildingType, Phase, TileType
from app.services.engine_gateway.env import flatten_dict_observation
from app.services.model_registry import load_bundle_manifest, resolve_bundle_checkpoint

ensure_puco_rl_path()
from common.semantic293_adapter import Semantic293TypeMayorAdapter  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE_DIR = REPO_ROOT / "PuCo_RL" / "models" / "ppo-pr-server-semantic293-20260419"


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def three_player_engine():
    return EngineWrapper(num_players=3)


@pytest.fixture
def three_player_engine_at_mayor():
    engine = EngineWrapper(num_players=3, governor_idx=0)
    game = engine.env.game
    game.current_phase = Phase.MAYOR
    game.current_player_idx = 0
    game.active_role_player = 0
    game.players_taken_action = 0
    for p in game.players:
        p.unplaced_colonists = 3
        p.island_board = []
        p.city_board = []
        p.place_plantation(TileType.CORN_PLANTATION)
        p.place_plantation(TileType.INDIGO_PLANTATION)
        p.build_building(BuildingType.SMALL_INDIGO_PLANT)
        p.build_building(BuildingType.SMALL_MARKET)
    engine.env.agent_selection = "player_0"
    engine._refresh_cached_view()
    return engine


# ── adapter shape / mask ──────────────────────────────────────────────────


def test_adapter_encode_obs_produces_293_dims(three_player_engine):
    state = build_canonical_state(three_player_engine)
    adapter = Semantic293TypeMayorAdapter()
    obs = adapter.encode_obs(state, player_idx=0)
    assert obs.shape == (293,)
    assert obs.dtype == np.float32


def test_adapter_encode_action_mask_produces_200_dims(three_player_engine):
    state = build_canonical_state(three_player_engine)
    mask_raw = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask_raw, state)
    adapter = Semantic293TypeMayorAdapter()
    mask = adapter.encode_action_mask(state, catalog["legal_actions"])
    assert mask.shape == (200,)
    assert int(mask.sum()) == catalog["total_legal"]


# ── decode behavior ───────────────────────────────────────────────────────


def test_adapter_decode_exact_match(three_player_engine):
    state = build_canonical_state(three_player_engine)
    mask_raw = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask_raw, state)
    adapter = Semantic293TypeMayorAdapter()

    first_legal = catalog["legal_actions"][0]["engine_action"]
    result = adapter.decode_action(first_legal, state, catalog["legal_actions"])
    assert result.engine_action == first_legal
    assert result.fallback_used is False


def test_adapter_decode_illegal_action_uses_fallback(three_player_engine):
    state = build_canonical_state(three_player_engine)
    mask_raw = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask_raw, state)
    adapter = Semantic293TypeMayorAdapter()

    legal_set = {e["engine_action"] for e in catalog["legal_actions"]}
    illegal = next(i for i in range(199, -1, -1) if i not in legal_set)

    result = adapter.decode_action(illegal, state, catalog["legal_actions"])
    assert result.fallback_used is True
    assert result.fallback_reason in ("exact_match_missing", "illegal_model_action")


def test_adapter_decode_mayor_exact_match(three_player_engine_at_mayor):
    state = build_canonical_state(three_player_engine_at_mayor)
    mask_raw = three_player_engine_at_mayor.get_action_mask()
    catalog = build_canonical_action_catalog(mask_raw, state)
    adapter = Semantic293TypeMayorAdapter()

    mayor_entry = next(
        e for e in catalog["legal_actions"]
        if e["category"] == "mayor" and e["detail"].get("target") == "island"
    )
    result = adapter.decode_action(
        mayor_entry["engine_action"], state, catalog["legal_actions"]
    )
    assert result.engine_action == mayor_entry["engine_action"]
    assert result.canonical_id == mayor_entry["canonical_id"]
    assert result.fallback_used is False


def test_adapter_decode_mayor_fallback_uses_lowest_engine_action():
    """Mayor fallback은 deterministic하게 lowest engine_action을 선택해야 한다."""
    adapter = Semantic293TypeMayorAdapter()
    legal_actions = [
        {
            "engine_action": 123,
            "canonical_id": "mayor:island:slot:3",
            "category": "mayor",
            "detail": {"target": "island", "slot_idx": 3, "tile_type": 5},
        },
        {
            "engine_action": 121,
            "canonical_id": "mayor:island:slot:1",
            "category": "mayor",
            "detail": {"target": "island", "slot_idx": 1, "tile_type": 2},
        },
    ]

    result = adapter.decode_action(125, {"meta": {"phase_id": 1}}, legal_actions)
    assert result.engine_action == 121
    assert result.canonical_id == "mayor:island:slot:1"
    assert result.fallback_used is True
    assert result.fallback_reason == "exact_match_missing"


def test_adapter_decode_no_legal_actions_returns_pass():
    adapter = Semantic293TypeMayorAdapter()
    result = adapter.decode_action(42, {"meta": {"phase_id": 9}}, [])
    assert result.engine_action == 15
    assert result.canonical_id == "pass"
    assert result.fallback_used is True
    assert result.fallback_reason == "adapter_guard_triggered"


# ── obs parity (핵심 검증) ────────────────────────────────────────────────


def _flatten_env_obs(engine: EngineWrapper) -> np.ndarray:
    raw_obs = engine.last_obs
    obs_space = engine.env.observation_space(
        engine.env.possible_agents[0]
    )["observation"]
    return flatten_dict_observation(raw_obs, obs_space)


def _load_default_runtime() -> AdapterRuntime:
    bundle_dir = Path(os.environ.get("PPO_SMOKE_BUNDLE_DIR", str(DEFAULT_BUNDLE_DIR)))
    manifest = load_bundle_manifest(str(bundle_dir))
    if manifest is None:
        pytest.skip(f"Bundle manifest not available at {bundle_dir}")
    checkpoint_path = resolve_bundle_checkpoint(str(bundle_dir), manifest)
    return AdapterRuntime(manifest, checkpoint_path)


def test_adapter_obs_parity_with_env_flatten_initial(three_player_engine):
    """
    초기 상태에서 adapter encode_obs == env flatten.
    이 테스트는 학습 시점의 obs를 서빙에서 정확히 재현하는지 검증한다.
    """
    state = build_canonical_state(three_player_engine)
    adapter = Semantic293TypeMayorAdapter()
    adapter_obs = adapter.encode_obs(state, player_idx=0)
    env_obs = _flatten_env_obs(three_player_engine)

    assert env_obs.shape == adapter_obs.shape, (
        f"Shape mismatch: adapter={adapter_obs.shape} env={env_obs.shape}"
    )
    np.testing.assert_allclose(
        adapter_obs, env_obs, atol=1e-5,
        err_msg="Adapter obs does not match env flatten - obs parity broken!",
    )


def test_adapter_obs_parity_with_env_flatten_at_mayor(three_player_engine_at_mayor):
    """Mayor phase에서도 obs parity가 유지되어야 한다."""
    state = build_canonical_state(three_player_engine_at_mayor)
    adapter = Semantic293TypeMayorAdapter()
    adapter_obs = adapter.encode_obs(state, player_idx=0)
    env_obs = _flatten_env_obs(three_player_engine_at_mayor)

    assert env_obs.shape == adapter_obs.shape
    np.testing.assert_allclose(
        adapter_obs, env_obs, atol=1e-5,
        err_msg="Adapter obs parity broken at MAYOR phase!",
    )


def test_smoke_inference_full_pipeline(three_player_engine):
    runtime = _load_default_runtime()
    result = runtime.infer(three_player_engine)

    mask = three_player_engine.get_action_mask()
    assert 0 <= result.engine_action < 200
    assert mask[result.engine_action] > 0.5
    assert result.bundle_id == runtime.manifest["bundle_id"]
    assert result.adapter_id == "puco.semantic293.type_mayor.v1"


def test_adapter_inference_matches_legacy_wrapper(three_player_engine):
    runtime = _load_default_runtime()
    manifest = runtime.manifest
    bundle_dir = Path(os.environ.get("PPO_SMOKE_BUNDLE_DIR", str(DEFAULT_BUNDLE_DIR)))
    checkpoint_path = resolve_bundle_checkpoint(str(bundle_dir), manifest)

    raw_obs = _flatten_env_obs(three_player_engine)
    obs_tensor = torch.as_tensor(raw_obs, dtype=torch.float32).unsqueeze(0)
    mask = three_player_engine.get_action_mask()
    mask_tensor = torch.as_tensor(mask, dtype=torch.float32).unsqueeze(0)

    wrapper = PPOWrapper(checkpoint_path, obs_dim=raw_obs.shape[0])
    legacy_action = wrapper.act(obs_tensor, mask_tensor)

    result = runtime.infer(three_player_engine)
    assert result.engine_action == legacy_action, (
        f"Parity broken: adapter={result.engine_action}, legacy={legacy_action}"
    )


def test_fallback_rate_under_threshold():
    runtime = _load_default_runtime()
    engine = EngineWrapper(num_players=3)
    fallback_count = 0
    total_count = 0

    for _ in range(100):
        if any(engine.env.terminations.values()):
            break
        result = runtime.infer(engine)
        total_count += 1
        if result.fallback_used:
            fallback_count += 1
        step_result = engine.step(result.engine_action)
        assert isinstance(step_result, dict)
        assert "done" in step_result
        if step_result["done"]:
            break

    assert total_count > 0
    rate = fallback_count / total_count
    assert rate <= 0.05, f"Fallback rate {rate:.1%} exceeds 5% threshold"
