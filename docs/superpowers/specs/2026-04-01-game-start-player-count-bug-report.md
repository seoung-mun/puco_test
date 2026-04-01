# 버그 해결 보고서: 게임 시작 최소 플레이어 수 오류

**날짜:** 2026-04-01
**심각도:** 높음 (게임 시작 불가 버그)
**분류:** 프론트엔드 상태 초기화 + 백엔드 로직 검증

---

## 1. 버그 요약

**증상:**
대기방(Lobby)에서 게임 시작 버튼이 방장을 제외한 3명의 플레이어를 요구한다. 즉, 방장 포함 총 4명이 있어야만 시작이 가능하다.

**기대 동작:**
방장을 포함하여 총 3명(방장 1명 + 비방장 2명)이 모이면 게임이 시작되어야 한다. Puerto Rico 게임의 기본 플레이어 수는 3인이며, 방장도 플레이어 중 한 명이다.

---

## 2. 코드 분석

### 2-1. 버그 위치 A — 프론트엔드 초기 상태 (핵심)

**파일:** `castone/frontend/src/App.tsx:503`

```tsx
// 방 생성 시 방장만 lobbyPlayers에 등록 (connected 필드 없음)
setLobbyPlayers([{ name: myEntry, player_id: authUser?.id ?? '' }]);
```

방 생성 직후 방장의 `LobbyPlayer` 객체에는 `connected` 필드가 없다. TypeScript 인터페이스에서 `connected?: boolean` (optional)이므로 `undefined`로 초기화된다.

**파일:** `castone/frontend/src/components/LobbyScreen.tsx:22-24`

```tsx
const activePlayers = players.filter(p => !p.is_spectator);
const connectedActive = activePlayers.filter(p => p.connected || p.is_bot);
const canStart = isHost && connectedActive.length >= 3;
```

`p.connected`가 `undefined`이고 `p.is_bot`도 `undefined`이면:
```
undefined || undefined = undefined (falsy)
```
→ 방장이 `connectedActive`에서 제외된다.

**결과:** 방장이 카운트에서 빠지므로, 비방장 플레이어 3명이 있어야 `connectedActive.length >= 3` 조건을 충족 → 총 4명 필요.

---

### 2-2. 버그 위치 B — 백엔드 `_build_lobby_payload` 의 `connected` 필드

**파일:** `castone/backend/app/services/lobby_manager.py:61-85`

```python
def _build_lobby_payload(room: GameSession, db: Session) -> dict:
    players_out = []
    for raw_pid in (room.players or []):
        pid = str(raw_pid)
        if pid.startswith("BOT_"):
            players_out.append({
                ...
                "connected": True,   # 항상 True
            })
        else:
            players_out.append({
                ...
                "is_host": (pid == str(room.host_id)),
                "connected": True,   # 항상 True (실제 WS 연결 여부 미반영)
            })
    return {"players": players_out, ...}
```

서버는 `room.players`에 있는 모든 플레이어에게 `connected: True`를 하드코딩하여 전송한다.
WebSocket이 연결된 후 `LOBBY_STATE`를 수신하면 방장의 `connected`가 `True`로 업데이트되지만, **WS 연결이 지연되거나 방장이 WS 상태 업데이트를 받기 전**에는 초기 `undefined` 값이 유지된다.

---

### 2-3. 타이밍 문제

방장이 방을 생성하면 다음 순서로 진행된다:

```
1. POST /api/puco/rooms  →  room 생성, players = [host_id]
2. setLobbyPlayers([{ name, player_id }])  ← connected = undefined !!!
3. connectLobbyWs(gid) 호출
4. WebSocket onopen → 토큰 전송
5. 서버: 인증 성공 → LOBBY_STATE 브로드캐스트 (connected: True)
6. setLobbyPlayers(msg.players)  ← 이제서야 connected = True
```

step 2와 step 6 사이의 시간 동안 `connected = undefined`가 유지된다.
만약 WS 연결이 느리거나, 다른 플레이어가 합류해서 `LOBBY_UPDATE`를 받기 전에 상태를 보게 되면 방장이 카운트에서 빠질 수 있다.

