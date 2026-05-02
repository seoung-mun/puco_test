# Shutdown Recovery v1 — Lazy Per-Game Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **PREREQUISITE:** v0 plan (`2026-05-02-shutdown-recovery-v0-engine-rng-isolation.md`) must be merged. This plan assumes `EngineWrapper.seed_used` and `EngineWrapper.initial_governor_idx` exist and the engine is deterministic given a seed.

**Goal:** Restore mid-game state automatically after a Render free-tier restart by replaying the action journal stored in PostgreSQL. Games that cannot be exactly recovered fall into a `RECOVERY_BLOCKED` first-class state where the user sees the last known screen and can manually end the game.

**Architecture:**
- DB becomes the source of truth (`game_logs` rows form the journal; `games` row holds metadata: `game_seed`, `governor_idx`, `engine_compat_version`, `state_revision`).
- Memory engine (`GameService.active_engines`) is a cache.
- Recovery is **lazy per-game**: triggered only when a request hits a game whose engine is missing. Single-flight via per-game `asyncio.Lock`.
- Recovery `replay_step()` skips ALL persistence side effects (no ML logger, no replay logger, no broadcast, no bot scheduling) — those are reserved for live `process_action`.
- Frontend gets `RECOVERY_STARTED` (during long replays) and `RECOVERY_BLOCKED` WS messages.

**Tech Stack:** FastAPI (mix of sync and async routes), SQLAlchemy 2.0 sync `Session`, Alembic, Redis, asyncio (`asyncio.Lock`, `asyncio.to_thread`), pytest, `pytest-asyncio`, React + TypeScript with `useGameWebSocket` hook.

**Spec:** `docs/superpowers/specs/2026-05-02-shutdown-recovery-supplement-design.md` §4–§15.

**Context for the worker (zero-context onboarding):**
- Code map: `backend/app/services/game_service.py` is the integration hub (game lifecycle, action processing, bot orchestration). `backend/app/api/channel/` holds REST + WS routes. `backend/app/engine_wrapper/wrapper.py` wraps the PuCo_RL engine. `backend/app/db/models.py` is SQLAlchemy ORM.
- Engine path is `self.env.game` on `EngineWrapper` (NOT `self.env.unwrapped.engine`).
- Memory rule: tests run in Docker only (`docker compose exec backend pytest ...`). Never push to remote.
- Existing patterns: alembic migration files live in `backend/alembic/versions/`. Sync DB sessions opened via `with SessionLocal() as db:`. `process_action` is sync. WS handler in `ws.py` is async.
- The 5-iteration spec review settled key decisions:
  - `_engine_revision` is a class-level `Dict[UUID, int]`, separate from `_bot_tasks`.
  - `_bot_tasks` migrates from `set` to `Dict[UUID, asyncio.Task]` (5 sites).
  - `process_action` gains a `canonical_id` keyword arg (the action route already computes this).
  - `ensure_engine_loaded` is `async def` but offloads its body via `asyncio.to_thread(self._do_recovery_sync, game_id)`.
  - Two `db.commit()` calls in `process_action` already exist (lines 316 and 340 today). Atomic GameLog+state_revision write happens at the FIRST commit.
  - `RECOVERY_BLOCKED` is a new value of the existing `games.status` STRING column.

---

## File Structure

| File | Type | Responsibility |
|---|---|---|
| `backend/alembic/versions/<ts>_recovery_metadata.py` | Create | Add 5 columns to `games`, 3 columns to `game_logs`, partial-unique index on `(game_id, revision)`. |
| `backend/app/db/models.py` | Modify | Declare new ORM columns. Import `BigInteger`. |
| `backend/app/services/engine_gateway/factory.py` | Modify | Export `ENGINE_COMPAT_VERSION = 1`. Pass through `game_seed` to `EngineWrapper`. |
| `backend/app/engine_wrapper/wrapper.py` | Modify | Add `current_phase`, `active_player`, `replay_step` to `EngineWrapper`. |
| `backend/app/services/game_service_support.py` | Modify | Add `_action_space_fingerprint`, `_mayor_semantics_fingerprint`. Embed `__engine__` block in `model_versions` snapshot. |
| `backend/app/services/game_service.py` | Modify | Add `_engine_revision`, `_recovery_locks`, recovery methods. Migrate `_bot_tasks` to dict. Modify `start_game` and `process_action`. |
| `backend/app/api/channel/ws.py` | Modify | Insert `ensure_engine_loaded` + state push between `auth_ok` and `manager.connect`. |
| `backend/app/api/channel/game.py` | Modify | Action route awaits `ensure_engine_loaded` and passes `canonical_id`. final-score awaits ensure_engine_loaded. |
| `backend/app/api/channel/playback.py` | Modify | Convert sync routes (`get_playback`, `set_speed`) to `async def`; await `ensure_engine_loaded`. |
| `backend/app/schemas/playback.py` | (no change) | already correct |
| `frontend/src/hooks/useGameWebSocket.ts` | Modify | Add `onRecoveryStarted`, `onRecoveryBlocked` callbacks. |
| `frontend/src/components/GameScreen.tsx` (or equivalent) | Modify | Wire recovery overlay + blocked modal UI. |
| `backend/tests/test_recovery_*.py` | Create | 12 backend tests (spec §8.2). |
| `frontend/src/hooks/__tests__/useGameWebSocket.test.ts` | Modify | Add 3 frontend tests (spec §8.3). |

---

## Phase A — Schema (3 tasks)

### Task A1: Alembic migration for recovery columns

**Files:**
- Create: `backend/alembic/versions/<timestamp>_add_recovery_metadata.py`

- [ ] **Step 1: Generate migration template**

```bash
docker compose exec backend alembic revision -m "add recovery metadata"
```
This creates a file like `backend/alembic/versions/abc123_add_recovery_metadata.py`. Note the path — we'll edit it next.

- [ ] **Step 2: Fill in upgrade/downgrade**

Replace the template body with:

```python
"""add recovery metadata

Revision ID: <auto>
Revises: <prev>
Create Date: 2026-05-02 ...
"""
from alembic import op
import sqlalchemy as sa

revision = '<auto>'
down_revision = '<prev>'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('games', sa.Column('game_seed', sa.BigInteger(), nullable=True))
    op.add_column('games', sa.Column('governor_idx', sa.Integer(), nullable=True))
    op.add_column('games', sa.Column('engine_compat_version', sa.Integer(), nullable=True))
    op.add_column('games', sa.Column('state_revision', sa.Integer(),
                                     nullable=False, server_default='0'))
    op.add_column('games', sa.Column('recovery_blocked_reason', sa.String(64), nullable=True))

    op.add_column('game_logs', sa.Column('revision', sa.Integer(), nullable=True))
    op.add_column('game_logs', sa.Column('phase_before', sa.String(32), nullable=True))
    op.add_column('game_logs', sa.Column('active_player_before', sa.String(16), nullable=True))

    op.create_index(
        'ux_game_logs_game_revision',
        'game_logs', ['game_id', 'revision'],
        unique=True,
        postgresql_where=sa.text('revision IS NOT NULL'),
    )


def downgrade():
    op.drop_index('ux_game_logs_game_revision', table_name='game_logs')
    op.drop_column('game_logs', 'active_player_before')
    op.drop_column('game_logs', 'phase_before')
    op.drop_column('game_logs', 'revision')
    op.drop_column('games', 'recovery_blocked_reason')
    op.drop_column('games', 'state_revision')
    op.drop_column('games', 'engine_compat_version')
    op.drop_column('games', 'governor_idx')
    op.drop_column('games', 'game_seed')
```

- [ ] **Step 3: Apply migration and verify schema**

```bash
docker compose exec backend alembic upgrade head
docker compose exec db psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl -c "\d games" -c "\d game_logs"
```
Expected: new columns visible. `state_revision` defaults to 0.

- [ ] **Step 4: Test downgrade then upgrade idempotency**

