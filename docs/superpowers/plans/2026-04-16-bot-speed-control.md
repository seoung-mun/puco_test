# Bot Speed Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add speed control (x1/x2/x4) and pause/resume for bot-only spectator games so users can watch at their preferred pace.

**Architecture:** In-memory dict on `GameService` tracks per-game speed and paused state. Three new REST endpoints under `/api/puco/games/{game_id}/playback` let the frontend read/write these values. `BotService.run_bot_turn()` divides its sleep delay by the current speed. The frontend renders speed/pause buttons only when `isSpectator && isBotGame`.

**Tech Stack:** FastAPI + Pydantic (backend), React + TypeScript (frontend), pytest (backend tests), vitest + React Testing Library (frontend tests)

**Spec:** `2026-04-16-bot-speed-control-design.md` (attached to conversation)

---

### Task 1: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/playback.py`

- [ ] **Step 1: Create schema file**

```python
from pydantic import BaseModel, field_validator
from typing import Literal


class PlaybackState(BaseModel):
    speed: int = 1
    paused: bool = False


class SpeedRequest(BaseModel):
    speed: int

    @field_validator("speed")
    @classmethod
    def validate_speed(cls, v: int) -> int:
        if v not in (1, 2, 4):
            raise ValueError("speed must be 1, 2, or 4")
        return v


class PauseRequest(BaseModel):
    paused: bool
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -c "from app.schemas.playback import PlaybackState, SpeedRequest, PauseRequest; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/playback.py
git commit -m "feat(playback): add Pydantic schemas for speed control"
```

---

### Task 2: GameService Speed/Pause State

**Files:**
- Modify: `backend/app/services/game_service.py` (add class-level dicts + getter/setter methods)

- [ ] **Step 1: Write unit test for speed/pause getters and setters**

Create `backend/tests/test_game_speed_state.py`:

```python
"""Unit tests for GameService speed/pause in-memory state."""
import uuid
from app.services.game_service import GameService


class TestGameSpeedState:
    def test_default_speed_is_1(self):
        game_id = uuid.uuid4()
        assert GameService.get_game_speed(game_id) == 1

    def test_set_speed(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 4)
        assert GameService.get_game_speed(game_id) == 4
        GameService._game_speed.pop(game_id, None)  # cleanup

    def test_default_paused_is_false(self):
        game_id = uuid.uuid4()
        assert GameService.get_game_paused(game_id) is False

    def test_set_paused(self):
        game_id = uuid.uuid4()
        GameService.set_game_paused(game_id, True)
        assert GameService.get_game_paused(game_id) is True
        GameService._game_paused.pop(game_id, None)  # cleanup

    def test_cleanup_on_delete(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 2)
        GameService.set_game_paused(game_id, True)
        GameService.clear_playback_state(game_id)
        assert GameService.get_game_speed(game_id) == 1
        assert GameService.get_game_paused(game_id) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -m pytest tests/test_game_speed_state.py -v`
Expected: FAIL with `AttributeError: type object 'GameService' has no attribute 'get_game_speed'`

- [ ] **Step 3: Add speed/pause state to GameService**

In `backend/app/services/game_service.py`, add class variables after `_bot_stall_watchdogs`:

```python
_game_speed: Dict[UUID, int] = {}      # game_id -> 1 | 2 | 4
_game_paused: Dict[UUID, bool] = {}    # game_id -> True | False
```

Add static methods after `get_room_list`:

```python
@staticmethod
def get_game_speed(game_id: UUID) -> int:
    return GameService._game_speed.get(game_id, 1)

@staticmethod
def set_game_speed(game_id: UUID, speed: int) -> None:
    GameService._game_speed[game_id] = speed

@staticmethod
def get_game_paused(game_id: UUID) -> bool:
    return GameService._game_paused.get(game_id, False)

@staticmethod
def set_game_paused(game_id: UUID, paused: bool) -> None:
    GameService._game_paused[game_id] = paused

@staticmethod
def clear_playback_state(game_id: UUID) -> None:
    GameService._game_speed.pop(game_id, None)
    GameService._game_paused.pop(game_id, None)
```

- [ ] **Step 4: Wire cleanup into game finish logic**

In `game_service.py`, inside `process_action()`, after the block `if result.get("terminated", result["done"]) and room:` where `room.status = "FINISHED"` is set (around line 247), add:

