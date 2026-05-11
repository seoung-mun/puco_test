# Prod-to-Dev Multiplayer Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `prod`를 최신 기준선으로 삼아 `dev` 브랜치를 재정렬한 뒤, 최소 수정으로 멀티플레이 실서비스 버그(UI 노출, 잘못된 역할 알림/행동 표면, 역할 handoff, 건축가 구매, 좌석 순서 고정)를 안정화한다.

**Architecture:** 브랜치는 `prod -> dev` 단방향 기준선으로 재설정하고, 코드 수정은 channel multiplayer 경로만 다룬다. 프론트엔드는 `meta.active_player`를 단일 턴 기준으로 통일하고, 행동 가능한 UI는 현재 행동 플레이어에게만 노출한다. 좌석 순서 문제는 `room.players`를 게임 시작 시점에 한 번만 셔플해서 엔진 인덱스, actor 검증, replay, 직렬화가 같은 기준선을 바라보게 만든다.

**Tech Stack:** Git, Docker Compose, Python (FastAPI, SQLAlchemy, pytest), TypeScript (React, Vite, Vitest)

**Spec/Input:** [2026-05-11-error-log-work-prep.md](./2026-05-11-error-log-work-prep.md)

**Branch rule:** `prod`는 건드리지 않는다. 구현은 새 worktree에서 `dev`를 `prod` 기준으로 다시 세운 뒤 진행한다. `main`은 이번 계획에서 건드리지 않는다. 사용자가 overwrite를 허용했지만, 범위를 줄이기 위해 안정화 완료 후 승격 시점에 맞춘다.

**Test execution rule:** 테스트는 전부 컨테이너 안에서만 실행한다. `docker compose exec backend pytest ...` / `docker compose exec frontend npx vitest ...`만 사용한다.

---

## File Structure

### Created
- `backend/tests/test_game_start_player_order.py` — 게임 시작 시 좌석 셔플 재현성/순열 보존/host 비고정 회귀
- `frontend/src/__tests__/App.turn-source-contract.test.tsx` — `isMyTurn`가 `decision.player`가 아니라 `meta.active_player`를 따라야 한다는 회귀

### Modified
- `backend/app/services/game_service.py` — `start_game()`에서 시작 시점 좌석 셔플 적용
- `backend/app/services/game_service_support.py` — 시작 셔플 helper 추가
- `backend/tests/test_governor_assignment.py` — governor randomness와 좌석 셔플이 함께 유지되는 회귀 추가
- `frontend/src/App.tsx` — `isMyTurn`, `isBotTurn`, `notMyTurn()`의 턴 기준선 통일
- `frontend/src/components/GameScreen.tsx` — trader/captain/craftsman/mayor 관련 live action surface를 현재 행동 플레이어에게만 노출
- `frontend/src/components/__tests__/GameScreen.test.tsx` — 비행동 플레이어에게 action card / mayor legal UI / craftsman overlay가 보이지 않는 회귀 추가
- `frontend/src/__tests__/App.action-index-contract.test.tsx` — 현재 action payload 회귀 유지, 턴 기준 변경 이후에도 깨지지 않도록 고정
- `docs/superpowers/plans/2026-05-11-error-log-work-prep.md` — 구현 후 결과 반영 메모 2~3줄 추가 (선택)

---

## Task 1: `dev`를 `prod` 기준으로 재정렬하는 작업 베이스 만들기

**Files:**
- Modify: local git refs only (tracked file changes 없음)

- [ ] **Step 1: 최신 원격 기준선 가져오기**

```bash
git fetch origin
git rev-parse origin/prod
git rev-parse origin/dev
git rev-parse origin/main
```

Expected: `origin/prod`가 `origin/dev`, `origin/main`보다 최신 커밋임을 확인한다.

- [ ] **Step 2: dirty `prod`를 건드리지 않는 새 worktree 만들기**

```bash
git worktree add ../castone-dev prod
```

Expected: 현재 워크트리와 별개로 `../castone-dev`가 생성되고, checkout 기준은 `prod` 커밋이다.