또한 App.tsx:539에서 방 참가 시도:
```tsx
setLobbyPlayers([{ name: myEntry, player_id: authUser?.id ?? '' }]);
```
방에 참가하는 플레이어도 동일하게 `connected` 없이 초기화된다.

---

### 2-4. 백엔드 `game_service.py` 확인 (정상)

**파일:** `castone/backend/app/services/game_service.py:69-71`

```python
actual_players = len(room.players or [])
if actual_players < 3:
    raise ValueError(f"Need at least 3 players to start, currently {actual_players}")
```

백엔드의 검증 로직은 방장을 포함한 `room.players`의 총 수를 확인하므로 **정상**이다.
방장 + 2명 = 3명 → 통과. 백엔드 수정 불필요.

---

## 3. 수정 방안 (TDD 접근)

### 3-1. RED — 실패하는 테스트 먼저 작성

**파일 위치:** `castone/frontend/src` (Jest + React Testing Library 기준)

```typescript
// LobbyScreen.test.tsx

test('방장 포함 총 3명이면 게임 시작 버튼이 활성화된다', () => {
  const players: LobbyPlayer[] = [
    { name: 'Alice', player_id: 'alice-id', is_host: true },   // connected 없음 (초기 상태)
    { name: 'Bob',   player_id: 'bob-id',   is_bot: false, connected: true },
    { name: 'Charlie', player_id: 'charlie-id', is_bot: false, connected: true },
  ];

  render(
    <LobbyScreen
      players={players}
      host="Alice"
      myName="Alice"
      onStart={jest.fn()}
      onLogout={jest.fn()}
    />
  );

  const startButton = screen.getByRole('button', { name: /시작|start/i });
  expect(startButton).not.toBeDisabled();
});

test('방장 포함 총 2명이면 게임 시작 버튼이 비활성화된다', () => {
  const players: LobbyPlayer[] = [
    { name: 'Alice', player_id: 'alice-id', is_host: true },
    { name: 'Bob',   player_id: 'bob-id',   connected: true },
  ];

  render(
    <LobbyScreen
      players={players}
      host="Alice"
      myName="Alice"
      onStart={jest.fn()}
      onLogout={jest.fn()}
    />
  );

  const startButton = screen.getByRole('button', { name: /더 필요|need/i });
  expect(startButton).toBeDisabled();
});
```

---

### 3-2. GREEN — 최소 수정으로 테스트 통과

**수정 1: LobbyScreen.tsx — `canStart` 조건 수정**

**파일:** `castone/frontend/src/components/LobbyScreen.tsx:22-24`

```tsx
// Before (버그)
const activePlayers = players.filter(p => !p.is_spectator);
const connectedActive = activePlayers.filter(p => p.connected || p.is_bot);
const canStart = isHost && connectedActive.length >= 3;

// After (수정)
const activePlayers = players.filter(p => !p.is_spectator);
// connected가 undefined인 플레이어도 활성 플레이어로 인정 (spectator, is_bot=false 제외 제거)
const connectedActive = activePlayers.filter(p => p.connected !== false || p.is_bot);
const canStart = isHost && connectedActive.length >= 3;
```

`p.connected !== false` 로 변경하면:
- `connected = true` → 카운트됨 ✓
- `connected = undefined` → 카운트됨 ✓ (방장 초기 상태 포함)
- `connected = false` → 제외됨 ✓ (명시적으로 연결 끊긴 플레이어)

**수정 2: App.tsx — 방장 초기 상태에 `connected: true` 명시**

**파일:** `castone/frontend/src/App.tsx:503, 539`

```tsx
// Before
setLobbyPlayers([{ name: myEntry, player_id: authUser?.id ?? '' }]);

// After
setLobbyPlayers([{ name: myEntry, player_id: authUser?.id ?? '', connected: true }]);
```

