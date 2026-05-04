# Shutdown Recovery v2 — Human Action Idempotency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **PREREQUISITE:** v1 plan (`2026-05-02-shutdown-recovery-v1-lazy-recovery.md`) must be merged. This plan assumes `games.state_revision` exists, `_engine_revision` dict is in `GameService`, `process_action` accepts `canonical_id` keyword arg, `RECOVERY_BLOCKED` status exists.

**Goal:** Make human action submissions **at-most-once safe** — same click never applied twice, stale (out-of-date) actions are rejected with explicit error, and clients self-resync. Closes the race window between v1's recovery and the frontend's optimistic submit pattern.

**Architecture:**
- Each human click generates a fresh UUID `action_intent_id` and includes the player's last-seen `expected_state_revision`.
- Server side: `(game_id, action_intent_id)` is unique in `game_logs` → duplicate intent returns the original result without re-applying. `expected_state_revision` mismatch returns `409 stale_state` and the client resyncs from latest `STATE_UPDATE`.
- Bot actions don't carry intent_id (they're server-internal, never retried) — both fields stay NULL for bot rows.
- Frontend `channelAction` helper generates UUID per click; `useGameWebSocket` tracks latest revision from incoming `STATE_UPDATE`; on 409 stale_state, the client waits for the next `STATE_UPDATE` instead of retrying.

**Tech Stack:** Same as v1 — FastAPI, SQLAlchemy 2.0 sync, Alembic, React+TypeScript, pytest, vitest. UUIDs via `crypto.randomUUID()` on the client and Python's `uuid.uuid4()` on the server-side fixtures.

**Spec:** `docs/superpowers/specs/2026-05-02-shutdown-recovery-supplement-design.md` §10. Original concept in `docs/shutdown_error.md` §6.4 + §7 (시나리오 A~E).

**Context for the worker:**
- `ActionRequestPayload` is in `backend/app/schemas/game.py:9-14` with `extra="forbid"` (contract §2.5). Adding fields is breaking for any client that uses unknown-key forbidding — but Pydantic with `extra="forbid"` rejects EXTRA keys, not MISSING keys. Optional fields are fine.
- Action route at `backend/app/api/channel/game.py:60` already computes `decoded_canonical` and passes it to `process_action` (after v1).
- Bot chain in `game_service.py` uses `sync_callback` (`:415`) which does positional-arg invocation — adding keyword-only params is backward compatible.
- Memory rule: tests in Docker only. Never push to remote.

---

## Decisions baked in (from spec review)

1. **Both fields are `Optional`** in the schema, not required. This allows a transition period where backend accepts both old and new payloads. After frontend is fully rolled out, both are always sent in practice.
2. **Duplicate intent → 200 success with cached result** (not error). The original write happened, the response was lost, the retry just gets the same response. Includes a `duplicate: true` flag for client telemetry.
3. **Stale revision → 409 stale_state**. No engine change. Body shape mirrors v1's `canonical_id_mismatch` 422.
4. **Bot actions stay NULL** for both fields. Unique constraint is `WHERE action_intent_id IS NOT NULL` so bots never collide.
5. **`expected_state_revision` is checked BEFORE intent dedupe**. If client is stale AND retried, server tells them "you're stale" rather than silently returning a stale-cached result.

---

## File Structure

| File | Type | Responsibility |
|---|---|---|
| `backend/alembic/versions/<ts>_action_intent_id.py` | Create | Add `action_intent_id` column + partial unique index. |
| `backend/app/db/models.py` | Modify | Declare `action_intent_id` on `GameLog`. |
| `backend/app/schemas/game.py` | Modify | Add optional `action_intent_id` and `expected_state_revision` to `ActionRequestPayload`. |
| `backend/app/services/game_service.py` | Modify | `process_action` accepts new params. Stale check + dedupe lookup BEFORE engine.step. |
| `backend/app/api/channel/game.py` | Modify | Pass new fields to process_action. Translate `StaleRevisionError` to 409. |
| `frontend/src/App.tsx` (or wherever `channelAction` lives) | Modify | Generate UUID per click. Track latest revision. Send both fields in payload. |
| `frontend/src/hooks/useGameWebSocket.ts` | Modify | Extract `data.meta.state_revision` from STATE_UPDATE; expose to App via callback or ref. |
| `frontend/src/components/...` (action-emitting components) | Modify | Use `channelAction` helper consistently — no direct fetch with old payload. |
| `backend/tests/test_idempotency_*.py` | Create | 4 backend tests. |
| `frontend/src/__tests__/App.idempotency.test.tsx` | Create | 2 frontend tests. |

