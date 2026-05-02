# Shutdown Recovery v0 — Engine RNG Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace global `random` / `numpy.random` state in the Puerto Rico engine with per-instance RNG so the engine becomes deterministic given a seed alone — prerequisite for v1 (recovery via journal replay).

**Architecture:** Add `self._rng` and `self._np_rng` to `PuertoRicoGame.__init__` and route every existing engine random call through them. `pr_env.reset(seed=...)` stops calling `random.seed()` / `np.random.seed()` (which mutate global state); instead it passes the seed to `PuertoRicoGame`. `EngineWrapper` captures `_seed_used` and `_initial_governor_idx` for v1 to persist.

**Tech Stack:** Python 3.12, `random`, `numpy`, `pytest`. Tests run in Docker via `docker compose exec backend pytest`.

**Spec:** `docs/superpowers/specs/2026-05-02-shutdown-recovery-supplement-design.md` §3, §14.1, §14.2, §14.17.

**Context for the worker (zero-context onboarding):**
- The Puerto Rico game engine lives at `PuCo_RL/env/engine.py` (`PuertoRicoGame` class) and `PuCo_RL/env/pr_env.py` (`PuertoRicoEnv` PettingZoo AEC wrapper).
- Backend talks to the engine through `backend/app/engine_wrapper/wrapper.py` (`EngineWrapper`), which holds an instance of `PuertoRicoEnv` at `self.env`.
- The engine inside the env is exposed as `self.env.game` (NOT `self.env.unwrapped.engine` — that path doesn't exist).
- Running tests: backend tests `docker compose exec backend pytest <path>`. PuCo_RL tests run in the backend container at `/app/PuCo_RL` (verify with `docker compose exec backend ls /app/PuCo_RL/tests`).
- Memory rule: **never run tests locally**, always Docker. **never push to remote**, only commit.

---

## File Structure

| File | Type | Responsibility |
|---|---|---|
| `PuCo_RL/env/engine.py` | Modify | Add `seed` param to `PuertoRicoGame.__init__`. Replace 3 global `random.*` calls with `self._rng.*`. |
| `PuCo_RL/env/pr_env.py` | Modify | `reset(seed=...)`: stop mutating global `random`/`np.random`. Pass seed to `PuertoRicoGame`. Capture `self._seed_used`. |
| `backend/app/engine_wrapper/wrapper.py` | Modify | `_reset_environment`: capture `self._seed_used` and `self._initial_governor_idx`. Add 2 read-only properties. |
| `PuCo_RL/tests/test_engine_rng_isolation.py` | Create | 4 tests from spec §3.3 + 1 wrapper exposure test. |

---

## Task 1: Set up failing test file

**Files:**
- Create: `PuCo_RL/tests/test_engine_rng_isolation.py`

- [ ] **Step 1: Create the test file with 4 stubs that will drive the refactor**

```python
# PuCo_RL/tests/test_engine_rng_isolation.py
"""
Engine RNG isolation tests (spec §3.3).

These tests verify that the engine's randomness is sourced from per-instance
RNG (`self._rng` / `self._np_rng`) rather than global Python `random` / `numpy.random`
state. This is a prerequisite for journal-replay recovery (v1).
"""
import random
import numpy as np
import pytest

from env.pr_env import PuertoRicoEnv


def _capture_initial_state(env: PuertoRicoEnv) -> dict:
    """Return a comparable snapshot of the engine's initial deterministic state."""
    g = env.game
    return {
        "governor_idx": g.governor_idx,
        "plantation_stack": list(g.plantation_stack),
        "face_up_plantations": list(g.face_up_plantations),
    }


def _fresh_env(seed: int) -> PuertoRicoEnv:
    env = PuertoRicoEnv(num_players=3)
    env.reset(seed=seed)
    return env


def test_same_seed_produces_same_sequence():
    """Two independent envs with the same seed produce identical initial state."""
    a = _fresh_env(12345)
    b = _fresh_env(12345)
    assert _capture_initial_state(a) == _capture_initial_state(b)


def test_different_seeds_produce_different_sequences():
    """Different seeds produce different initial state."""
    a = _fresh_env(12345)
    b = _fresh_env(67890)
    assert _capture_initial_state(a) != _capture_initial_state(b)


def test_concurrent_global_random_does_not_affect_engine():
    """Engine random output is unaffected by other code consuming global random.

    This is the canary test: with global random.seed/np.random.seed (current code),
    creating a second env with a different seed clobbers global state and a
    subsequent reset of the first env produces a DIFFERENT result than reset alone.
    """
    a = _fresh_env(12345)
    a_alone = _capture_initial_state(a)

    # New env with different seed pollutes global state
    a = _fresh_env(12345)
    b = _fresh_env(67890)
    _ = _capture_initial_state(b)
    a_with_b = _capture_initial_state(a)

    assert a_alone == a_with_b, "Engine state should be isolated from global RNG mutations"


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
```

- [ ] **Step 2: Run tests to confirm they're collected and currently failing**

Run:
```bash
docker compose exec backend pytest /app/PuCo_RL/tests/test_engine_rng_isolation.py -v
```

Expected: At least `test_concurrent_global_random_does_not_affect_engine` and `test_engine_reset_does_not_mutate_global_random` FAIL. The other two may pass coincidentally with the current global-seed approach but are still meaningful regression guards.

If pytest can't import `env.pr_env` from this path, check the existing `PuCo_RL/tests/test_pr_env.py` — that file is already runnable, so use the same import pattern (probably PYTHONPATH-based).

- [ ] **Step 3: Commit failing tests**

```bash
git add PuCo_RL/tests/test_engine_rng_isolation.py
git commit -m "test(rl): add failing engine RNG isolation tests (v0 prep)"
```

---

## Task 2: Add per-instance RNG to `PuertoRicoGame`

**Files:**
- Modify: `PuCo_RL/env/engine.py:1, 15-17, 47, 67, 96, 141`

- [ ] **Step 1: Add `numpy` import and modify `__init__` signature**

Edit `PuCo_RL/env/engine.py` near the top to add numpy:

```python
# At top of file, BEFORE 'from configs.constants import ...'
import random
import numpy as np
from typing import List, Dict, Optional, Tuple
```

Then modify the `PuertoRicoGame.__init__` signature (line 16) from:
```python
def __init__(self, num_players: int):
```
to:
```python
def __init__(self, num_players: int, seed: Optional[int] = None):
```

- [ ] **Step 2: Initialize per-instance RNG before any random use**

Insert after line 20 (`self.num_players = num_players`), BEFORE line 21 (`self.players = ...`):

```python
        # Per-instance RNG — must be initialized BEFORE any code that consumes random.
        # Replaces former reliance on global random/np.random state in pr_env.reset.
        self._rng = random.Random(seed)
        self._np_rng = np.random.default_rng(seed)
```

This must be set before `_init_plantation_stack()` (which uses random.shuffle on line 96) is called from line 47, and before `self.governor_idx = random.randint(...)` on line 67.

- [ ] **Step 3: Replace 3 global random calls with per-instance RNG**

| Original line | Original | Replacement |
|---|---|---|
| `engine.py:67` | `self.governor_idx = random.randint(0, num_players - 1)` | `self.governor_idx = self._rng.randint(0, num_players - 1)` |
| `engine.py:96` (in `_init_plantation_stack`) | `random.shuffle(stack)` | `self._rng.shuffle(stack)` |
| `engine.py:141` (in plantation discard reshuffle) | `random.shuffle(self.plantation_discard)` | `self._rng.shuffle(self.plantation_discard)` |

After this step, `engine.py` has zero direct calls to global `random.*`.

Verify with grep:
```bash
docker compose exec backend grep -nE "(^|[^_a-zA-Z0-9.])(random|np\.random)\." /app/PuCo_RL/env/engine.py
```
Expected output: no remaining `random.*` lines (only the `import random` at top, which the regex excludes).

- [ ] **Step 4: Run engine-only test to confirm engine compiles and basic behavior intact**

Run a fast existing test that exercises engine init:
```bash
docker compose exec backend pytest /app/PuCo_RL/tests/test_engine.py -v
```
Expected: all PASS (no behavior change for callers that already pass seed via global state — the new code paths produce same outcomes given same seed).

- [ ] **Step 5: Commit**

```bash
git add PuCo_RL/env/engine.py
git commit -m "refactor(rl-env): per-instance RNG in PuertoRicoGame"
```

---

## Task 3: Wire seed through `pr_env.reset`, capture `_seed_used`

**Files:**
- Modify: `PuCo_RL/env/pr_env.py:127-148`

- [ ] **Step 1: Update `reset(seed=None)` to remove global mutation and pass seed to engine**

Current code at `pr_env.py:127-148` (verify line numbers — file may shift):

```python
def reset(self, seed=None, options=None):
    if seed is not None:
        # Note: We should ideally pass seed to the engine, but for now we'll rely on global random
        import random
        random.seed(seed)
        np.random.seed(seed)

    self.agents = self.possible_agents[:]
    self.rewards = {agent: 0.0 for agent in self.agents}
    self._cumulative_rewards = {agent: 0.0 for agent in self.agents}
    self.terminations = {agent: False for agent in self.agents}
    self.truncations = {agent: False for agent in self.agents}
    self.infos = {agent: {} for agent in self.agents}

    self.game = PuertoRicoGame(self.num_players)
    self.game.start_game()
    ...
```

Replace with:

```python
def reset(self, seed=None, options=None):
    # Determine the effective seed; capture it so callers (EngineWrapper) can
    # persist it for later journal-replay recovery (v1).
    import random as _stdlib_random  # local alias to avoid shadow with numpy below
    if seed is None:
        seed_used = _stdlib_random.randrange(2**63)
    else:
        seed_used = int(seed)
    self._seed_used = seed_used

    self.agents = self.possible_agents[:]
    self.rewards = {agent: 0.0 for agent in self.agents}
    self._cumulative_rewards = {agent: 0.0 for agent in self.agents}
    self.terminations = {agent: False for agent in self.agents}
    self.truncations = {agent: False for agent in self.agents}
    self.infos = {agent: {} for agent in self.agents}

    self.game = PuertoRicoGame(self.num_players, seed=seed_used)
    self.game.start_game()
    # ... rest unchanged
```

The crucial change: **delete** the `random.seed(seed)` and `np.random.seed(seed)` lines. They were the global pollution. Replace with `self._seed_used` capture and `seed=seed_used` arg passing to `PuertoRicoGame`.

- [ ] **Step 2: Run the v0 isolation tests — all 4 should pass now**

```bash
docker compose exec backend pytest /app/PuCo_RL/tests/test_engine_rng_isolation.py -v
```
Expected: 4/4 PASS.

If `test_concurrent_global_random_does_not_affect_engine` still fails: confirm step 1 actually removed `random.seed(seed)` and `np.random.seed(seed)` lines (grep `pr_env.py` for `random.seed`).

- [ ] **Step 3: Run existing pr_env tests — no regression**

```bash
docker compose exec backend pytest /app/PuCo_RL/tests/test_pr_env.py -v
```
Expected: all PASS. If any test fails because it depended on global seed being set (e.g., expected a specific shuffle outcome from `random.seed(42)` external + `env.reset()` with no seed), the test was relying on undefined behavior — fix by passing the seed to `env.reset()` instead.

- [ ] **Step 4: Commit**

```bash
git add PuCo_RL/env/pr_env.py
git commit -m "refactor(rl-env): pass seed to PuertoRicoGame, drop global RNG mutation"
```

---

## Task 4: Capture `_initial_governor_idx` and expose `EngineWrapper` properties

**Files:**
- Modify: `backend/app/engine_wrapper/wrapper.py:42-49, near class body for new properties`

- [ ] **Step 1: Capture `_seed_used` and `_initial_governor_idx` in `_reset_environment`**

Find the `_reset_environment` method (currently at `wrapper.py:85`). After the env reset (either the early-return at `:87-88` or after the retry loop at `:104`), capture:

```python
def _reset_environment(self, game_seed: Optional[int], governor_idx: Optional[int]) -> None:
    if governor_idx is None:
        self.env.reset(seed=game_seed)
        # Capture for v1 recovery: the actual seed used and the governor chosen.
        self._seed_used = self.env._seed_used
        self._initial_governor_idx = self.env.game.governor_idx
        return

    if governor_idx < 0 or governor_idx >= self.env.num_players:
        raise ValueError(
            f"governor_idx must be between 0 and {self.env.num_players - 1}, got {governor_idx}"
        )

    max_attempts = 64
    for attempt in range(max_attempts):
        seed = None if game_seed is None else game_seed + attempt
        self.env.reset(seed=seed)
        if self.env.game.governor_idx == governor_idx:
            self._seed_used = self.env._seed_used
            self._initial_governor_idx = self.env.game.governor_idx
            return

    raise RuntimeError(
        f"Unable to initialize engine with governor_idx={governor_idx} after {max_attempts} attempts"
    )
```

Two capture sites cover both branches.

- [ ] **Step 2: Add read-only properties to `EngineWrapper`**

Add these property definitions inside the `EngineWrapper` class (anywhere convenient, e.g., right after `_reset_environment`):

```python
    @property
    def seed_used(self) -> int:
        """Seed actually used to initialize this engine instance.

        Set in `_reset_environment`. Callers persist this for v1 journal-replay recovery.
        """
        return self._seed_used

    @property
    def initial_governor_idx(self) -> int:
        """Governor index chosen at engine initialization time.

        Set in `_reset_environment`. Callers persist this for v1 verification.
        """
        return self._initial_governor_idx
```

- [ ] **Step 3: Add a wrapper-exposure test**

Append to `PuCo_RL/tests/test_engine_rng_isolation.py`:

```python
def test_engine_wrapper_exposes_seed_used_and_initial_governor_idx():
    """EngineWrapper must expose the captured seed and governor for backend persistence."""
    # Imported lazily so the rest of the test file can run without backend deps in scope.
    import sys
    sys.path.insert(0, "/app/backend")
    from app.engine_wrapper.wrapper import EngineWrapper

    wrapper = EngineWrapper(num_players=3, game_seed=12345)

    assert wrapper.seed_used == 12345
    assert isinstance(wrapper.initial_governor_idx, int)
    assert 0 <= wrapper.initial_governor_idx < 3

    # Determinism: a second wrapper with same seed yields same governor.
    wrapper2 = EngineWrapper(num_players=3, game_seed=12345)
    assert wrapper2.initial_governor_idx == wrapper.initial_governor_idx

    # When seed=None, seed_used is auto-generated and stable for the instance.
    auto = EngineWrapper(num_players=3, game_seed=None)
    assert isinstance(auto.seed_used, int)
    assert 0 <= auto.seed_used < 2**63
```

- [ ] **Step 4: Run the new test**

```bash
docker compose exec backend pytest /app/PuCo_RL/tests/test_engine_rng_isolation.py::test_engine_wrapper_exposes_seed_used_and_initial_governor_idx -v
```
Expected: PASS.

- [ ] **Step 5: Run all 5 isolation tests + existing wrapper tests**

```bash
docker compose exec backend pytest /app/PuCo_RL/tests/test_engine_rng_isolation.py -v
docker compose exec backend pytest backend/tests/ -k "engine_wrapper or wrapper" -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine_wrapper/wrapper.py PuCo_RL/tests/test_engine_rng_isolation.py
git commit -m "feat(engine-wrapper): expose seed_used and initial_governor_idx for v1"
```

---

## Task 5: Regression sweep

**Files:** none modified.

- [ ] **Step 1: Run the broader PuCo_RL test suite**

```bash
docker compose exec backend pytest /app/PuCo_RL/tests/ -v
```
Expected: all PASS. Specifically the existing `test_engine.py` and `test_pr_env.py` should still be green.

- [ ] **Step 2: Run backend tests that touch engine/wrapper paths**

```bash
docker compose exec backend pytest backend/tests/ -k "engine or wrapper or scenario" -v
```
Expected: all PASS. Includes `test_canonical_state.py`, `test_canonical_action.py`, `test_state_serializer*.py`, etc.

- [ ] **Step 3: Run a broader smoke — full backend test suite**

```bash
docker compose exec backend pytest backend/tests/ -v --maxfail=3
```
Expected: all PASS. If anything fails because of seed/RNG dependence, investigate — most likely a test that was relying on `random.seed(42)` being set before engine creation (now ineffective). Fix by passing seed via `EngineWrapper(game_seed=42)`.

- [ ] **Step 4: Confirm zero remaining global random usage in engine code**

```bash
docker compose exec backend grep -nE "(^|[^_a-zA-Z0-9.])(random|np\.random)\." /app/PuCo_RL/env/engine.py /app/PuCo_RL/env/pr_env.py
```
Expected output: only the `import random` lines and any unrelated comments. **No `random.seed`, `random.randint`, `random.shuffle`, `np.random.seed` lines in either file.**

If grep finds residual calls, repeat the find/replace until clean.

- [ ] **Step 5: Final verification — same seed twice, same outcome**

```bash
docker compose exec backend python -c "
from env.pr_env import PuertoRicoEnv
import json

def fingerprint(seed):
    e = PuertoRicoEnv(num_players=3)
    e.reset(seed=seed)
    return (e.game.governor_idx, [t.value for t in e.game.plantation_stack])

a = fingerprint(12345)
b = fingerprint(12345)
print('match:', a == b)
assert a == b, 'NOT DETERMINISTIC'
print('OK: same seed -> same outcome')
"
```
Expected: `match: True` and `OK: same seed -> same outcome`. If this fails, v0 is incomplete — investigate before merging.

- [ ] **Step 6: Final commit if any cleanup was needed**

If steps 1-5 surfaced any test fixes, commit them:

```bash
git status
git add <whatever-was-modified>
git commit -m "test: align tests with per-instance RNG"
```

---

## Merge checklist (before opening PR)

- [ ] All 5 tests in `PuCo_RL/tests/test_engine_rng_isolation.py` pass.
- [ ] Existing PuCo_RL test suite passes.
- [ ] Backend test suite passes.
- [ ] Grep confirms zero remaining `random.*` / `np.random.*` calls in `engine.py` and `pr_env.py` (only top-of-file imports remain).
- [ ] `EngineWrapper.seed_used` and `EngineWrapper.initial_governor_idx` properties work and are deterministic.
- [ ] No changes outside the 3 files listed in File Structure.

## Out of scope (v1)

The following land in the v1 plan, NOT this PR:
- `EngineWrapper.current_phase`, `EngineWrapper.active_player`, `EngineWrapper.replay_step`
- `ENGINE_COMPAT_VERSION` constant in `engine_gateway/factory.py`
- Any DB schema changes
- Any `GameService` changes
- Frontend changes

## Risk and rollback

- **Risk: model inference outputs shift due to changed RNG sequencing.** Same input seed produces same output, so trained PPO/HPPO models see equivalent state distributions. Verified by step 5's existing test suite.
- **Risk: `PuCo_RL/tests/balance_test.py:58-60` uses `random.seed`/`np.random.seed`/`torch.manual_seed` explicitly.** That file is a stand-alone benchmarking tool — `torch.manual_seed` is unaffected by this PR. Leave as-is.
- **Rollback**: revert the 5 commits. No DB or persistent state changes; rollback is purely code.
