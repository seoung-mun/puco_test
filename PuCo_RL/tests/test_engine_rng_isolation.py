"""
Engine RNG isolation tests (spec Section 3.3).

These tests verify that the engine's randomness is sourced from per-instance
RNG (``self._rng`` / ``self._np_rng``) rather than global Python ``random`` /
``numpy.random`` state. This is a prerequisite for journal-replay recovery (v1).
"""

import random

import numpy as np

from env.pr_env import PuertoRicoEnv


def _capture_initial_state(env: PuertoRicoEnv) -> dict:
    """Return a comparable snapshot of the engine's initial deterministic state."""
    game = env.game
    return {
        "governor_idx": game.governor_idx,
        "plantation_stack": list(game.plantation_stack),
        "face_up_plantations": list(game.face_up_plantations),
    }


def _fresh_env(seed: int) -> PuertoRicoEnv:
    env = PuertoRicoEnv(num_players=3)
    env.reset(seed=seed)
    return env


def test_same_seed_produces_same_sequence():
    """Two independent envs with the same seed produce identical initial state."""
    env_a = _fresh_env(12345)
    env_b = _fresh_env(12345)

    assert _capture_initial_state(env_a) == _capture_initial_state(env_b)


def test_different_seeds_produce_different_sequences():
    """Different seeds produce different initial state."""
    env_a = _fresh_env(12345)
    env_b = _fresh_env(67890)

    assert _capture_initial_state(env_a) != _capture_initial_state(env_b)


def test_concurrent_global_random_does_not_affect_engine():
    """Engine random output is unaffected by other code consuming global random."""
    env_alone = _fresh_env(12345)
    baseline_state = _capture_initial_state(env_alone)

    env_with_interference = _fresh_env(12345)
    other_env = _fresh_env(67890)
    _ = _capture_initial_state(other_env)
    state_with_other_env = _capture_initial_state(env_with_interference)

    assert baseline_state == state_with_other_env, (
        "Engine state should be isolated from global RNG mutations"
    )


def test_engine_reset_does_not_mutate_global_random():
    """Engine reset must not change global random / np.random state."""
    random.seed(99999)
    np.random.seed(99999)

    py_state_before = random.getstate()
    np_state_before = np.random.get_state()[1].tobytes()

    _ = _fresh_env(12345)

    py_state_after = random.getstate()
    np_state_after = np.random.get_state()[1].tobytes()

    assert py_state_before == py_state_after, "global random state was mutated by engine"
    assert np_state_before == np_state_after, "global numpy random state was mutated by engine"


def test_engine_wrapper_exposes_seed_used_and_initial_governor_idx():
    """EngineWrapper must expose the captured seed and governor for backend persistence."""
    import sys

    if "/app/backend" not in sys.path:
        sys.path.insert(0, "/app/backend")

    from app.engine_wrapper.wrapper import EngineWrapper

    wrapper = EngineWrapper(num_players=3, game_seed=12345)

    assert wrapper.seed_used == 12345
    assert isinstance(wrapper.initial_governor_idx, int)
    assert 0 <= wrapper.initial_governor_idx < 3

    wrapper_again = EngineWrapper(num_players=3, game_seed=12345)
    assert wrapper_again.initial_governor_idx == wrapper.initial_governor_idx

    auto_seed_wrapper = EngineWrapper(num_players=3, game_seed=None)
    assert isinstance(auto_seed_wrapper.seed_used, int)
    assert 0 <= auto_seed_wrapper.seed_used < 2**63