---

## Phase A — Schema (1 task)

### Task A1: Migration + ORM column

**Files:**
- Create: `backend/alembic/versions/<ts>_add_action_intent_id.py`
- Modify: `backend/app/db/models.py` (GameLog)

- [ ] **Step 1: Generate migration**

```bash
docker compose exec backend alembic revision -m "add action_intent_id"
```

- [ ] **Step 2: Fill in upgrade/downgrade**

```python
def upgrade():
    op.add_column('game_logs', sa.Column('action_intent_id', sa.String(64), nullable=True))
    op.create_index(
        'ux_game_logs_game_intent',
        'game_logs', ['game_id', 'action_intent_id'],
        unique=True,
        postgresql_where=sa.text('action_intent_id IS NOT NULL'),
    )

def downgrade():
    op.drop_index('ux_game_logs_game_intent', table_name='game_logs')
    op.drop_column('game_logs', 'action_intent_id')
```

- [ ] **Step 3: Add ORM column declaration**

In `backend/app/db/models.py` `GameLog`, append:

```python
    action_intent_id = Column(String(64), nullable=True)
```

- [ ] **Step 4: Apply, verify, downgrade-roundtrip**

```bash
docker compose exec backend alembic upgrade head
docker compose exec db psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl -c "\d game_logs"
docker compose exec backend alembic downgrade -1
docker compose exec backend alembic upgrade head
```
Expected: column visible; downgrade clean; re-upgrade clean.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/*_add_action_intent_id.py backend/app/db/models.py
git commit -m "feat(db): add action_intent_id column + partial unique index"
```

---

## Phase B — Backend payload schema (1 task)

### Task B1: Extend `ActionRequestPayload`

**Files:**
- Modify: `backend/app/schemas/game.py:9-14`

- [ ] **Step 1: Add fields**

Find the existing `ActionRequestPayload`. Add the two optional fields:

```python
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ActionRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    action_index: int
    canonical_id: Optional[str] = None
    action_intent_id: Optional[str] = Field(default=None, max_length=64)        # v2: dedupe key
    expected_state_revision: Optional[int] = Field(default=None, ge=0)          # v2: stale check
```

`max_length=64` matches the DB column. `ge=0` ensures non-negative revision.

- [ ] **Step 2: Verify schema loads + existing tests pass**

```bash
docker compose exec backend python -c "from app.schemas.game import ActionRequestPayload; print(ActionRequestPayload.model_fields.keys())"
docker compose exec backend pytest backend/tests/test_action_request_canonical_guard.py -v
```
Expected: 5 field names listed; existing canonical guard tests still PASS (they don't touch new fields).

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/game.py
git commit -m "feat(schema): add optional action_intent_id and expected_state_revision"
```

---

## Phase C — Backend dedupe + stale check (4 tasks)

### Task C1: Failing test for stale revision rejection

**Files:**
- Create: `backend/tests/test_idempotency_stale.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_idempotency_stale.py
"""Spec §8.2 (v2) test: expected_state_revision mismatch is rejected."""
import pytest
from uuid import uuid4


@pytest.mark.asyncio
async def test_human_action_stale_revision_is_rejected(http_client, started_three_human_game):
    """Submit an action with an out-of-date expected_state_revision → 409 stale_state, no engine change."""
    g = started_three_human_game
    # Apply 1 action so server is at revision=1
    await http_client.post(
        f"/api/puco/game/{g.game_id}/action",
        json={
            "schema_version": "v1",
            "action_index": g.first_legal_action_idx,
            "canonical_id": g.first_legal_canonical_id,
            "action_intent_id": str(uuid4()),
            "expected_state_revision": 0,  # correct: server is at 0 going to 1
        },
    )

    # Now submit with expected_state_revision=0 again — server is at 1 now → stale
    next_legal = g.legal_action_for_current_actor()
    response = await http_client.post(
        f"/api/puco/game/{g.game_id}/action",
        json={
            "schema_version": "v1",
            "action_index": next_legal.action_idx,
            "canonical_id": next_legal.canonical_id,
            "action_intent_id": str(uuid4()),
            "expected_state_revision": 0,   # stale!
        },
    )
    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["error"] == "stale_state"
    assert body["detail"]["expected_state_revision"] == 0
    assert body["detail"]["current_state_revision"] == 1
```

- [ ] **Step 2: Run, expect FAIL**

```bash
docker compose exec backend pytest backend/tests/test_idempotency_stale.py -v
```
Expected: FAIL — server doesn't yet check `expected_state_revision`.

- [ ] **Step 3: Commit failing test**

```bash
git add backend/tests/test_idempotency_stale.py
git commit -m "test(idempotency): stale revision rejection (red)"
```

### Task C2: Failing test for duplicate intent dedupe

**Files:**
- Create: `backend/tests/test_idempotency_dedupe.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_idempotency_dedupe.py
"""Spec §8.2 (v2) test: same action_intent_id is not applied twice."""
import pytest
from uuid import uuid4

from app.db.models import GameSession, GameLog
from app.services.game_service import GameService


@pytest.mark.asyncio
async def test_human_action_duplicate_intent_is_not_applied_twice(
    db, http_client, started_three_human_game
):
    """Same intent_id submitted twice → step/revision increment exactly once.
    Second response is 200 with duplicate=true and same state shape."""
    g = started_three_human_game
    intent = str(uuid4())
    payload = {
        "schema_version": "v1",
        "action_index": g.first_legal_action_idx,
        "canonical_id": g.first_legal_canonical_id,
        "action_intent_id": intent,
        "expected_state_revision": 0,
    }

    r1 = await http_client.post(f"/api/puco/game/{g.game_id}/action", json=payload)
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1.get("duplicate") is not True

    # Server is now at revision=1. Replay same intent (e.g., network retry).
    # Note: expected_state_revision is intentionally still 0 — duplicate detection
    # MUST come before stale-check, OR client must include matching revision; spec
    # decision: stale check first, BUT duplicate intent is recognized and returns
    # the original (then-correct) response without engine change.
    payload_retry = {**payload, "expected_state_revision": 0}
    r2 = await http_client.post(f"/api/puco/game/{g.game_id}/action", json=payload_retry)
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2.get("duplicate") is True

    db.expire_all()
    rev = db.query(GameSession).filter(GameSession.id == g.game_id).first().state_revision
    log_count = db.query(GameLog).filter(
        GameLog.game_id == g.game_id,
        GameLog.action_intent_id == intent,
    ).count()
    assert rev == 1, "engine must not advance on duplicate intent"
    assert log_count == 1, "exactly one row should exist for this intent"
```

- [ ] **Step 2: Run, expect FAIL**

```bash
docker compose exec backend pytest backend/tests/test_idempotency_dedupe.py -v
```
Expected: FAIL.

- [ ] **Step 3: Commit failing test**

```bash
git add backend/tests/test_idempotency_dedupe.py
git commit -m "test(idempotency): duplicate intent dedupe (red)"
```

### Task C3: Implement stale check + dedupe in `process_action`

**Files:**
- Modify: `backend/app/services/game_service.py`

- [ ] **Step 1: Add a small exception type at module top**

```python
class StaleRevisionError(Exception):
    """Raised when client's expected_state_revision is behind the server."""
    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"stale: expected={expected} current={current}")


class DuplicateIntentResult:
    """Marker that an action_intent_id was already applied. Carries cached state."""
    def __init__(self, prior_state: Dict, prior_action_mask):
        self.state = prior_state
        self.action_mask = prior_action_mask
```

- [ ] **Step 2: Extend `process_action` signature**

```python
def process_action(
    self,
    game_id: UUID,
    actor_id: str,
    action: int,
    canonical_id: Optional[str] = None,
    action_intent_id: Optional[str] = None,
    expected_state_revision: Optional[int] = None,
    suppress_broadcast: bool = False,
):
    ...
```

- [ ] **Step 3: At top of body, add stale check then dedupe lookup**

Right after the trace logs and BEFORE any engine.step or DB write:

```python
    # v2 idempotency gate. Order matters: stale check before dedupe.
    current_revision = GameService._engine_revision.get(game_id, 0)
    if expected_state_revision is not None and expected_state_revision != current_revision:
        raise StaleRevisionError(expected=expected_state_revision, current=current_revision)

    if action_intent_id is not None:
        prior = self._lookup_prior_intent(game_id, action_intent_id)
        if prior is not None:
            return {
                "state": prior["state"],
                "action_mask": prior["action_mask"],
                "duplicate": True,
            }
```

`_lookup_prior_intent`:

```python
    def _lookup_prior_intent(self, game_id: UUID, intent_id: str) -> Optional[Dict]:
        """If this intent was already committed, return its cached state shape."""
        log = (
            self.db.query(GameLog)
            .filter(
                GameLog.game_id == game_id,
                GameLog.action_intent_id == intent_id,
            )
            .first()
        )
        if log is None:
            return None
        # Rebuild rich state from current engine (the engine IS at the post-action revision)
        # This is correct because revision == log.revision means engine state matches the
        # moment right after this action was committed.
        engine = GameService.active_engines.get(game_id)
        if engine is None:
            # Engine was evicted. Caller's `ensure_engine_loaded` should have run earlier;
            # but as a safety net, return None to fall through to normal apply path
            # (the unique constraint on action_intent_id will catch the duplicate at INSERT).
            return None
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        rich = build_rich_state(self.db, game_id, engine, room)
        return {
            "state": rich,
            "action_mask": rich.get("action_mask", engine.get_action_mask()),
        }
```

- [ ] **Step 4: Add `action_intent_id` to GameLog row construction**

In the existing GameLog row write (added in v1), include:

```python
    game_log = GameLog(
        # ... existing fields including action_data with action_index/canonical_id ...
        action_intent_id=action_intent_id,
    )
```

- [ ] **Step 5: Catch unique violation as last-line dedupe fallback**

Wrap the `self.db.commit()` in a try/except for `IntegrityError` on the partial unique index. If raised, treat as duplicate: roll back, look up the existing row, return `DuplicateIntentResult` shape:

```python
    from sqlalchemy.exc import IntegrityError
    try:
        self.db.commit()
    except IntegrityError as exc:
        if "ux_game_logs_game_intent" in str(exc.orig):
            self.db.rollback()
            prior = self._lookup_prior_intent(game_id, action_intent_id)
            if prior is not None:
                return {**prior, "duplicate": True}
        raise
```

This handles the rare race where two requests with the same intent slip past the SELECT check and both attempt INSERT. DB-level unique enforces correctness.

- [ ] **Step 6: Run idempotency tests**

```bash
docker compose exec backend pytest backend/tests/test_idempotency_dedupe.py backend/tests/test_idempotency_stale.py -v
```
Expected: BOTH PASS.

- [ ] **Step 7: Run full game-service regression**

```bash
docker compose exec backend pytest backend/tests/ -k "process_action or game_service or canonical" -v
```
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/game_service.py
git commit -m "feat(game-service): stale revision check + intent dedupe in process_action"
```

### Task C4: state_revision must be exposed in rich_state.meta

**Files:**
- Modify: `backend/app/services/state_serializer.py` and/or `state_serializer_support.py`

- [ ] **Step 1: Add `state_revision` to meta block**

Frontend needs to read `data.meta.state_revision` from `STATE_UPDATE`. Find where `meta` dict is built (look for `step_count`, `round`, `phase` adjacency — likely in `state_serializer.py` `build_rich_state` or its helper). Add:

```python
    meta["state_revision"] = room.state_revision if room else 0
```

If `room` isn't passed in scope, thread it through. If the existing build_rich_state already accepts `room` (per v1 changes, it does at game_service.py:114), this is a 2-line change.

- [ ] **Step 2: Add a contract test**

```python
# backend/tests/test_state_revision_in_meta.py
def test_rich_state_includes_state_revision(db, started_three_human_game):
    g = started_three_human_game
    # ... call build_rich_state via service helper ...
    rich = service._build_rich_state(g.game_id, engine, room)
    assert "state_revision" in rich["meta"]
    assert rich["meta"]["state_revision"] == 0  # at start
```

- [ ] **Step 3: Run**

```bash
docker compose exec backend pytest backend/tests/test_state_revision_in_meta.py backend/tests/test_state_serializer_action_index.py -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/state_serializer.py backend/app/services/state_serializer_support.py backend/tests/test_state_revision_in_meta.py
git commit -m "feat(serializer): expose state_revision in meta block"
```

---

## Phase D — Action route 409 handling (1 task)

### Task D1: Translate `StaleRevisionError` to HTTP 409

**Files:**
- Modify: `backend/app/api/channel/game.py` action route

- [ ] **Step 1: Pass new fields + handle exception**

In the action route handler (around line 60-110), after parsing payload and before calling `process_action`:

```python
    intent_id = action_data.payload.action_intent_id
    expected_rev = action_data.payload.expected_state_revision

    try:
        result = service.process_action(
            game_id, actor_id, action_int,
            canonical_id=decoded_canonical,
            action_intent_id=intent_id,
            expected_state_revision=expected_rev,
        )
    except StaleRevisionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "stale_state",
                "expected_state_revision": exc.expected,
                "current_state_revision": exc.current,
            },
        )
```

The duplicate path returns `{"state": ..., "action_mask": ..., "duplicate": True}` — pass it through as 200 unchanged. Existing response builder may need a tiny tweak to include the `duplicate` flag if present.

- [ ] **Step 2: Re-run tests**

```bash
docker compose exec backend pytest backend/tests/test_idempotency_stale.py backend/tests/test_idempotency_dedupe.py -v
```
Expected: BOTH PASS end-to-end via HTTP.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/channel/game.py
git commit -m "feat(action-route): 409 stale_state + duplicate=true response shape"
```

---

## Phase E — Frontend `channelAction` helper (2 tasks)

### Task E1: UUID per click + revision tracking

**Files:**
- Modify: `frontend/src/App.tsx` (or wherever `channelAction` lives — check `frontend/src/App.tsx` first)
- Modify: `frontend/src/hooks/useGameWebSocket.ts`

- [ ] **Step 1: Track latest revision in the hook**

In `useGameWebSocket.ts`, in the `STATE_UPDATE` handler:

```ts
case 'STATE_UPDATE': {
  const data = message.data
  // Track latest server-known revision for v2 idempotency
  latestRevisionRef.current = data?.meta?.state_revision ?? latestRevisionRef.current
  onStateUpdate?.(data)
  break
}
```

Add `latestRevisionRef` as a `useRef<number>(0)` near the top of the hook. Expose via callback or ref:

```ts
return {
  // ... existing returns ...
  getLatestRevision: () => latestRevisionRef.current,
}
```

- [ ] **Step 2: Update `channelAction` to send intent_id + revision**

Find `channelAction(actionIndex, canonicalId?)` in `App.tsx`. Change to:

```ts
async function channelAction(
  actionIndex: number,
  canonicalId?: string,
) {
  const intent = crypto.randomUUID()
  const expectedRev = wsHandle.getLatestRevision()
  const response = await fetch(`/api/puco/game/${gameId}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({
      schema_version: 'v1',
      action_index: actionIndex,
      canonical_id: canonicalId,
      action_intent_id: intent,
      expected_state_revision: expectedRev,
    }),
  })
  if (response.status === 409) {
    const body = await response.json()
    if (body?.detail?.error === 'stale_state') {
      // Wait for next STATE_UPDATE; do NOT auto-retry
      console.warn('[CHANNEL_ACTION] stale_state, waiting for resync', body.detail)
      return { ok: false, reason: 'stale_state' }
    }
  }
  return { ok: response.ok, body: await response.json() }
}
```

`crypto.randomUUID()` is available in all modern browsers and Node 19+ (used in tests).

- [ ] **Step 3: Verify type checks pass**

```bash
docker compose exec frontend npm run typecheck
```
Expected: no errors. If `crypto.randomUUID` is flagged as unknown, add `lib: ["DOM"]` or polyfill in test setup.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/hooks/useGameWebSocket.ts
git commit -m "feat(frontend): channelAction sends action_intent_id + expected_state_revision"
```

### Task E2: Frontend tests

**Files:**
- Create: `frontend/src/__tests__/App.idempotency.test.tsx`

- [ ] **Step 1: Write 2 tests**

```tsx
// frontend/src/__tests__/App.idempotency.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'

describe('channelAction idempotency', () => {
  beforeEach(() => {
    // Mock crypto.randomUUID to be predictable
    let i = 0
    vi.stubGlobal('crypto', {
      randomUUID: () => `intent-${++i}`,
    })
  })

  it('generates a new intent_id per click', async () => {
    // ... render App, simulate two action clicks, capture fetch calls
    // expect first call body.action_intent_id !== second call body.action_intent_id
  })

  it('handles 409 stale_state by waiting (no retry)', async () => {
    // ... mock fetch to return 409 stale_state once, then a STATE_UPDATE via WS
    // assert: no retry POST is made; UI re-renders with new state from WS
  })
})
```

The test patterns match existing `frontend/src/__tests__/App.*.test.tsx` style. Reuse `mockServer` / `vi.mock('global', ...)` patterns from there.

- [ ] **Step 2: Run**

```bash
docker compose exec frontend npm run test -- App.idempotency
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/App.idempotency.test.tsx
git commit -m "test(frontend): channelAction intent UUID + stale_state handling"
```

---

## Phase F — Final integration (2 tasks)

### Task F1: Full backend regression

- [ ] **Step 1: Run all idempotency tests**

```bash
docker compose exec backend pytest backend/tests/test_idempotency_*.py backend/tests/test_state_revision_in_meta.py -v
```
Expected: all PASS.

- [ ] **Step 2: Run all v1 tests (regression check — v2 must not break v1)**

```bash
docker compose exec backend pytest backend/tests/test_recovery_*.py -v
```
Expected: all PASS.

- [ ] **Step 3: Run contract.md §7 regression suite**

```bash
docker compose exec backend pytest backend/tests/ -v --maxfail=5
```
Expected: all PASS. Watch for:
- `test_action_request_canonical_guard.py` — schema change might affect it; should still PASS since both new fields are optional
- `test_db_schema.py` — action_data shape (no change in v2; covered in v1)
- `test_game_action.py` — process_action signature (3 new optional kwargs, backward compat)

### Task F2: Manual smoke test

- [ ] **Step 1: Bring up full stack**

```bash
docker compose up -d --build
```

- [ ] **Step 2: Test duplicate clicks (network retry simulation)**

In browser DevTools Network tab, throttle network. Click an action button. Before response arrives, click again. Both requests carry the same intent_id (verify by inspecting payload in DevTools).

Expected behavior:
- First request: 200, normal state update.
- Second request (duplicate): 200, response body has `duplicate: true`, no double advance.

Check DB:
```bash
docker compose exec db psql -U puco_user -d puco_rl -c "
  SELECT action_intent_id, COUNT(*)
  FROM game_logs
  WHERE game_id = '<game_id>' AND action_intent_id IS NOT NULL
  GROUP BY action_intent_id
  ORDER BY action_intent_id;
"
```
Expected: every intent_id appears exactly once.

- [ ] **Step 3: Test stale_state (open two tabs)**

Open the game in two tabs as the same player (or simulate by manipulating browser state). In tab A, click an action. In tab B (which never received the STATE_UPDATE), click an action without refresh.

Expected: tab B's request returns 409 stale_state. Tab B's UI doesn't auto-retry. After tab B's WS receives the STATE_UPDATE from A's action, tab B's `latestRevision` updates and subsequent clicks work.

- [ ] **Step 4: Final commit if smoke surfaced fixes**

---

## Merge checklist

- [ ] 4 backend idempotency tests pass.
- [ ] 2 frontend idempotency tests pass.
- [ ] All v1 recovery tests still pass (no regression).
- [ ] contract.md §7 listed tests pass.
- [ ] Manual smoke (Task F2) succeeds.
- [ ] DB unique index on `(game_id, action_intent_id)` exists.
- [ ] Action endpoint returns `duplicate: true` flag for retries.
- [ ] Action endpoint returns `409 stale_state` for stale revisions, no auto-retry on client.

## Out of scope (separate PRs / specs)

- **Multi-human abandonment timeout** policy refinement.
- **Footprint optimization** (`/health` split, DB pool, OMP env, Redis removal).
- **CI guard for `ENGINE_COMPAT_VERSION`** — pre-commit hook or GHA.
- **Observability**: latency metrics for recovery, dedupe-hit rate, stale_state rate. Add via existing logger pattern after deploy if needed.

## Risk and rollback

- **Risk: existing client without v2 frontend code submits actions without intent_id.** Both fields are optional; behavior degrades to v1 (no dedupe, no stale check). Acceptable transition state.
- **Risk: `state_revision` mismatch between backend memory and serialized rich_state.meta.** v1's atomic GameLog+state_revision write in same transaction prevents this. Defensive: add an assertion in dev mode that `_engine_revision[game_id] == room.state_revision` after every commit (omit in prod).
- **Risk: `crypto.randomUUID` unavailable in old browsers.** Castone's frontend targets modern browsers (Vite + React 18). If support matrix expands later, fall back to `Math.random()`-based UUID v4 polyfill.
- **Rollback**: revert v2 commits + `alembic downgrade -1`. Migration is non-destructive (only adds column + index). v1 behavior fully restored.