```bash
docker compose exec backend alembic downgrade -1
docker compose exec backend alembic upgrade head
```
Expected: no errors. Schema returns to upgraded state.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/*_add_recovery_metadata.py
git commit -m "feat(db): add recovery metadata schema (games + game_logs)"
```

### Task A2: Update ORM models

**Files:**
- Modify: `backend/app/db/models.py:3, 25-43, 45-63`

- [ ] **Step 1: Update import line**

`models.py:3` currently imports:
```python
from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey, Index
```
Change to:
```python
from sqlalchemy import Column, Integer, BigInteger, Float, String, Boolean, DateTime, ForeignKey, Index
```

- [ ] **Step 2: Add columns to `GameSession` (lines 25-43)**

Inside the `GameSession` class, after the existing columns, add:

```python
    # Recovery metadata (v1). All nullable except state_revision (server_default=0).
    game_seed = Column(BigInteger, nullable=True)
    governor_idx = Column(Integer, nullable=True)
    engine_compat_version = Column(Integer, nullable=True)
    state_revision = Column(Integer, nullable=False, server_default="0", default=0)
    recovery_blocked_reason = Column(String(64), nullable=True)
```

- [ ] **Step 3: Add columns to `GameLog` (lines 45-63)**

Inside the `GameLog` class, after existing columns, add:

```python
    # Journal role for recovery (v1). NULL for pre-patch rows.
    revision = Column(Integer, nullable=True)
    phase_before = Column(String(32), nullable=True)
    active_player_before = Column(String(16), nullable=True)
```

- [ ] **Step 4: Verify ORM loads without error**

```bash
docker compose exec backend python -c "from app.db import models; print(models.GameSession.__table__.columns.keys()); print(models.GameLog.__table__.columns.keys())"
```
Expected: lists include the new columns.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py
git commit -m "feat(db): declare recovery metadata columns on ORM models"
```

### Task A3: Migration roundtrip test

**Files:**
- Create: `backend/tests/test_recovery_migration.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_recovery_migration.py
"""Spec §8.2 test 2: alembic migration up/down/up is idempotent."""
import subprocess


def _alembic(*args):
    return subprocess.run(
        ["alembic", *args],
        capture_output=True, text=True, check=True, cwd="/app/backend",
    )


def test_alembic_migration_adds_columns_idempotent():
    _alembic("downgrade", "-1")
    _alembic("upgrade", "head")
    _alembic("downgrade", "-1")
    _alembic("upgrade", "head")
```

- [ ] **Step 2: Run it**

```bash
docker compose exec backend pytest backend/tests/test_recovery_migration.py -v
```
Expected: PASS. Note: this test mutates schema; run only when DB is in a clean state.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_recovery_migration.py
git commit -m "test(db): roundtrip alembic recovery metadata migration"
```

---

## Phase B — GameService internal state (2 tasks)

### Task B1: Add `_engine_revision` and migrate `_bot_tasks` to dict

**Files:**
- Modify: `backend/app/services/game_service.py:39, 463, 471, 483, 504`

- [ ] **Step 1: Update class-level declarations**

Locate `class GameService:` near line 36. Update the class-variable block:

```python
class GameService:
    # In-memory store for active engines (Class variable to persist between requests)
    active_engines: Dict[UUID, EngineWrapper] = {}
    _bot_tasks: Dict[UUID, asyncio.Task] = {}        # was: set()
    _engine_revision: Dict[UUID, int] = {}           # NEW
    _recovery_locks: Dict[UUID, asyncio.Lock] = {}   # NEW (used in Phase F)
    _bot_stall_watchdogs: Dict[str, asyncio.Task] = {}
    _game_speed: Dict[UUID, int] = {}
    _game_paused: Dict[UUID, bool] = {}
```

`_recovery_locks_meta_lock` is module-level and added in Phase F.

- [ ] **Step 2: Update line 463 (`add` → dict assignment)**

Find the line:
```python
self._bot_tasks.add(task)
```
This is inside a function that takes `game_id` as parameter (likely `_schedule_next_bot_turn_if_needed` or similar). Change to:
```python
self._bot_tasks[game_id] = task
```

- [ ] **Step 3: Update line 471, 504 (len() — no change needed, but verify)**

These should already work (`len(dict)` is valid). No edit. Just confirm by reading the file.

- [ ] **Step 4: Update line 483 (done callback)**

Find:
```python
self._bot_tasks.discard(task)
```
This is inside a closure that has `game_id` in its enclosing scope. Replace with:
```python
# Pop only if this is still the registered task (avoids clobbering a freshly-resumed task)
if self._bot_tasks.get(game_id) is task:
    self._bot_tasks.pop(game_id, None)
```
If the closure does NOT already have `game_id` accessible, capture it explicitly when constructing the callback (look at the `add_done_callback(...)` call site and ensure `game_id` is closed over).

- [ ] **Step 5: Run existing bot-related tests**

```bash
docker compose exec backend pytest backend/tests/ -k "bot" -v
```
Expected: all PASS. If `test_bot_speed_delay.py` or similar relied on `_bot_tasks` being a set, fix the test to use dict semantics.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/game_service.py
git commit -m "refactor(game-service): _bot_tasks set→dict, add _engine_revision/_recovery_locks"
```

### Task B2: Add `secrets` import

**Files:**
- Modify: `backend/app/services/game_service.py` top imports

- [ ] **Step 1: Add `import secrets`**

In the import block at the top of `game_service.py`, add `import secrets` alongside other stdlib imports.

- [ ] **Step 2: Verify imports compile**

```bash
docker compose exec backend python -c "from app.services.game_service import GameService"
```
Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/game_service.py
git commit -m "chore: import secrets in game_service"
```

---

## Phase C — `start_game` persists metadata (3 tasks)

### Task C1: Define `ENGINE_COMPAT_VERSION` and pass seed via factory

**Files:**
- Modify: `backend/app/services/engine_gateway/factory.py`

- [ ] **Step 1: Add module constant**

At the top of `factory.py`, after imports:

```python
# Engine rule version. Increment by hand in any PR that changes engine BEHAVIOR
# (rule logic, scoring, shuffle algorithm, etc.). Do NOT increment for non-behavior
# changes (logging, refactors, frontend, bot models). This is the primary gate
# for v1 recovery: a recovered game's compat_version must match this constant.
ENGINE_COMPAT_VERSION = 1
```

- [ ] **Step 2: Verify the existing `create_game_engine` already accepts `game_seed`**

```bash
docker compose exec backend grep -A 10 "def create_game_engine" backend/app/services/engine_gateway/factory.py
```
Expected: signature already includes `game_seed: Optional[int] = None`. (Confirmed via earlier exploration.) No change needed.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/engine_gateway/factory.py
git commit -m "feat(engine-gateway): add ENGINE_COMPAT_VERSION constant"
```

### Task C2: Failing test for metadata persistence

**Files:**
- Create: `backend/tests/test_recovery_start_game.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_recovery_start_game.py
"""Spec §8.2 test 1: start_game persists recovery metadata."""
import pytest
from uuid import uuid4

from app.db.models import GameSession
from app.services.game_service import GameService
from app.services.engine_gateway.factory import ENGINE_COMPAT_VERSION


@pytest.mark.usefixtures("db")
def test_start_game_persists_recovery_metadata(db, client_with_three_humans_in_room):
    """After start_game, the games row has game_seed, governor_idx, engine_compat_version, state_revision=0."""
    room_id = client_with_three_humans_in_room.room_id  # fixture provides 3-human waiting room
    service = GameService(db)
    service.start_game(room_id)
    db.refresh(...)  # reload row

    row = db.query(GameSession).filter(GameSession.id == room_id).first()
    assert row.game_seed is not None
    assert isinstance(row.game_seed, int)
    assert 0 <= row.game_seed < 2**63
    assert row.governor_idx in (0, 1, 2)
    assert row.engine_compat_version == ENGINE_COMPAT_VERSION
    assert row.state_revision == 0

    # __engine__ snapshot exists in model_versions
    assert "__engine__" in (row.model_versions or {})
    eng = row.model_versions["__engine__"]
    assert eng["compat_version"] == ENGINE_COMPAT_VERSION
    assert "action_space" in eng
    assert "mayor_semantics" in eng
```

The fixture `client_with_three_humans_in_room` may not exist — check `backend/tests/conftest.py`. If the closest equivalent is `db` + manual GameSession creation, write a small inline helper that builds a 3-player room with `players=[uuid1, uuid2, uuid3]` and `status="WAITING"`.

- [ ] **Step 2: Run test, expect FAIL (start_game doesn't yet persist seed)**

```bash
docker compose exec backend pytest backend/tests/test_recovery_start_game.py -v
```
Expected: FAIL with "row.game_seed is None" or AttributeError.

- [ ] **Step 3: Commit failing test**

```bash
git add backend/tests/test_recovery_start_game.py
git commit -m "test(recovery): start_game persists recovery metadata (red)"
```

### Task C3: Implement metadata persistence in `start_game`

**Files:**
- Modify: `backend/app/services/game_service.py:93-134`
- Modify: `backend/app/services/game_service_support.py` (build_model_versions_snapshot)

- [ ] **Step 1: Add fingerprint helpers in `game_service_support.py`**

Append to `game_service_support.py`:

```python
import hashlib
import json

from app.services.canonical_action import _describe_action, CANONICAL_ACTION_VERSION
# Adjust import paths if these enums live elsewhere — verify with grep before editing.
from configs.constants import TileType, BuildingType


def _action_space_fingerprint() -> str:
    """Stable hash over state-INDEPENDENT branches of _describe_action.

    State-dependent branches (if any are added in the future) are excluded;
    when one is added, this function and ENGINE_COMPAT_VERSION must both bump.
    """
    indices = sorted(set(
        list(range(0, 16))
        + list(range(16, 39))
        + list(range(39, 69))
        + list(range(93, 98))
        + [105]
        + list(range(106, 111))
        + list(range(120, 126))
        + list(range(140, 163))
    ))
    catalog = {i: _describe_action(i, state={}) for i in indices}
    payload = json.dumps({
        "version": CANONICAL_ACTION_VERSION,
        "catalog": catalog,
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _mayor_semantics_fingerprint() -> str:
    payload = json.dumps({
        "island_offset": 120,
        "city_offset": 140,
        "tiles": sorted([(t.name, t.value) for t in TileType]),
        "buildings": sorted([(b.name, b.value) for b in BuildingType]),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
```

- [ ] **Step 2: Embed `__engine__` block in `build_model_versions_snapshot`**

Find `build_model_versions_snapshot(room)` in `game_service_support.py`. At the end (right before `return snapshot`):

```python
    from app.services.engine_gateway.factory import ENGINE_COMPAT_VERSION
    snapshot["__engine__"] = {
        "compat_version": ENGINE_COMPAT_VERSION,
        "action_space": _action_space_fingerprint(),
        "mayor_semantics": _mayor_semantics_fingerprint(),
    }
    return snapshot
```

- [ ] **Step 3: Modify `start_game` to capture seed/governor and persist metadata**

In `backend/app/services/game_service.py`, locate `start_game` (around line 93). Change the body between line 102 and line 111:

```python
    actual_players = len(room.players or [])
    if actual_players < 3:
        raise ValueError(f"Need at least 3 players to start, currently {actual_players}")

    # ===== Recovery v1: explicit seed for journal-replay =====
    game_seed = secrets.randbits(63)
    engine = create_game_engine(
        num_players=actual_players,
        game_seed=game_seed,
        player_control_modes=build_player_control_modes(room),
    )
    GameService.active_engines[game_id] = engine
    GameService._engine_revision[game_id] = 0

    from app.services.engine_gateway.factory import ENGINE_COMPAT_VERSION
    room.status = "PROGRESS"
    room.model_versions = build_model_versions_snapshot(room)
    room.game_seed = game_seed
    room.governor_idx = engine.initial_governor_idx
    room.engine_compat_version = ENGINE_COMPAT_VERSION
    room.state_revision = 0
    self.db.commit()
    # ===== end recovery v1 patch =====

    # (rest of start_game unchanged)
```

- [ ] **Step 4: Run failing test — should now PASS**

```bash
docker compose exec backend pytest backend/tests/test_recovery_start_game.py -v
```
Expected: PASS.

- [ ] **Step 5: Run broader regression**

```bash
docker compose exec backend pytest backend/tests/ -k "start_game or model_version" -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/game_service.py backend/app/services/game_service_support.py
git commit -m "feat(game-service): start_game persists seed/governor/compat_version"
```

---

## Phase D — `process_action` revision tracking (3 tasks)

### Task D1: Failing test for atomic revision increment

**Files:**
- Create: `backend/tests/test_recovery_action_revision.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_recovery_action_revision.py
"""Spec §8.2 test 3: process_action increments state_revision atomically with GameLog write."""
import pytest

from app.db.models import GameSession, GameLog
from app.services.game_service import GameService


def test_action_apply_increments_revision_atomically(db, started_three_human_game):
    """One process_action call -> games.state_revision=1 AND game_logs has revision=1, both committed together."""
    game_id = started_three_human_game.game_id
    actor_id = started_three_human_game.first_actor_id  # whoever's turn it is

    service = GameService(db)
    # Pick a legal action — use action_index for "pass" or first available role.
    # The test fixture should expose a legal action index.
    legal_action_idx = started_three_human_game.first_legal_action_idx

    service.process_action(game_id, actor_id, legal_action_idx, canonical_id=None)

    db.expire_all()
    game = db.query(GameSession).filter(GameSession.id == game_id).first()
    log = (
        db.query(GameLog)
        .filter(GameLog.game_id == game_id)
        .order_by(GameLog.id.desc())
        .first()
    )
    assert game.state_revision == 1
    assert log.revision == 1
    assert log.phase_before is not None
    assert log.active_player_before is not None
    assert log.action_data["action_index"] == legal_action_idx
    assert "canonical_id" in log.action_data
```

The fixture `started_three_human_game` likely doesn't exist — write or extend in `conftest.py`. Pattern: create 3 users, 1 room, call `start_game`, expose `game_id`, `first_actor_id`, and a legal action index from the engine's action_mask.

- [ ] **Step 2: Run, expect FAIL**

```bash
docker compose exec backend pytest backend/tests/test_recovery_action_revision.py -v
```
Expected: FAIL — `process_action` doesn't yet accept `canonical_id`, doesn't write `revision`/`phase_before`/`active_player_before`, doesn't update `state_revision`.

- [ ] **Step 3: Commit failing test**

```bash
git add backend/tests/test_recovery_action_revision.py
git commit -m "test(recovery): atomic revision increment (red)"
```

### Task D2: Modify `process_action` signature and journal write

**Files:**
- Modify: `backend/app/services/game_service.py:136 (signature), 273-287 (GameLog write block), 316 (commit)`

- [ ] **Step 1: Add `canonical_id` keyword arg**

Locate `def process_action(self, game_id, actor_id, action, suppress_broadcast=False)` (around line 136). Change signature to:

```python
def process_action(
    self,
    game_id: UUID,
    actor_id: str,
    action: int,
    canonical_id: Optional[str] = None,
    suppress_broadcast: bool = False,
):
```

`canonical_id` keyword-only via default; backward compatible — bot chain (`sync_callback` at line 415) keeps positional invocation, gets `None`.

- [ ] **Step 2: Capture `phase_before` and `active_player_before` BEFORE engine.step**

Inside `process_action`, find the line where `engine.step(action)` is called. Just BEFORE that call, add:

```python
phase_before_step = engine.current_phase            # Property added in Phase E
active_player_before_step = engine.active_player    # Property added in Phase E
```

These properties don't exist yet — Phase E adds them. For now this code will be staged but won't run until Phase E lands. **In step 4 below we'll re-run the test after Phase E.**

- [ ] **Step 3: Update GameLog row construction (lines 273-287)**

Find:
```python
game_log = GameLog(
    game_id=game_id,
    round=result["info"].get("round", 0),
    step=result["info"].get("step", 0),
    actor_id=actor_id,
    action_data={
        "action": action,
        "model_info": actor_model_info,
    },
    available_options=current_mask,
    state_before=result["state_before"],
    state_after=result["state_after"],
    state_summary=summary,
)
```

Replace with:
```python
new_revision = GameService._engine_revision.get(game_id, 0) + 1
game_log = GameLog(
    game_id=game_id,
    round=result["info"].get("round", 0),
    step=result["info"].get("step", 0),
    actor_id=actor_id,
    action_data={
        "action_index": action,
        "canonical_id": canonical_id,
        "model_info": actor_model_info,
    },
    available_options=current_mask,
    state_before=result["state_before"],
    state_after=result["state_after"],
    state_summary=summary,
    revision=new_revision,
    phase_before=phase_before_step,
    active_player_before=active_player_before_step,
)
self.db.add(game_log)
```

- [ ] **Step 4: Update `state_revision` in same transaction (before line 316 commit)**

Just before the existing `self.db.commit()` at line 316, add:

```python
from sqlalchemy import update
self.db.execute(
    update(GameSession)
    .where(GameSession.id == game_id)
    .values(state_revision=new_revision)
)
GameService._engine_revision[game_id] = new_revision
```

This piggybacks on the existing first commit, so GameLog insert + state_revision update + (FINISHED transition if game ended) are one transaction.

- [ ] **Step 5: Update action route to pass `canonical_id`**

In `backend/app/api/channel/game.py`, find the line `result = service.process_action(game_id, actor_id, action_int)` (around line 102). Change to:
```python
result = service.process_action(game_id, actor_id, action_int, canonical_id=decoded_canonical)
```
`decoded_canonical` is already computed at line 65 from `_describe_action`. Just pass it through.

- [ ] **Step 6: Update `test_db_schema.py` action_data fixtures**

The schema test asserts `action_data` shape. Update fixtures at lines `:143, :165, :201, :223, :259` (verify with grep) from:
```python
action_data={"action": 5, "model_info": {...}}
```
to:
```python
action_data={"action_index": 5, "canonical_id": None, "model_info": {...}}
```

Run schema tests:
```bash
docker compose exec backend pytest backend/tests/test_db_schema.py -v
```
Expected: PASS after fixture updates.

- [ ] **Step 7: Commit (still red on action revision test until Phase E)**

```bash
git add backend/app/services/game_service.py backend/app/api/channel/game.py backend/tests/test_db_schema.py
git commit -m "feat(game-service): process_action writes revision + canonical_id (signature)"
```

### Task D3: Defer test re-run to after Phase E

The `test_action_apply_increments_revision_atomically` test still fails because `engine.current_phase` / `engine.active_player` properties don't exist yet. We re-validate after Phase E.

---

## Phase E — `EngineWrapper` additions (2 tasks)

### Task E1: Add `current_phase`, `active_player`, `replay_step`

**Files:**
- Modify: `backend/app/engine_wrapper/wrapper.py`

- [ ] **Step 1: Add the 3 members**

Inside `EngineWrapper`, append these (anywhere convenient — e.g., near `seed_used` from v0):

```python
    @property
    def current_phase(self) -> str:
        """Phase string normalized via the same map as state_serializer.

        END_ROUND/PROSPECTOR collapse to role_selection. Used by recovery validation.
        """
        from app.services.state_serializer_support import PHASE_TO_STR
        return PHASE_TO_STR.get(self.env.game.current_phase, "role_selection")

    @property
    def active_player(self) -> str:
        """'player_<idx>' format consistent with the rest of the channel contract."""
        return f"player_{self.env.game.current_player_idx}"

    def replay_step(self, action_index: int) -> None:
        """Apply a journal action without persistence side effects.

        No DB write, no logger, no broadcast, no bot scheduling.
        Engine state mutation only. Used by recovery replay.
        """
        self.env.step(action_index)
        self._refresh_cached_view()
```

The `_refresh_cached_view` call mirrors what regular `step` does (line 153) so `last_obs` is current after replay completes.

- [ ] **Step 2: Run Phase D's deferred test — should now PASS**

```bash
docker compose exec backend pytest backend/tests/test_recovery_action_revision.py -v
```
Expected: PASS.

- [ ] **Step 3: Run all engine-related tests**

```bash
docker compose exec backend pytest backend/tests/ -k "engine or wrapper or action" -v
```
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine_wrapper/wrapper.py
git commit -m "feat(engine-wrapper): add current_phase, active_player, replay_step"
```

### Task E2: Test `replay_step` has zero side effects

**Files:**
- Create: `backend/tests/test_recovery_replay_step_isolation.py`

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_recovery_replay_step_isolation.py
"""Spec §8.2 test 12: replay_step does not invoke ML logger / Replay logger / broadcast."""
from unittest.mock import patch

from app.engine_wrapper.wrapper import EngineWrapper


def test_replay_step_does_not_invoke_loggers_or_broadcast():
    wrapper = EngineWrapper(num_players=3, game_seed=42)

    with patch("app.services.ml_logger.MLLogger.log_transition") as ml, \
         patch("app.services.replay_logger.ReplayLogger.append_entry") as rl, \
         patch("app.services.ws_manager.manager.broadcast_to_game") as wsbc:
        # Apply 5 legal actions via replay_step
        for _ in range(5):
            mask = wrapper.get_action_mask()
            legal_idx = next(i for i, v in enumerate(mask) if v)
            wrapper.replay_step(legal_idx)

        ml.assert_not_called()
        rl.assert_not_called()
        wsbc.assert_not_called()
```

- [ ] **Step 2: Run**

```bash
docker compose exec backend pytest backend/tests/test_recovery_replay_step_isolation.py -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_recovery_replay_step_isolation.py
git commit -m "test(recovery): replay_step has no persistence side effects"
```

---

## Phase F — `ensure_engine_loaded` + lock infrastructure (4 tasks)

### Task F1: `_recovery_locks_meta_lock` and `_get_or_create_recovery_lock`

**Files:**
- Modify: `backend/app/services/game_service.py`

- [ ] **Step 1: Add module-level meta lock**

At module top of `game_service.py`, after imports:

```python
_recovery_locks_meta_lock = asyncio.Lock()  # protects _recovery_locks dict mutations
```

(Module-level so it's not re-created per GameService instance.)

- [ ] **Step 2: Add `_get_or_create_recovery_lock` method**

Inside `GameService`:

```python
    async def _get_or_create_recovery_lock(self, game_id: UUID) -> asyncio.Lock:
        global _recovery_locks_meta_lock
        async with _recovery_locks_meta_lock:
            lock = GameService._recovery_locks.get(game_id)
            if lock is None:
                lock = asyncio.Lock()
                GameService._recovery_locks[game_id] = lock
            return lock
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/game_service.py
git commit -m "feat(game-service): per-game recovery lock infrastructure"
```

### Task F2: `ensure_engine_loaded` async wrapper

**Files:**
- Modify: `backend/app/services/game_service.py`

- [ ] **Step 1: Add `EngineLoadResult` dataclass and method**

Near the top of `game_service.py`, after imports, add:

```python
from dataclasses import dataclass
from typing import Literal


@dataclass
class EngineLoadResult:
    state: Literal["ready", "blocked"]
    reason: Optional[str] = None
    state_revision: Optional[int] = None
```

Inside `GameService`:

```python
    async def ensure_engine_loaded(self, game_id: UUID) -> EngineLoadResult:
        if game_id in GameService.active_engines:
            return EngineLoadResult(
                state="ready",
                state_revision=GameService._engine_revision.get(game_id, 0),
            )
        lock = await self._get_or_create_recovery_lock(game_id)
        async with lock:
            # Re-check after acquiring lock; another caller may have just finished recovery.
            if game_id in GameService.active_engines:
                return EngineLoadResult(
                    state="ready",
                    state_revision=GameService._engine_revision.get(game_id, 0),
                )
            return await asyncio.to_thread(self._do_recovery_sync, game_id)
```

- [ ] **Step 2: Commit (still won't work; needs `_do_recovery_sync`)**

```bash
git add backend/app/services/game_service.py
git commit -m "feat(game-service): ensure_engine_loaded async + single-flight"
```

### Task F3: `_do_recovery_sync` and `_mark_blocked`

**Files:**
- Modify: `backend/app/services/game_service.py`

- [ ] **Step 1: Implement `_mark_blocked`**

```python
    def _mark_blocked(self, game_id: UUID, reason: str) -> None:
        from sqlalchemy import update
        with SessionLocal() as db:
            db.execute(
                update(GameSession)
                .where(GameSession.id == game_id)
                .values(status="RECOVERY_BLOCKED", recovery_blocked_reason=reason)
            )
            db.commit()
        GameService._recovery_locks.pop(game_id, None)
        logger.warning("[RECOVERY] blocked game=%s reason=%s", game_id, reason)
```

- [ ] **Step 2: Implement `_do_recovery_sync`**

```python
    def _do_recovery_sync(self, game_id: UUID) -> EngineLoadResult:
        from app.services.engine_gateway.factory import ENGINE_COMPAT_VERSION
        with SessionLocal() as db:
            game = db.query(GameSession).filter(GameSession.id == game_id).first()
            if not game or game.status != "PROGRESS":
                return EngineLoadResult(state="blocked", reason="not_recoverable")

            if game.game_seed is None or game.engine_compat_version is None:
                self._mark_blocked(game_id, "no_metadata")
                return EngineLoadResult(state="blocked", reason="no_metadata")

            if game.engine_compat_version != ENGINE_COMPAT_VERSION:
                self._mark_blocked(game_id, "engine_version_mismatch")
                return EngineLoadResult(state="blocked", reason="engine_version_mismatch")

            # Auxiliary fingerprint check
            from app.services.game_service_support import (
                _action_space_fingerprint,
                _mayor_semantics_fingerprint,
            )
            stored = (game.model_versions or {}).get("__engine__", {})
            if (
                stored.get("action_space") != _action_space_fingerprint()
                or stored.get("mayor_semantics") != _mayor_semantics_fingerprint()
            ):
                self._mark_blocked(game_id, "fingerprint_mismatch")
                return EngineLoadResult(state="blocked", reason="fingerprint_mismatch")

            # Fresh engine
            engine = create_game_engine(
                num_players=game.num_players,
                game_seed=game.game_seed,
            )
            if engine.initial_governor_idx != game.governor_idx:
                self._mark_blocked(game_id, "replay_validation_failed")
                return EngineLoadResult(state="blocked", reason="replay_validation_failed")

            # Journal
            entries = (
                db.query(GameLog)
                .filter(GameLog.game_id == game_id, GameLog.revision.isnot(None))
                .order_by(GameLog.revision)
                .all()
            )
            expected_rev = 0
            for e in entries:
                expected_rev += 1
                if e.revision != expected_rev:
                    self._mark_blocked(game_id, "journal_corrupt")
                    return EngineLoadResult(state="blocked", reason="journal_corrupt")

            # Replay
            for e in entries:
                if engine.current_phase != e.phase_before or engine.active_player != e.active_player_before:
                    self._mark_blocked(game_id, "replay_validation_failed")
                    return EngineLoadResult(state="blocked", reason="replay_validation_failed")
                try:
                    engine.replay_step(int(e.action_data["action_index"]))
                except Exception:
                    logger.exception(
                        "[RECOVERY] replay_step failed game=%s revision=%d",
                        game_id, e.revision,
                    )
                    self._mark_blocked(game_id, "replay_validation_failed")
                    return EngineLoadResult(state="blocked", reason="replay_validation_failed")

            # Final check
            if game.state_revision != len(entries):
                self._mark_blocked(game_id, "replay_validation_failed")
                return EngineLoadResult(state="blocked", reason="replay_validation_failed")

            # Register in memory
            GameService.active_engines[game_id] = engine
            GameService._engine_revision[game_id] = game.state_revision

            # Refresh Redis cache + meta
            rich_state = build_rich_state(db, game_id, engine, game)
            self._sync_to_redis(game_id, rich_state)
            self._store_game_meta(game_id, game)

            # Bot resume (Phase H)
            self._maybe_resume_bot(game_id, game, engine)

            return EngineLoadResult(state="ready", state_revision=game.state_revision)
```

`_maybe_resume_bot` is added in Phase H. Define it as a stub now:

```python
    def _maybe_resume_bot(self, game_id: UUID, room: GameSession, engine: EngineWrapper) -> None:
        # Phase H fills this in. For now, no-op.
        pass
```

- [ ] **Step 2: Run a smoke check — code compiles**

```bash
docker compose exec backend python -c "from app.services.game_service import GameService; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/game_service.py
git commit -m "feat(game-service): _do_recovery_sync + _mark_blocked"
```

### Task F4: Tests for normal recovery (3 tests)

**Files:**
- Create: `backend/tests/test_recovery_lazy_load.py`

- [ ] **Step 1: Write the 3 tests**

```python
# backend/tests/test_recovery_lazy_load.py
"""Spec §8.2 tests 4, 5, 6: lazy recovery behavior."""
import asyncio
from uuid import UUID

import pytest

from app.services.game_service import GameService


@pytest.mark.asyncio
async def test_lazy_recovery_on_action_endpoint_after_engine_eviction(
    db, started_three_human_game, http_client
):
    """Game running, evict engine from memory, post next action — engine recovered transparently."""
    game_id = started_three_human_game.game_id
    actor_id = started_three_human_game.first_actor_id
    legal_idx = started_three_human_game.first_legal_action_idx
    canonical = started_three_human_game.first_legal_canonical_id

    # Apply 5 actions normally
    service = GameService(db)
    for _ in range(5):
        # Use the test client's action endpoint to drive realistic flow
        # ... (test fixture detail)
        pass

    # Evict the engine
    GameService.active_engines.pop(game_id, None)
    GameService._engine_revision.pop(game_id, None)

    # Next action triggers lazy recovery
    response = await http_client.post(
        f"/api/puco/game/{game_id}/action",
        json={"action_index": legal_idx, "canonical_id": canonical},
    )
    assert response.status_code == 200
    # Engine is back in memory
    assert game_id in GameService.active_engines


@pytest.mark.asyncio
async def test_lazy_recovery_on_ws_connect_emits_state_update_once(
    started_three_human_game, ws_client_factory
):
    """WS connect after engine eviction triggers recovery and sends STATE_UPDATE exactly once after auth_ok."""
    game_id = started_three_human_game.game_id
    GameService.active_engines.pop(game_id, None)

    async with ws_client_factory(game_id) as ws:
        await ws.send_json({"token": started_three_human_game.first_player_token})
        msgs = []
        for _ in range(3):  # auth_ok + STATE_UPDATE + maybe RECOVERY_STARTED
            msgs.append(await ws.receive_json())
        types = [m["type"] for m in msgs]
        assert "auth_ok" in types
        assert types.count("STATE_UPDATE") == 1
        # data.meta.step_count reflects recovered position
        state_msg = next(m for m in msgs if m["type"] == "STATE_UPDATE")
        assert "step_count" in state_msg["data"]["meta"]


@pytest.mark.asyncio
async def test_concurrent_recovery_runs_replay_only_once(started_three_human_game, monkeypatch):
    """10 concurrent ensure_engine_loaded calls with same game_id replay journal exactly once."""
    game_id = started_three_human_game.game_id
    GameService.active_engines.pop(game_id, None)

    call_count = {"replay_step": 0}

    from app.engine_wrapper.wrapper import EngineWrapper
    original = EngineWrapper.replay_step

    def counting_replay(self, action_index):
        call_count["replay_step"] += 1
        return original(self, action_index)

    monkeypatch.setattr(EngineWrapper, "replay_step", counting_replay)

    service = GameService(db=None)  # ensure_engine_loaded opens its own session
    results = await asyncio.gather(*[
        service.ensure_engine_loaded(game_id) for _ in range(10)
    ])

    # All callers got ready
    assert all(r.state == "ready" for r in results)
    # replay_step was invoked at most equal to journal length (single-flight)
    journal_len = started_three_human_game.action_count
    assert call_count["replay_step"] == journal_len
```

These tests need fixtures (`started_three_human_game`, `http_client`, `ws_client_factory`). Create or reuse from `backend/tests/conftest.py`. The 5-action loop in the first test can use the existing API client.

- [ ] **Step 2: Run**

```bash
docker compose exec backend pytest backend/tests/test_recovery_lazy_load.py -v
```
Expected: tests fail until WS handler + action route call `ensure_engine_loaded` (Phase J), but at least the third test (`concurrent_recovery`) should pass independently — it calls `ensure_engine_loaded` directly. If that one passes, lock infrastructure works.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_recovery_lazy_load.py
git commit -m "test(recovery): lazy load + single-flight (red until Phase J)"
```

---

## Phase G — Recovery validation paths (3 tests)

### Task G1: Tests for blocked states

**Files:**
- Create: `backend/tests/test_recovery_blocked_states.py`

- [ ] **Step 1: Write the 3 tests**

```python
# backend/tests/test_recovery_blocked_states.py
"""Spec §8.2 tests 7, 8, 9: recovery_blocked entry conditions."""
import pytest
from uuid import UUID, uuid4

from app.db.models import GameSession, GameLog
from app.services.game_service import GameService
from app.services.engine_gateway.factory import ENGINE_COMPAT_VERSION


@pytest.mark.asyncio
async def test_recovery_blocked_when_metadata_absent(db):
    """A PROGRESS game with NULL game_seed transitions to RECOVERY_BLOCKED on first access."""
    game_id = uuid4()
    db.add(GameSession(
        id=game_id, status="PROGRESS",
        num_players=3, players=[uuid4(), uuid4(), uuid4()],
        game_seed=None,                    # critical: pre-patch / unrecoverable
        engine_compat_version=None,
        state_revision=0,
    ))
    db.commit()

    service = GameService(db)
    result = await service.ensure_engine_loaded(game_id)

    assert result.state == "blocked"
    assert result.reason == "no_metadata"

    db.expire_all()
    row = db.query(GameSession).filter(GameSession.id == game_id).first()
    assert row.status == "RECOVERY_BLOCKED"
    assert row.recovery_blocked_reason == "no_metadata"


@pytest.mark.asyncio
async def test_recovery_blocked_when_engine_compat_version_mismatch(db):
    """A game with engine_compat_version != current transitions to RECOVERY_BLOCKED."""
    game_id = uuid4()
    db.add(GameSession(
        id=game_id, status="PROGRESS",
        num_players=3, players=[uuid4(), uuid4(), uuid4()],
        game_seed=12345,
        engine_compat_version=ENGINE_COMPAT_VERSION + 99,  # mismatch
        state_revision=0,
    ))
    db.commit()

    service = GameService(db)
    result = await service.ensure_engine_loaded(game_id)

    assert result.state == "blocked"
    assert result.reason == "engine_version_mismatch"


@pytest.mark.asyncio
async def test_recovery_blocked_when_journal_validation_fails(db, started_three_human_game):
    """Journal entry with phase_before mismatch triggers replay_validation_failed."""
    game_id = started_three_human_game.game_id
    GameService.active_engines.pop(game_id, None)

    # Corrupt journal: change phase_before of last entry to a clearly wrong value
    log = (
        db.query(GameLog)
        .filter(GameLog.game_id == game_id)
        .order_by(GameLog.id.desc())
        .first()
    )
    log.phase_before = "definitely_not_a_real_phase"
    db.commit()

    service = GameService(db)
    result = await service.ensure_engine_loaded(game_id)
    assert result.state == "blocked"
    assert result.reason == "replay_validation_failed"
```

- [ ] **Step 2: Run**

```bash
docker compose exec backend pytest backend/tests/test_recovery_blocked_states.py -v
```
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_recovery_blocked_states.py
git commit -m "test(recovery): blocked states (no_metadata / version_mismatch / validation_failed)"
```

---

## Phase H — Bot resume single-flight (3 tasks)

### Task H1: Implement `_maybe_resume_bot`

**Files:**
- Modify: `backend/app/services/game_service.py` (replace stub from Phase F)

- [ ] **Step 1: Replace stub with real implementation**

```python
    def _maybe_resume_bot(self, game_id: UUID, room: GameSession, engine: EngineWrapper) -> None:
        if room.status != "PROGRESS":
            return
        if GameService._game_paused.get(game_id, False):
            return

        active_idx = engine.env.game.current_player_idx
        players = list(room.players or [])
        if active_idx >= len(players):
            return
        actor_id = players[active_idx]
        if not str(actor_id).startswith("BOT_"):
            return

        existing = GameService._bot_tasks.get(game_id)
        if existing is not None and not existing.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Recovery happened in a worker thread without a running loop.
            # Bot scheduling will fire on next request that reaches an async route.
            return

        task = loop.create_task(self._run_bot_turn(game_id, room, engine))
        GameService._bot_tasks[game_id] = task
        task.add_done_callback(
            lambda t, gid=game_id: (
                GameService._bot_tasks.pop(gid, None)
                if GameService._bot_tasks.get(gid) is t else None
            )
        )
```

`_run_bot_turn` already exists in `game_service.py` (driven by `_schedule_next_bot_turn_if_needed`). Reuse — confirm signature with grep.

Note the `loop = asyncio.get_running_loop()` guard: `_do_recovery_sync` runs in `asyncio.to_thread`, which doesn't have a running loop. In that case, defer bot scheduling to the next async request — acceptable degradation.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/game_service.py
git commit -m "feat(game-service): _maybe_resume_bot single-flight bot scheduling"
```

### Task H2: Tests for bot resume

**Files:**
- Create: `backend/tests/test_recovery_bot_resume.py`

- [ ] **Step 1: Write 2 tests**

```python
# backend/tests/test_recovery_bot_resume.py
"""Spec §8.2 tests 10, 11: bot resume after recovery."""
import asyncio
import pytest

from app.services.game_service import GameService


@pytest.mark.asyncio
async def test_recovery_resumes_bot_turn_exactly_once(db, started_game_with_bot_active_turn):
    """After recovery, if active player is bot, exactly one bot task is scheduled."""
    game_id = started_game_with_bot_active_turn.game_id
    GameService.active_engines.pop(game_id, None)
    GameService._bot_tasks.pop(game_id, None)

    service = GameService(db)
    await service.ensure_engine_loaded(game_id)

    task = GameService._bot_tasks.get(game_id)
    assert task is not None
    # Calling ensure_engine_loaded again does NOT spawn another task
    await service.ensure_engine_loaded(game_id)
    assert GameService._bot_tasks.get(game_id) is task


@pytest.mark.asyncio
async def test_bot_resume_does_not_trigger_when_human_turn_active(db, started_three_human_game):
    """Human turn -> no bot task spawned by recovery."""
    game_id = started_three_human_game.game_id
    GameService.active_engines.pop(game_id, None)
    GameService._bot_tasks.pop(game_id, None)

    service = GameService(db)
    await service.ensure_engine_loaded(game_id)

    assert GameService._bot_tasks.get(game_id) is None
```

Fixture `started_game_with_bot_active_turn` may need creation: 1 human + 2 bots, advance to a state where bot is active.

- [ ] **Step 2: Run**

```bash
docker compose exec backend pytest backend/tests/test_recovery_bot_resume.py -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_recovery_bot_resume.py
git commit -m "test(recovery): bot resume single-flight"
```

---

## Phase I — WS init sync + recovery messages (2 tasks)

### Task I1: Modify `ws.py` for recovery + state push

**Files:**
- Modify: `backend/app/api/channel/ws.py:80-83`

- [ ] **Step 1: Insert recovery + state push between `auth_ok` and `manager.connect`**

Find lines 80-83:
```python
    await websocket.send_json({"type": "auth_ok", "player_id": player_id})
    logger.warning("[WS_TRACE] ws_auth_ok_sent ...")

    await manager.connect(game_id, websocket, player_id=player_id)
```

Replace with:
```python
    await websocket.send_json({"type": "auth_ok", "player_id": player_id})
    logger.warning("[WS_TRACE] ws_auth_ok_sent ...")

    # Recovery v1: lazy ensure engine + push current state (or RECOVERY_BLOCKED)
    from app.services.game_service import GameService
    from uuid import UUID
    service = GameService(None)  # ensure_engine_loaded opens its own session via to_thread
    load_result = await service.ensure_engine_loaded(UUID(game_id))

    if load_result.state == "blocked":
        last_state = await service._fetch_last_rich_state(UUID(game_id))
        if last_state is not None:
            await websocket.send_json({"type": "STATE_UPDATE", "data": last_state})
        await websocket.send_json({
            "type": "RECOVERY_BLOCKED",
            "reason": load_result.reason,
        })
    else:  # ready
        rich_state = await service._fetch_or_build_rich_state(UUID(game_id))
        await websocket.send_json({"type": "STATE_UPDATE", "data": rich_state})

    await manager.connect(game_id, websocket, player_id=player_id)
```

Note: the `with SessionLocal() as db:` block at lines 57-60 already closes before line 80, so awaiting recovery here doesn't hold a sync session. (Verified in spec §14.13.)

- [ ] **Step 2: Add the two helpers to GameService**

In `game_service.py`:

```python
    async def _fetch_last_rich_state(self, game_id: UUID) -> Optional[Dict]:
        cached = redis_client.get(f"game:{game_id}:state")
        if cached:
            return json.loads(cached)
        return await asyncio.to_thread(self._read_last_rich_state_from_replay_log, game_id)

    def _read_last_rich_state_from_replay_log(self, game_id: UUID) -> Optional[Dict]:
        """Fall back to data/logs/replay/<game_id>.json — last rich_state entry."""
        import os, json
        path = f"data/logs/replay/{game_id}.json"
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        for entry in reversed(doc.get("entries") or []):
            if entry.get("rich_state"):
                return entry["rich_state"]
        return None

    async def _fetch_or_build_rich_state(self, game_id: UUID) -> Dict:
        engine = GameService.active_engines.get(game_id)
        if engine is not None:
            return await asyncio.to_thread(self._build_rich_state_sync, game_id, engine)
        cached = redis_client.get(f"game:{game_id}:state")
        return json.loads(cached) if cached else {}

    def _build_rich_state_sync(self, game_id: UUID, engine: EngineWrapper) -> Dict:
        with SessionLocal() as db:
            room = db.query(GameSession).filter(GameSession.id == game_id).first()
            return build_rich_state(db, game_id, engine, room)
```

- [ ] **Step 3: Run WS tests**

```bash
docker compose exec backend pytest backend/tests/test_game_ws_auth_contract.py backend/tests/test_recovery_lazy_load.py -v
```
Expected: existing auth contract tests still PASS. Lazy-load test 5 (`test_lazy_recovery_on_ws_connect_emits_state_update_once`) should now PASS too.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/channel/ws.py backend/app/services/game_service.py
git commit -m "feat(ws): emit STATE_UPDATE/RECOVERY_BLOCKED on connect after recovery"
```

### Task I2: `RECOVERY_STARTED` for long replays

**Files:**
- Modify: `backend/app/services/game_service.py` (`_do_recovery_sync`)

- [ ] **Step 1: Add notification when journal is large**

In `_do_recovery_sync`, between the `expected_rev` ordering check and the replay loop, add:

```python
            # Hint to client that this may take a while (spec §6.3 step 6)
            if len(entries) >= 30:
                self._broadcast_recovery_started(game_id)
```

Implement `_broadcast_recovery_started`:

```python
    def _broadcast_recovery_started(self, game_id: UUID) -> None:
        try:
            redis_client.publish(
                f"game:{game_id}:events",
                json.dumps({"type": "RECOVERY_STARTED"}),
            )
        except Exception:
            logger.warning("[RECOVERY] could not broadcast RECOVERY_STARTED game=%s", game_id, exc_info=True)
```

Connected WS clients receive this through the existing Redis subscriber path that already routes `:events` to ws broadcasts.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/game_service.py
git commit -m "feat(recovery): broadcast RECOVERY_STARTED for long replays"
```

---

## Phase J — REST routes await recovery (3 tasks)

### Task J1: Action route awaits ensure_engine_loaded

**Files:**
- Modify: `backend/app/api/channel/game.py` action route (`channel_action` near line 60)

- [ ] **Step 1: Add `await ensure_engine_loaded` at route entry**

Right after the route's existing input parsing but before `service.process_action(...)` at line 102, insert:

```python
    load_result = await service.ensure_engine_loaded(game_id)
    if load_result.state == "blocked":
        raise HTTPException(
            status_code=409,
            detail={"error": "recovery_blocked", "reason": load_result.reason},
        )
```

- [ ] **Step 2: Run lazy-load test 4 — should now PASS**

```bash
docker compose exec backend pytest backend/tests/test_recovery_lazy_load.py::test_lazy_recovery_on_action_endpoint_after_engine_eviction -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/channel/game.py
git commit -m "feat(action-route): ensure_engine_loaded gate at route entry"
```

### Task J2: Convert playback routes to async + recovery gate

**Files:**
- Modify: `backend/app/api/channel/playback.py:27, 40`

- [ ] **Step 1: Convert `def get_playback` to `async def`**

Find:
```python
@router.get("/{game_id}/playback", response_model=PlaybackState)
def get_playback(...):
```
Change to:
```python
@router.get("/{game_id}/playback", response_model=PlaybackState)
async def get_playback(...):
    load_result = await service.ensure_engine_loaded(UUID(game_id))
    if load_result.state == "blocked":
        raise HTTPException(409, detail={"error": "recovery_blocked", "reason": load_result.reason})
    # ... rest of original body
```

- [ ] **Step 2: Convert `def set_speed` to `async def`** (same pattern)

- [ ] **Step 3: Run playback tests**

```bash
docker compose exec backend pytest backend/tests/test_playback_api.py backend/tests/test_game_speed_state.py -v
```
Expected: all PASS. FastAPI's TestClient handles async routes transparently.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/channel/playback.py
git commit -m "feat(playback): async routes + ensure_engine_loaded gate"
```

### Task J3: final-score route gate

**Files:**
- Modify: `backend/app/api/channel/game.py` final-score route (around line 198)

- [ ] **Step 1: Add ensure_engine_loaded gate for PROGRESS games**

Find the final-score handler. If it's already `async def`, just add:
```python
    if room.status == "PROGRESS":
        load_result = await service.ensure_engine_loaded(game_id)
        if load_result.state == "blocked":
            raise HTTPException(409, detail={"error": "recovery_blocked", "reason": load_result.reason})
```
before the engine access. `FINISHED` games don't need recovery — final scores are persisted.

- [ ] **Step 2: Run final-score test**

```bash
docker compose exec backend pytest backend/tests/test_final_score_access.py -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/channel/game.py
git commit -m "feat(final-score): ensure_engine_loaded gate for PROGRESS"
```

---

## Phase K — Frontend (3 tasks)

### Task K1: Hook callbacks

**Files:**
- Modify: `frontend/src/hooks/useGameWebSocket.ts:7-32`

- [ ] **Step 1: Extend the options type and switch handler**

Find the options-object type definition. Add two optional callbacks:

```ts
export type UseGameWebSocketOptions = {
  // ... existing props ...
  onRecoveryStarted?: () => void
  onRecoveryBlocked?: (msg: { reason: string }) => void
}
```

Find the `switch` on `message.type` inside `onmessage`. Add:
```ts
case 'RECOVERY_STARTED':
  onRecoveryStarted?.()
  break
case 'RECOVERY_BLOCKED':
  onRecoveryBlocked?.({ reason: message.reason })
  break
```

- [ ] **Step 2: Wire UI in `GameScreen.tsx` (or equivalent caller)**

Find where `useGameWebSocket(...)` is invoked at the top level. Add local state:
```tsx
const [recoveryOverlay, setRecoveryOverlay] = useState(false)
const [recoveryBlocked, setRecoveryBlocked] = useState<{ reason: string } | null>(null)

useGameWebSocket({
  // ... existing props ...
  onRecoveryStarted: () => setRecoveryOverlay(true),
  onRecoveryBlocked: (msg) => {
    setRecoveryBlocked(msg)
    setRecoveryOverlay(false)
  },
  onStateUpdate: (data) => {
    setRecoveryOverlay(false)
    /* existing handler that sets gameState */
  },
})
```

Render overlay/banner:
```tsx
{recoveryOverlay && <div className="recovery-overlay">게임 복구 중…</div>}
{recoveryBlocked && (
  <div className="recovery-blocked-modal">
    <p>이 게임은 복구할 수 없습니다 (사유: {recoveryBlocked.reason})</p>
    <button onClick={() => setRecoveryBlocked(null)}>그대로 보기</button>
    <button onClick={() => sendEndGame()}>종료</button>
  </div>
)}
```

`sendEndGame` reuses the existing `END_GAME_REQUEST` send path.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useGameWebSocket.ts frontend/src/components/GameScreen.tsx
git commit -m "feat(frontend): RECOVERY_STARTED/BLOCKED handlers + overlay UI"
```