```python
GameService.clear_playback_state(game_id)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -m pytest tests/test_game_speed_state.py -v`
Expected: all 5 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/game_service.py backend/tests/test_game_speed_state.py
git commit -m "feat(playback): add speed/pause in-memory state to GameService"
```

---

### Task 3: Playback API Endpoints (RED tests)

**Files:**
- Create: `backend/tests/test_playback_api.py`

- [ ] **Step 1: Write all API tests**

Create `backend/tests/test_playback_api.py`:

```python
"""TDD: Playback speed/pause API endpoints for bot-only spectator games."""
import uuid
import pytest
from app.core.security import create_access_token
from app.db.models import GameSession, User


def _make_user(db, nickname="Tester"):
    uid = uuid.uuid4()
    user = User(id=uid, google_id=f"gid_{uuid.uuid4().hex}", nickname=nickname)
    db.add(user)
    return uid


def _make_bot_game(db, host_id, status="PROGRESS"):
    gid = uuid.uuid4()
    room = GameSession(
        id=gid,
        title="Bot Speed Test",
        status=status,
        num_players=3,
        players=["BOT_ppo", "BOT_random", "BOT_random"],
        host_id=str(host_id),
    )
    db.add(room)
    db.flush()
    return gid


def _make_human_game(db, host_id, status="PROGRESS"):
    gid = uuid.uuid4()
    room = GameSession(
        id=gid,
        title="Human Game",
        status=status,
        num_players=3,
        players=[str(host_id), "BOT_random", "BOT_random"],
        host_id=str(host_id),
    )
    db.add(room)
    db.flush()
    return gid


def _auth(user_id):
    return {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}