- [ ] **Step 3: 새 worktree에서 `dev`를 `prod` 기준으로 다시 세우기**

```bash
git -C ../castone-dev switch -C dev prod
git -C ../castone-dev status --short --branch
git -C ../castone-dev rev-parse HEAD
git -C ../castone-dev rev-parse prod
```

Expected: `../castone-dev`의 `dev` HEAD와 `prod` HEAD가 동일하다.

- [ ] **Step 4: 원격 `dev`도 같은 기준으로 맞추기**

```bash
git -C ../castone-dev push --force-with-lease origin dev
git -C ../castone-dev rev-parse dev
git -C ../castone-dev rev-parse origin/dev
```

Expected: `dev`와 `origin/dev`가 동일 커밋을 가리킨다.

- [ ] **Step 5: 이번 계획 범위에서 `main`은 보류한다고 명시**

```text
이번 플랜에서는 main을 건드리지 않는다.
이유: 사용자가 overwrite를 허용했지만, 범위를 줄이기 위해 안정화 완료 후 승격 시점에만 main을 맞춘다.
```

No commit for this task. 이 태스크는 브랜치 기준선 정리 작업이다.

---

## Task 2: 비행동 플레이어에게 보이면 안 되는 UI를 먼저 RED로 잠근다

**Files:**
- Modify: `frontend/src/components/__tests__/GameScreen.test.tsx`

- [ ] **Step 1: trader action card가 비행동 플레이어에게는 안 보이는 failing test 추가**

```tsx
it('hides trader action card for non-active multiplayer viewers', () => {
  const state = makeState();
  state.meta.phase = 'trader_action';
  state.meta.active_role = 'trader';
  state.meta.active_player = 'player_0';
  state.players.player_0.goods.corn = 1;
  state.players.player_0.goods.d_total = 1;

  render(
    <GameScreen
      {...commonProps({
        state,
        isMyTurn: false,
        isMultiplayer: true,
      })}
    />,
  );

  expect(screen.queryByText('trader.title')).toBeNull();
});
```

- [ ] **Step 2: craftsman overlay와 mayor legal UI가 비행동 플레이어에게 안 보이는 failing test 추가**

```tsx
it('hides craftsman privilege overlay for non-active multiplayer viewers', () => {
  const state = makeState();
  state.meta.phase = 'craftsman_action';
  state.meta.active_role = 'craftsman';
  state.common_board.roles.craftsman.taken_by = 'player_0';

  render(
    <GameScreen
      {...commonProps({
        state,
        isMyTurn: false,
        isMultiplayer: true,
      })}
    />,
  );

  expect(screen.queryByText('craftsmanDialog.message')).toBeNull();
});

it('does not pass mayor legal slots to non-active multiplayer viewers', () => {
  const state = makeState();
  state.meta.phase = 'mayor_action';
  state.meta.active_role = 'mayor';
  state.meta.active_player = 'player_0';
  state.meta.mayor_legal_island_slots = [0, 1];
  state.meta.mayor_legal_city_slots = [0];

  render(
    <GameScreen
      {...commonProps({
        state,
        isMyTurn: false,
        isMultiplayer: true,
      })}
    />,
  );

  expect(screen.getByTestId('player_0').textContent).toContain('Alice:normal');
});
```

- [ ] **Step 3: RED 확인**

```bash
docker compose exec frontend npx vitest run src/components/__tests__/GameScreen.test.tsx
```

Expected: 새 테스트들이 FAIL 한다. 현재 구현은 `isMyTurn` 없이 trader/captain/craftsman/mayor surface를 보여주기 때문이다.

- [ ] **Step 4: 최소 구현으로 GREEN 만들기**

`frontend/src/components/GameScreen.tsx`에서 live action surface 조건을 `isMyTurn`까지 포함하도록 바꾼다.