### Task K2: Frontend tests

**Files:**
- Modify: `frontend/src/hooks/__tests__/useGameWebSocket.test.ts`

- [ ] **Step 1: Add 3 tests**

```ts
it('recovery_started_shows_overlay', async () => {
  const onRecoveryStarted = vi.fn()
  renderHook(() => useGameWebSocket({ ..., onRecoveryStarted }))
  await server.send({ type: 'RECOVERY_STARTED' })
  expect(onRecoveryStarted).toHaveBeenCalledOnce()
})

it('state_update_after_recovery_clears_overlay', async () => {
  const onRecoveryStarted = vi.fn()
  const onStateUpdate = vi.fn()
  renderHook(() => useGameWebSocket({ ..., onRecoveryStarted, onStateUpdate }))
  await server.send({ type: 'RECOVERY_STARTED' })
  await server.send({ type: 'STATE_UPDATE', data: { meta: { step_count: 7 } } })
  expect(onRecoveryStarted).toHaveBeenCalledOnce()
  expect(onStateUpdate).toHaveBeenCalledOnce()
})

it('recovery_blocked_disables_input_and_shows_modal', async () => {
  const onRecoveryBlocked = vi.fn()
  renderHook(() => useGameWebSocket({ ..., onRecoveryBlocked }))
  await server.send({ type: 'RECOVERY_BLOCKED', reason: 'no_metadata' })
  expect(onRecoveryBlocked).toHaveBeenCalledWith({ reason: 'no_metadata' })
})
```