방을 생성하거나 참가할 때 자신(현재 유저)은 항상 연결 상태이므로 `connected: true`를 명시한다. 이후 WS `LOBBY_STATE`가 오면 전체 리스트가 덮어써지므로 side effect 없음.

---

### 3-3. 백엔드 테스트 추가 (회귀 방지)

**파일:** `castone/backend/tests/test_game_action.py` 또는 별도 파일

```python
def test_host_plus_two_players_can_start(client, db, alice, bob, charlie):
    """방장 + 2명 = 총 3명으로 게임 시작 가능해야 한다."""
    room = _create_room_for(db, alice)
    room.players = [str(alice.id), str(bob.id), str(charlie.id)]
    db.flush()

    app.dependency_overrides[get_current_user] = lambda: alice
    res = client.post(f"/api/puco/game/{room.id}/start")
    assert res.status_code == 200, f"방장 포함 3명으로 시작 실패: {res.json()}"


def test_host_alone_cannot_start(client, db, alice):
    """방장 혼자서는 게임을 시작할 수 없다."""
    room = _create_room_for(db, alice)
    room.players = [str(alice.id)]
    db.flush()

    app.dependency_overrides[get_current_user] = lambda: alice
    res = client.post(f"/api/puco/game/{room.id}/start")
    assert res.status_code == 400
    assert "3" in res.json()["detail"]


def test_host_plus_one_cannot_start(client, db, alice, bob):
    """방장 + 1명 = 총 2명으로는 게임을 시작할 수 없다."""
    room = _create_room_for(db, alice)
    room.players = [str(alice.id), str(bob.id)]
    db.flush()

    app.dependency_overrides[get_current_user] = lambda: alice
    res = client.post(f"/api/puco/game/{room.id}/start")
    assert res.status_code == 400
```

---

## 4. 수정 범위 요약

| 파일 | 변경 내용 | 우선순위 |
|------|-----------|---------|
| `frontend/src/components/LobbyScreen.tsx:24` | `p.connected || p.is_bot` → `p.connected !== false \|\| p.is_bot` | **필수** |
| `frontend/src/App.tsx:503` | 방 생성 시 `connected: true` 추가 | 권장 |
| `frontend/src/App.tsx:539` | 방 참가 시 `connected: true` 추가 | 권장 |
| `backend/tests/` | 3인 시작 테스트 추가 | 회귀 방지 |

---

## 5. TDD 실행 순서

```
1. RED:   LobbyScreen.test.tsx에 위 테스트 2개 추가 → 실패 확인
2. GREEN: LobbyScreen.tsx:24 한 줄 수정 → 테스트 통과 확인
3. REFACTOR: App.tsx 503, 539라인에 connected: true 추가 (방어적 초기화)
4. RED:   백엔드 pytest 3개 추가 → 통과 여부 확인 (이미 통과해야 정상)
5. 전체 테스트 실행: pytest + npm test → 모두 통과 확인
```

---

## 6. 근본 원인 정리

| 구분 | 내용 |
|------|------|
| **직접 원인** | `LobbyScreen.tsx`의 `connectedActive` 필터가 `connected: undefined` (방장 초기 상태)를 falsy로 처리 |
| **간접 원인** | `App.tsx`에서 방 생성/참가 시 `connected` 필드를 명시하지 않음 |
| **백엔드** | 이상 없음 — `room.players`는 방장 포함, `game_service.py` 검증 로직 정상 |
| **수정 복잡도** | 매우 낮음 (핵심 수정 1줄: `!== false` 변경) |

---

## 7. 검증 체크리스트

- [ ] `방장 + 2명 인간` 조합으로 시작 버튼 활성화 확인
- [ ] `방장 + 1명 인간 + 1 봇` 조합으로 시작 버튼 활성화 확인
- [ ] `방장 + 2 봇` 조합으로 시작 버튼 활성화 확인
- [ ] `방장 혼자` 또는 `방장 + 1명`에서 시작 버튼 비활성화 확인
- [ ] 게임 시작 후 백엔드에서 정상적으로 3인 게임 초기화 확인
- [ ] 전체 기존 테스트 회귀 없음 확인