```tsx
const canViewLiveActionSurface = showLiveOnlyUi && !isBlocked && isMyTurn;

const showMayorPanel = isMayorPhase && activeMayorPlayer != null && !isBotTurn && isMyTurn;

{canViewLiveActionSurface && isCraftsmanPrivilege && (() => { ... })}

{canViewLiveActionSurface && (isTraderPhase || isCaptainPhase || isCaptainDiscard) && (() => { ... })}

mayorLegalIslandSlots={
  showMayorPanel && id === state.meta.active_player
    ? state.meta.mayor_legal_island_slots
    : undefined
}
```

- [ ] **Step 5: GREEN 확인**

```bash
docker compose exec frontend npx vitest run src/components/__tests__/GameScreen.test.tsx
```

Expected: 새 테스트 포함 PASS.

- [ ] **Step 6: Commit**

```bash
git -C ../castone-dev add frontend/src/components/GameScreen.tsx frontend/src/components/__tests__/GameScreen.test.tsx
git -C ../castone-dev commit -m "fix(multiplayer-ui): hide action surfaces from non-active viewers"
```

---

## Task 3: `meta.active_player`를 단일 턴 기준으로 고정해서 역할 handoff / 건축가 구매 문제를 막는다

**Files:**
- Create: `frontend/src/__tests__/App.turn-source-contract.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/__tests__/App.action-index-contract.test.tsx`

- [ ] **Step 1: `isMyTurn`가 `decision.player` 대신 `meta.active_player`를 따라야 한다는 failing test 작성**

```tsx
import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from '../App';

vi.mock('../components/GameScreen', () => ({
  default: (props: { isMyTurn: boolean }) => (
    <div data-testid="turn-probe">{props.isMyTurn ? 'my-turn' : 'not-my-turn'}</div>
  ),
}));

it('derives multiplayer turn ownership from meta.active_player', async () => {
  const state = makeSettlerState();
  state.meta.active_player = 'player_1';
  state.decision.player = 'player_0';

  render(<App />);

  await waitFor(() => {
    expect(document.querySelector('[data-testid="turn-probe"]')?.textContent).toBe('not-my-turn');
  });
});
```

> 이 테스트 파일은 `App.action-index-contract.test.tsx`의 mock 패턴을 그대로 재사용한다. auth bootstrap / room join / start 응답을 stub 하는 방식도 동일하게 맞춘다.

- [ ] **Step 2: RED 확인**

```bash
docker compose exec frontend npx vitest run src/__tests__/App.turn-source-contract.test.tsx
```

Expected: FAIL. 현재 `App.tsx`의 `isMyTurn`는 `state?.decision?.player === myPlayerId`를 사용한다.

- [ ] **Step 3: `App.tsx`에서 단일 턴 기준선을 도입**

```tsx
const currentTurnPlayerId = state?.meta.active_player ?? state?.decision?.player ?? null;

const isBotTurn = !!(
  state?.bot_players &&
  currentTurnPlayerId &&
  state.bot_players[currentTurnPlayerId] !== undefined
);

const isMyTurn = isSpectator
  ? false
  : !isMultiplayer
    ? !isBotTurn
    : (myPlayerId !== null && currentTurnPlayerId === myPlayerId);

function notMyTurn(): boolean {
  return isMultiplayer && myPlayerId !== null && myPlayerId !== currentTurnPlayerId;
}
```

그리고 `currentTurnPlayerId`를 사용하는 주석을 1줄 추가한다.

```tsx
// Channel multiplayer에서는 meta.active_player를 단일 턴 기준으로 사용한다.
```

- [ ] **Step 4: 기존 action-index 회귀가 안 깨지는지 함께 확인**

```bash
docker compose exec frontend npx vitest run \
  src/__tests__/App.turn-source-contract.test.tsx \
  src/__tests__/App.action-index-contract.test.tsx
```

Expected: 둘 다 PASS.

- [ ] **Step 5: builder / role handoff 기준 시나리오를 한 개 더 고정**

`frontend/src/__tests__/App.turn-source-contract.test.tsx`에 아래 테스트를 추가한다.