`server.send` is the test harness — match the existing pattern in the file.

- [ ] **Step 2: Run**

```bash
docker compose exec frontend npm run test -- useGameWebSocket
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/__tests__/useGameWebSocket.test.ts
git commit -m "test(frontend): RECOVERY_STARTED/BLOCKED handler tests"
```

### Task K3: Frontend lint + build

- [ ] **Step 1: Type check + build**

```bash
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run build
```
Expected: no errors.

- [ ] **Step 2: Commit if anything was fixed**

---

## Phase L — Final integration (2 tasks)

### Task L1: Full backend regression

- [ ] **Step 1: Run full backend test suite**

```bash
docker compose exec backend pytest backend/tests/ -v --maxfail=5
```
Expected: all PASS. Pay attention to:
- `contract.md` §7 listed tests
- `test_db_schema.py` (action_data shape)
- `test_game_action.py` (process_action signature)
- `test_model_version_snapshot.py` (new __engine__ key)

- [ ] **Step 2: Run PuCo_RL test suite (no regression from v0)**

```bash
docker compose exec backend pytest /app/PuCo_RL/tests/ -v
```
Expected: all PASS.

### Task L2: Manual smoke test

- [ ] **Step 1: Start a 1-human + 2-bot game, restart backend mid-game**

```bash
docker compose up -d --build
# In browser: log in, create bot game, watch a few rounds
docker compose restart backend
# Reload the game page
# Verify: RECOVERY_STARTED overlay → STATE_UPDATE → bot resumes its turn
```