class TestPlaybackRequiresAuth:
    def test_get_playback_requires_auth(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.get(f"/api/puco/games/{gid}/playback")
        assert res.status_code == 401

    def test_speed_requires_auth(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(f"/api/puco/games/{gid}/speed", json={"speed": 2})
        assert res.status_code == 401

    def test_pause_requires_auth(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(f"/api/puco/games/{gid}/pause", json={"paused": True})
        assert res.status_code == 401


class TestSpeedChangeBotGameOnly:
    def test_speed_change_human_game_returns_403(self, client, db):
        uid = _make_user(db)
        gid = _make_human_game(db, uid)
        res = client.post(
            f"/api/puco/games/{gid}/speed",
            json={"speed": 2},
            headers=_auth(uid),
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "speed_control_bot_game_only"


class TestSpeedInvalidValue:
    def test_speed_invalid_value_422(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(
            f"/api/puco/games/{gid}/speed",
            json={"speed": 3},
            headers=_auth(uid),
        )
        assert res.status_code == 422


class TestSpeedChangeAccepted:
    def test_speed_change_to_2(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(
            f"/api/puco/games/{gid}/speed",
            json={"speed": 2},
            headers=_auth(uid),
        )
        assert res.status_code == 200
        assert res.json()["speed"] == 2


class TestSpeedCycles:
    def test_speed_cycles_1_2_4(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        headers = _auth(uid)
        for spd in [1, 2, 4, 1]:
            client.post(f"/api/puco/games/{gid}/speed", json={"speed": spd}, headers=headers)
            res = client.get(f"/api/puco/games/{gid}/playback", headers=headers)
            assert res.json()["speed"] == spd


class TestPause:
    def test_pause_accepted(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.post(
            f"/api/puco/games/{gid}/pause",
            json={"paused": True},
            headers=_auth(uid),
        )
        assert res.status_code == 200
        assert res.json()["paused"] is True

    def test_resume_accepted(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        headers = _auth(uid)
        client.post(f"/api/puco/games/{gid}/pause", json={"paused": True}, headers=headers)
        res = client.post(f"/api/puco/games/{gid}/pause", json={"paused": False}, headers=headers)
        assert res.status_code == 200
        assert res.json()["paused"] is False


class TestGetPlayback:
    def test_get_playback_default(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        res = client.get(f"/api/puco/games/{gid}/playback", headers=_auth(uid))
        assert res.status_code == 200
        data = res.json()
        assert data["speed"] == 1
        assert data["paused"] is False

    def test_get_playback_after_change(self, client, db):
        uid = _make_user(db)
        gid = _make_bot_game(db, uid)
        headers = _auth(uid)
        client.post(f"/api/puco/games/{gid}/speed", json={"speed": 4}, headers=headers)
        client.post(f"/api/puco/games/{gid}/pause", json={"paused": True}, headers=headers)
        res = client.get(f"/api/puco/games/{gid}/playback", headers=headers)
        data = res.json()
        assert data["speed"] == 4
        assert data["paused"] is True


class TestNonexistentGame:
    def test_nonexistent_game_404(self, client, db):
        uid = _make_user(db)
        fake_id = uuid.uuid4()
        res = client.get(f"/api/puco/games/{fake_id}/playback", headers=_auth(uid))
        assert res.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -m pytest tests/test_playback_api.py -v`
Expected: FAIL (404 because the router doesn't exist yet)

- [ ] **Step 3: Commit RED tests**

```bash
git add backend/tests/test_playback_api.py
git commit -m "test(playback): add RED API tests for speed/pause endpoints"
```

---

### Task 4: Playback Router (GREEN)

**Files:**
- Create: `backend/app/api/channel/playback.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create playback router**

Create `backend/app/api/channel/playback.py`:

```python
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.dependencies import get_db
from app.api.deps import get_current_user
from app.db.models import User, GameSession
from app.schemas.playback import PlaybackState, SpeedRequest, PauseRequest
from app.services.game_service import GameService

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_bot_game(db: Session, game_id: UUID) -> GameSession:
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room or room.status != "PROGRESS":
        raise HTTPException(status_code=404, detail="Game not found or not in progress")
    players = room.players or []
    if not all(str(p).startswith("BOT_") for p in players):
        raise HTTPException(status_code=403, detail="speed_control_bot_game_only")
    return room


@router.get("/{game_id}/playback", response_model=PlaybackState)
def get_playback(
    game_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_bot_game(db, game_id)
    return PlaybackState(
        speed=GameService.get_game_speed(game_id),
        paused=GameService.get_game_paused(game_id),
    )


@router.post("/{game_id}/speed")
def set_speed(
    game_id: UUID,
    body: SpeedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_bot_game(db, game_id)
    GameService.set_game_speed(game_id, body.speed)
    return {"speed": body.speed}


@router.post("/{game_id}/pause")
def set_pause(
    game_id: UUID,
    body: PauseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_bot_game(db, game_id)
    GameService.set_game_paused(game_id, body.paused)
    if not body.paused:
        _try_resume_bot(game_id, db)
    return {"paused": body.paused}


def _try_resume_bot(game_id: UUID, db: Session):
    """When unpausing, schedule the next bot turn if one is pending."""
    engine = GameService.active_engines.get(game_id)
    if not engine:
        return
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        return
    service = GameService(db)
    service._schedule_next_bot_turn_if_needed(game_id, room, engine)
```

- [ ] **Step 2: Register router in main.py**

In `backend/app/main.py`, add import:

```python
from app.api.channel import room, game, ws, auth, lobby_ws, replay, playback
```

Add router registration after the replays line:

```python
app.include_router(playback.router, prefix="/api/puco/games", tags=["playback"])
```

- [ ] **Step 3: Run API tests to verify they pass**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -m pytest tests/test_playback_api.py -v`
Expected: all PASS

- [ ] **Step 4: Run full backend test suite for regressions**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -m pytest tests/ -v --timeout=30`
Expected: no regressions

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/channel/playback.py backend/app/main.py
git commit -m "feat(playback): add speed/pause REST endpoints (GREEN)"
```

---

### Task 5: Bot Delay Tests (RED)

**Files:**
- Create: `backend/tests/test_bot_speed_delay.py`

- [ ] **Step 1: Write delay calculation tests**

Create `backend/tests/test_bot_speed_delay.py`:

```python
"""TDD: Bot turn delay respects game speed setting."""
import uuid
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.game_service import GameService


def _make_engine_mock(role_selection=False):
    """Create a mock engine with action mask."""
    engine = MagicMock()
    mask = [0] * 200
    if role_selection:
        mask[0] = 1  # role action valid
    else:
        mask[15] = 1  # non-role action valid
    engine.get_action_mask.return_value = mask
    engine.last_obs = {}
    engine.env.game.current_player_idx = 0
    engine.env.game.current_phase = None
    return engine


class TestBotDelayCalculation:
    """Verify that delay = base_delay / speed."""

    @pytest.mark.asyncio
    async def test_delay_at_speed_1(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 1)
        engine = _make_engine_mock(role_selection=False)

        sleep_calls = []
        original_sleep = asyncio.sleep

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(15, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(2.0)
        GameService._game_speed.pop(game_id, None)

    @pytest.mark.asyncio
    async def test_delay_at_speed_2(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 2)
        engine = _make_engine_mock(role_selection=False)

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(15, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(1.0)
        GameService._game_speed.pop(game_id, None)

    @pytest.mark.asyncio
    async def test_delay_at_speed_4(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 4)
        engine = _make_engine_mock(role_selection=False)

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(15, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(0.5)
        GameService._game_speed.pop(game_id, None)

    @pytest.mark.asyncio
    async def test_role_selection_delay_at_speed_4(self):
        game_id = uuid.uuid4()
        GameService.set_game_speed(game_id, 4)
        engine = _make_engine_mock(role_selection=True)

        sleep_calls = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(0, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(0.75)
        GameService._game_speed.pop(game_id, None)


class TestPauseBlocksScheduling:
    @pytest.mark.asyncio
    async def test_pause_blocks_scheduling(self):
        """When paused=True, run_bot_turn should return without executing."""
        game_id = uuid.uuid4()
        GameService.set_game_paused(game_id, True)
        engine = _make_engine_mock()

        select_mock = MagicMock()
        with patch("app.services.bot_service.BotService._select_action_for_current_state", select_mock):
            from app.services.bot_service import BotService
            await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        select_mock.assert_not_called()
        GameService._game_paused.pop(game_id, None)

    @pytest.mark.asyncio
    async def test_resume_triggers_scheduling(self):
        """When paused=False (default), bot turn executes normally."""
        game_id = uuid.uuid4()
        GameService.set_game_paused(game_id, False)
        engine = _make_engine_mock()

        sleep_calls = []
        async def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("app.services.bot_service.asyncio.sleep", side_effect=mock_sleep):
            with patch("app.services.bot_service.BotService._select_action_for_current_state", return_value=(15, MagicMock())):
                with patch("app.services.bot_service.BotService._apply_action_with_retry", new_callable=AsyncMock):
                    from app.services.bot_service import BotService
                    await BotService.run_bot_turn(game_id, engine, "BOT_random", MagicMock())

        assert len(sleep_calls) == 1  # bot turn executed
        GameService._game_paused.pop(game_id, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -m pytest tests/test_bot_speed_delay.py -v`
Expected: FAIL (delay still hardcoded, no pause check)

- [ ] **Step 3: Commit RED tests**

```bash
git add backend/tests/test_bot_speed_delay.py
git commit -m "test(playback): add RED tests for bot delay and pause behavior"
```

---

### Task 6: Bot Delay + Pause Implementation (GREEN)

**Files:**
- Modify: `backend/app/services/bot_service.py`

- [ ] **Step 1: Add pause check and speed-aware delay to run_bot_turn**

In `backend/app/services/bot_service.py`, at the top of `run_bot_turn()` (after the initial logging), add pause check:

```python
from app.services.game_service import GameService

# Check if game is paused - if so, skip this turn (resume will re-trigger)
if GameService.get_game_paused(game_id):
    logger.warning("[BOT_TRACE] turn_skipped_paused game=%s actor=%s", game_id, actor_id)
    return
```

Then change the delay calculation from:

```python
delay = 3.0 if is_role_selection else 2.0
```

to:

```python
speed = GameService.get_game_speed(game_id)
base_delay = 3.0 if is_role_selection else 2.0
delay = base_delay / speed
```

- [ ] **Step 2: Also add pause check to _schedule_next_bot_turn_if_needed in game_service.py**

In `backend/app/services/game_service.py`, at the start of `_schedule_next_bot_turn_if_needed()`, after the initial logging, add:

```python
if GameService.get_game_paused(game_id):
    logger.warning("[BOT_TRACE] schedule_skipped_paused game=%s", game_id)
    return
```

- [ ] **Step 3: Run delay tests to verify they pass**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -m pytest tests/test_bot_speed_delay.py -v`
Expected: all PASS

- [ ] **Step 4: Run full backend test suite for regressions**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -m pytest tests/ -v --timeout=30`
Expected: no regressions

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bot_service.py backend/app/services/game_service.py
git commit -m "feat(playback): speed-aware delay and pause check in bot turns (GREEN)"
```

---

### Task 7: Frontend Speed/Pause UI

**Files:**
- Modify: `frontend/src/components/GameScreen.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write frontend tests**

Add to `frontend/src/components/__tests__/GameScreen.test.tsx`:

```typescript
describe('Playback controls', () => {
  it('shows speed/pause buttons in bot spectator mode', () => {
    const state = makeState();
    state.meta.player_order = ['BOT_ppo', 'BOT_random', 'BOT_random'];
    state.players = {
      BOT_ppo: makePlayer('PPO Bot', 1),
      BOT_random: makePlayer('Random Bot', 2),
      BOT_random_2: makePlayer('Random Bot 2', 3),
    };
    render(
      <GameScreen
        {...commonProps({
          state,
          isSpectator: true,
          isBotGame: true,
          playbackSpeed: 1,
          playbackPaused: false,
          onSpeedChange: vi.fn(),
          onPauseToggle: vi.fn(),
        })}
      />,
    );
    expect(screen.getByTestId('playback-speed-btn')).toBeDefined();
    expect(screen.getByTestId('playback-pause-btn')).toBeDefined();
  });

  it('hides speed/pause buttons in normal game', () => {
    render(<GameScreen {...commonProps({ isSpectator: false, isBotGame: false })} />);
    expect(screen.queryByTestId('playback-speed-btn')).toBeNull();
    expect(screen.queryByTestId('playback-pause-btn')).toBeNull();
  });

  it('speed button cycles x1 -> x2 -> x4 -> x1', async () => {
    const onSpeedChange = vi.fn();
    const state = makeState();
    state.meta.player_order = ['BOT_ppo', 'BOT_random', 'BOT_random'];
    state.players = {
      BOT_ppo: makePlayer('PPO Bot', 1),
      BOT_random: makePlayer('Random Bot', 2),
      BOT_random_2: makePlayer('Random Bot 2', 3),
    };
    render(
      <GameScreen
        {...commonProps({
          state,
          isSpectator: true,
          isBotGame: true,
          playbackSpeed: 1,
          playbackPaused: false,
          onSpeedChange,
          onPauseToggle: vi.fn(),
        })}
      />,
    );
    const btn = screen.getByTestId('playback-speed-btn');
    btn.click();
    expect(onSpeedChange).toHaveBeenCalledWith(2);
  });

  it('pause button toggles icon', () => {
    const state = makeState();
    state.meta.player_order = ['BOT_ppo', 'BOT_random', 'BOT_random'];
    state.players = {
      BOT_ppo: makePlayer('PPO Bot', 1),
      BOT_random: makePlayer('Random Bot', 2),
      BOT_random_2: makePlayer('Random Bot 2', 3),
    };
    const { rerender } = render(
      <GameScreen
        {...commonProps({
          state,
          isSpectator: true,
          isBotGame: true,
          playbackSpeed: 1,
          playbackPaused: false,
          onSpeedChange: vi.fn(),
          onPauseToggle: vi.fn(),
        })}
      />,
    );
    expect(screen.getByTestId('playback-pause-btn').textContent).toContain('⏸');

    rerender(
      <GameScreen
        {...commonProps({
          state,
          isSpectator: true,
          isBotGame: true,
          playbackSpeed: 1,
          playbackPaused: true,
          onSpeedChange: vi.fn(),
          onPauseToggle: vi.fn(),
        })}
      />,
    );
    expect(screen.getByTestId('playback-pause-btn').textContent).toContain('▶');
  });

  it('hides controls when spectating a human game', () => {
    render(
      <GameScreen
        {...commonProps({
          isSpectator: true,
          isBotGame: false,
        })}
      />,
    );
    expect(screen.queryByTestId('playback-speed-btn')).toBeNull();
    expect(screen.queryByTestId('playback-pause-btn')).toBeNull();
  });

  it('pause button calls onPauseToggle', () => {
    const onPauseToggle = vi.fn();
    const state = makeState();
    state.meta.player_order = ['BOT_ppo', 'BOT_random', 'BOT_random'];
    state.players = {
      BOT_ppo: makePlayer('PPO Bot', 1),
      BOT_random: makePlayer('Random Bot', 2),
      BOT_random_2: makePlayer('Random Bot 2', 3),
    };
    render(
      <GameScreen
        {...commonProps({
          state,
          isSpectator: true,
          isBotGame: true,
          playbackSpeed: 1,
          playbackPaused: false,
          onSpeedChange: vi.fn(),
          onPauseToggle,
        })}
      />,
    );
    screen.getByTestId('playback-pause-btn').click();
    expect(onPauseToggle).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/frontend && npx vitest run src/components/__tests__/GameScreen.test.tsx`
Expected: FAIL (new props don't exist yet)

- [ ] **Step 3: Add playback props to GameScreen**

In `frontend/src/components/GameScreen.tsx`, add to `Props` type:

```typescript
isBotGame?: boolean;
playbackSpeed?: number;
playbackPaused?: boolean;
onSpeedChange?: (speed: number) => void;
onPauseToggle?: () => void;
```

Add to the function destructuring params:

```typescript
isBotGame = false,
playbackSpeed = 1,
playbackPaused = false,
onSpeedChange,
onPauseToggle,
```

- [ ] **Step 4: Add playback controls to the sticky bar**

In `GameScreen.tsx`, inside the sticky bar's main section (after the spectator badge block, before `<MetaPanel>`), add:

```tsx
{isSpectator && isBotGame && (
  <span style={{ display: 'flex', alignItems: 'center', gap: 4, marginRight: 8, flexShrink: 0 }}>
    <button
      data-testid="playback-speed-btn"
      onClick={() => {
        const cycle: Record<number, number> = { 1: 2, 2: 4, 4: 1 };
        onSpeedChange?.(cycle[playbackSpeed] ?? 1);
      }}
      style={{ background: '#1a2a3a', border: '1px solid #2a4a6a', borderRadius: 4, color: '#4af', cursor: 'pointer', padding: '2px 8px', fontSize: 12, fontWeight: 'bold', whiteSpace: 'nowrap' }}
    >
      x{playbackSpeed}
    </button>
    <button
      data-testid="playback-pause-btn"
      onClick={() => onPauseToggle?.()}
      style={{ background: '#1a2a3a', border: '1px solid #2a4a6a', borderRadius: 4, color: playbackPaused ? '#4f8' : '#fa0', cursor: 'pointer', padding: '2px 8px', fontSize: 14, whiteSpace: 'nowrap' }}
    >
      {playbackPaused ? '▶' : '⏸'}
    </button>
  </span>
)}
```

- [ ] **Step 5: Update commonProps in test to include new props defaults**

In the test file's `commonProps` function, add defaults:

```typescript
isBotGame: false,
playbackSpeed: 1,
playbackPaused: false,
onSpeedChange: vi.fn(),
onPauseToggle: vi.fn(),
```

- [ ] **Step 6: Run frontend tests to verify they pass**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/frontend && npx vitest run src/components/__tests__/GameScreen.test.tsx`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/GameScreen.tsx frontend/src/components/__tests__/GameScreen.test.tsx
git commit -m "feat(playback): add speed/pause UI controls to GameScreen"
```

---

### Task 8: Wire Playback State in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add playback state and API calls**

In `frontend/src/App.tsx`, add state variables near the existing state declarations:

```typescript
const [playbackSpeed, setPlaybackSpeed] = useState(1);
const [playbackPaused, setPlaybackPaused] = useState(false);
```

Add `isBotGame` computation (near where `isSpectator` is computed):

```typescript
const isBotGame = state
  ? state.meta.player_order.every((id) => id.startsWith('BOT_'))
  : false;
```

Add API helper functions:

```typescript
const handleSpeedChange = async (speed: number) => {
  if (!gameId) return;
  setPlaybackSpeed(speed);
  try {
    await fetch(`${backend}/api/puco/games/${gameId}/speed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
      body: JSON.stringify({ speed }),
    });
  } catch (e) {
    console.error('Speed change failed:', e);
  }
};

const handlePauseToggle = async () => {
  if (!gameId) return;
  const newPaused = !playbackPaused;
  setPlaybackPaused(newPaused);
  try {
    await fetch(`${backend}/api/puco/games/${gameId}/pause`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authToken}` },
      body: JSON.stringify({ paused: newPaused }),
    });
  } catch (e) {
    console.error('Pause toggle failed:', e);
  }
};
```

Add a playback state fetch when game starts (inside the effect or callback that sets gameId):

```typescript
// Fetch playback state on mount (for page refresh)
if (isBotGame && isSpectator && gameId && authToken) {
  fetch(`${backend}/api/puco/games/${gameId}/playback`, {
    headers: { Authorization: `Bearer ${authToken}` },
  })
    .then((r) => r.json())
    .then((data) => {
      setPlaybackSpeed(data.speed ?? 1);
      setPlaybackPaused(data.paused ?? false);
    })
    .catch(() => {});
}
```

- [ ] **Step 2: Pass props to GameScreen**

Find the `<GameScreen` JSX and add the new props:

```typescript
isBotGame={isBotGame}
playbackSpeed={playbackSpeed}
playbackPaused={playbackPaused}
onSpeedChange={handleSpeedChange}
onPauseToggle={handlePauseToggle}
```

- [ ] **Step 3: Reset playback state when leaving game**

In the exit/return-to-rooms handlers, add:

```typescript
setPlaybackSpeed(1);
setPlaybackPaused(false);
```

- [ ] **Step 4: Test manually in browser**

1. Start dev servers: `cd backend && uvicorn app.main:app --reload` and `cd frontend && npm run dev`
2. Create a bot game via the UI
3. Verify speed/pause buttons appear in spectator mode
4. Click speed button: x1 -> x2 -> x4 -> x1
5. Click pause: game pauses, button shows ▶
6. Click resume: game resumes from where it stopped
7. Verify buttons do NOT appear in a human multiplayer game

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(playback): wire speed/pause state and API calls in App.tsx"
```

---

### Task 9: i18n Keys

**Files:**
- Modify: `frontend/src/locales/ko.json`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/it.json`

- [ ] **Step 1: Add playback i18n keys to all three locale files**

Add under a new `"playback"` key in each locale file:

**ko.json:**
```json
"playback": {
  "speed": "배속",
  "pause": "일시정지",
  "resume": "재생"
}
```

**en.json:**
```json
"playback": {
  "speed": "Speed",
  "pause": "Pause",
  "resume": "Resume"
}
```

**it.json:**
```json
"playback": {
  "speed": "Velocita",
  "pause": "Pausa",
  "resume": "Riprendi"
}
```

- [ ] **Step 2: Update GameScreen button titles to use i18n**

In the speed button, add `title={t('playback.speed')}`.
In the pause button, add `title={playbackPaused ? t('playback.resume') : t('playback.pause')}`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/locales/ko.json frontend/src/locales/en.json frontend/src/locales/it.json frontend/src/components/GameScreen.tsx
git commit -m "feat(playback): add i18n keys for speed/pause controls"
```

---

### Task 10: Contract Docs Update

**Files:**
- Modify: `docs/contract.md` (if exists, otherwise skip)

- [ ] **Step 1: Check if contract.md exists and add playback section**

Add a "Playback Control" section documenting the three endpoints:

```markdown
### Playback Control (Bot-Only Games)

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | /api/puco/games/{game_id}/playback | - | `{speed, paused}` |
| POST | /api/puco/games/{game_id}/speed | `{speed: 1|2|4}` | `{speed}` |
| POST | /api/puco/games/{game_id}/pause | `{paused: bool}` | `{paused}` |

All endpoints require `Authorization: Bearer <token>`. Returns 403 if game has human players.
```

- [ ] **Step 2: Commit**

```bash
git add docs/contract.md
git commit -m "docs: add playback control endpoints to contract"
```

---

### Task 11: Final Integration Test

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/backend && python -m pytest tests/ -v --timeout=30`
Expected: all PASS

- [ ] **Step 2: Run full frontend test suite**

Run: `cd /Users/seoungmun/Documents/agent_dev/castest/castone/frontend && npx vitest run`
Expected: all PASS

- [ ] **Step 3: Manual smoke test**

1. Create bot game, verify controls appear
2. Test x1 -> x2 -> x4 cycle
3. Test pause/resume
4. Verify normal game has no controls
5. Refresh page, verify state persists from backend