```tsx
it('keeps non-active human blocked during builder turn when meta.active_player is another seat', async () => {
  const state = makeSettlerState();
  state.meta.phase = 'builder_action';
  state.meta.active_role = 'builder';
  state.meta.active_player = 'player_0';
  state.decision.player = 'player_1';

  render(<App />);

  await waitFor(() => {
    expect(document.querySelector('[data-testid="turn-probe"]')?.textContent).toBe('not-my-turn');
  });
});
```

- [ ] **Step 6: Commit**

```bash
git -C ../castone-dev add frontend/src/App.tsx frontend/src/__tests__/App.turn-source-contract.test.tsx frontend/src/__tests__/App.action-index-contract.test.tsx
git -C ../castone-dev commit -m "fix(turn-source): use meta.active_player as single multiplayer turn owner"
```

---

## Task 4: 게임 시작 시 좌석 자체를 셔플해서 `host -> guest -> bot` 고정 순서를 끊는다

**Files:**
- Modify: `backend/app/services/game_service_support.py`
- Modify: `backend/app/services/game_service.py`
- Create: `backend/tests/test_game_start_player_order.py`
- Modify: `backend/tests/test_governor_assignment.py`

- [ ] **Step 1: 셔플 helper에 대한 failing test 작성**

`backend/tests/test_game_start_player_order.py` 생성:

```python
from app.services.game_service_support import shuffle_players_for_game_start


def test_shuffle_players_for_game_start_is_reproducible():
    players = ["HOST", "GUEST", "BOT_ppo"]
    assert shuffle_players_for_game_start(players, 101) == shuffle_players_for_game_start(players, 101)


def test_shuffle_players_for_game_start_preserves_members():
    players = ["HOST", "GUEST", "BOT_ppo"]
    shuffled = shuffle_players_for_game_start(players, 202)
    assert sorted(shuffled) == sorted(players)


def test_shuffle_players_for_game_start_can_move_host_out_of_seat_zero():
    players = ["HOST", "GUEST", "BOT_ppo"]
    orders = {
        tuple(shuffle_players_for_game_start(players, seed))
        for seed in range(30)
    }
    assert any(order[0] != "HOST" for order in orders)
```

- [ ] **Step 2: RED 확인**

```bash
docker compose exec backend pytest backend/tests/test_game_start_player_order.py -q
```

Expected: FAIL. helper가 아직 없다.

- [ ] **Step 3: helper 구현**

`backend/app/services/game_service_support.py`에 추가:

```python
import random


def shuffle_players_for_game_start(players: List[str], game_seed: int) -> List[str]:
    shuffled = list(players)
    rng = random.Random(game_seed)
    rng.shuffle(shuffled)
    return shuffled
```

`__all__`가 없다면 export 추가는 생략한다. import path만 맞추면 된다.

- [ ] **Step 4: `start_game()`에서 셔플을 실제로 적용**

`backend/app/services/game_service.py`의 `start_game()` 초반을 아래처럼 바꾼다.

```python
game_seed = secrets.randbits(63)
seat_players = shuffle_players_for_game_start(list(room.players or []), game_seed)
room.players = seat_players

engine = create_game_engine(
    num_players=len(seat_players),
    game_seed=game_seed,
    player_control_modes=build_player_control_modes(room),
)
```

그리고 아래 줄도 `seat_players` 기준으로 맞춘다.

```python
actual_players = len(room.players or [])
```

> `room.players`를 engine 생성 전에 바꾸는 이유는 이후 actor validation, replay snapshot, model_versions snapshot이 모두 같은 좌석 기준선을 쓰게 만들기 위해서다.

- [ ] **Step 5: governor 회귀 테스트를 보강**

`backend/tests/test_governor_assignment.py`에 추가:

```python
from app.services.game_service_support import shuffle_players_for_game_start


def test_start_shuffle_is_distinct_from_governor_rotation():
    players = ["HOST", "GUEST", "BOT_ppo"]
    shuffled = shuffle_players_for_game_start(players, 20260405)
    assert sorted(shuffled) == sorted(players)
    assert len(shuffled) == 3
```

그리고 기존 `test_random_governor_varies_across_seeds()`는 유지한다.