- [ ] **Step 2: Verify DB state**

```bash
docker compose exec db psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl -c "
  SELECT id, status, game_seed, governor_idx, engine_compat_version, state_revision, recovery_blocked_reason
  FROM games
  ORDER BY created_at DESC LIMIT 3;
"
```
Expected: `state_revision` matches the number of GameLog rows for the game; `engine_compat_version=1`.

- [ ] **Step 3: Verify journal**

```bash
docker compose exec db psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl -c "
  SELECT game_id, revision, phase_before, active_player_before, action_data->>'action_index' AS action_idx
  FROM game_logs
  WHERE game_id = '<latest>'
  ORDER BY revision;
"
```
Expected: `revision` is consecutive 1, 2, 3, ...; `phase_before` and `active_player_before` populated; `action_data` has `action_index` and `canonical_id` keys.

- [ ] **Step 4: Final commit if smoke surfaced any fixes**

---

## Merge checklist (before opening PR)

- [ ] All 12 backend tests in spec §8.2 pass.
- [ ] All 3 frontend tests in spec §8.3 pass.
- [ ] Existing contract.md §7 regression tests pass.
- [ ] Manual smoke test (Task L2) succeeds.
- [ ] No `random.*` or `np.random.*` calls regressed in `engine.py`/`pr_env.py` (v0 invariant).
- [ ] `_bot_tasks` is dict everywhere (no remaining `.add(task)` / `.discard(task)` calls except inside `done_callback` migration).
- [ ] `process_action` accepts `canonical_id`; action route passes it.
- [ ] All `ensure_engine_loaded` callers (action route, ws, playback, final-score) handle `blocked` state.
- [ ] Migration up→down→up roundtrips cleanly.

## Out of scope (deferred to v2 / separate PRs)

- `action_intent_id` / `expected_state_revision` on `ActionRequestPayload` (v2 idempotency).
- DB pool reduction, `/health` decomposition, `OMP_NUM_THREADS` (footprint optimization, separate PR).
- Multi-human abandonment timeout policy (separate spec).
- Pre-patch `PROGRESS` row batch cleanup (operational, separate spec).
- CI guard for `ENGINE_COMPAT_VERSION` not bumped on engine.py changes (separate small PR).

## Risk and rollback

Each phase commits independently. To roll back v1:
1. `git revert` the relevant commits (in reverse order).
2. `docker compose exec backend alembic downgrade -1` to drop the schema columns.

The migration is non-destructive (only adds columns); rolling back loses recovery metadata for games started after v1 deploy but doesn't damage existing data.