- [ ] **Step 6: GREEN 확인**

```bash
docker compose exec backend pytest \
  backend/tests/test_game_start_player_order.py \
  backend/tests/test_governor_assignment.py \
  backend/tests/test_game_service_turn_validation.py \
  -q
```

Expected: PASS. 특히 `process_action`의 `expected_actor = room.players[current_idx]` 검증이 셔플 이후에도 계속 맞아야 한다.

- [ ] **Step 7: Commit**

```bash
git -C ../castone-dev add backend/app/services/game_service.py backend/app/services/game_service_support.py backend/tests/test_game_start_player_order.py backend/tests/test_governor_assignment.py
git -C ../castone-dev commit -m "fix(start-order): shuffle room seats once at game start"
```

---

## Task 5: 회귀 검증을 docker 경로에서 마무리하고 `dev`만 유지한다

**Files:**
- Modify: none required

- [ ] **Step 1: backend 회귀 묶음 실행**

```bash
docker compose exec backend pytest \
  backend/tests/test_game_service_turn_validation.py \
  backend/tests/test_game_start_player_order.py \
  backend/tests/test_governor_assignment.py \
  backend/tests/test_active_game_session.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: frontend 회귀 묶음 실행**

```bash
docker compose exec frontend npx vitest run \
  src/components/__tests__/GameScreen.test.tsx \
  src/__tests__/App.turn-source-contract.test.tsx \
  src/__tests__/App.action-index-contract.test.tsx
```

Expected: PASS.

- [ ] **Step 3: 수동 시나리오 확인**

```text
1. host + human + bot room 생성
2. host가 게임 시작
3. 비행동 플레이어 화면에서 craftsman/trader/captain/mayor surface가 안 보이는지 확인
4. role_selection에서 사람 1 -> 사람 2 handoff가 refresh 없이 되는지 확인
5. builder_action에서 다른 인간 플레이어가 자기 차례에 건물을 구매할 수 있는지 확인
6. 여러 새 게임을 시작해 host가 항상 seat 0에 고정되지 않는지 확인
```

- [ ] **Step 4: `dev`만 유지하고 `main`은 건드리지 않았음을 작업 메모에 남기기**

```text
이번 작업은 prod 최신본을 기준으로 dev만 재정렬했다.
main overwrite 권한은 확보했지만, 최소 작업 원칙에 따라 이번 플랜에서는 사용하지 않았다.
```

- [ ] **Step 5: Final commit (문서 메모가 생겼다면)**

```bash
git -C ../castone-dev add docs/superpowers/plans/2026-05-11-error-log-work-prep.md
git -C ../castone-dev commit -m "docs(multiplayer): record stabilized prod-to-dev execution notes"
```

> 문서 메모를 남기지 않으면 이 Step은 skip 가능하다.

---

## Self-Review

### Spec coverage

- `git` 1순위 반영: Task 1에서 `prod -> dev` 재정렬만 수행하고 `main`은 보류
- 최소 작업 원칙 반영: UI 노출/알림/turn-source 먼저, 그 다음 seat shuffle
- 멀티플레이 핵심 증상 반영:
  - 다른 플레이어 UI 노출: Task 2
  - 잘못된 알림/행동 표면: Task 2
  - 역할 handoff / 건축가 구매: Task 3
  - 순서 고정: Task 4
  - 새로고침 잔여 문제: Task 5 수동 재검증

### Placeholder scan

- `TODO`, `TBD`, “적절히 수정” 같은 표현 없이 각 작업에 실제 테스트/명령/코드 뼈대를 넣었다.
- `main` 처리도 모호하게 남기지 않고 이번 계획 범위 밖이라고 명시했다.

### Type consistency

- 턴 기준선은 계획 전반에서 `meta.active_player`로 일관되게 사용했다.
- 좌석 셔플 기준선은 `room.players`로 일관되게 사용했다.

---

Plan complete and saved to `docs/superpowers/plans/2026-05-11-prod-to-dev-multiplayer-stabilization.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

