# Bug Investigation Report — 2026-04-03

**대상 컴포넌트**: 로비(Lobby) → 게임(Game) 전환 흐름  
**관련 파일**:
- `frontend/src/App.tsx`
- `frontend/src/components/LobbyScreen.tsx`
- `backend/app/services/lobby_manager.py`
- `backend/app/api/channel/game.py`
- `backend/app/api/channel/lobby_ws.py`

---

## 목차

1. [에러 현상 요약](#1-에러-현상-요약)
2. [시스템 구조 이해](#2-시스템-구조-이해)
3. [Bug 1 — 봇이 UI에서 2개로 표시되는 현상](#3-bug-1--봇이-ui에서-2개로-표시되는-현상)
4. [Bug 2 — 게임 시작 400 Bad Request](#4-bug-2--게임-시작-400-bad-request)
5. [Bug 3 — Action 404 Not Found (치명적)](#5-bug-3--action-404-not-found-치명적)
6. [수정 요약](#6-수정-요약)
7. [유사하게 발생할 수 있는 문제 패턴](#7-유사하게-발생할-수-있는-문제-패턴)
8. [재발 방지를 위한 설계 원칙](#8-재발-방지를-위한-설계-원칙)

---

## 1. 에러 현상 요약

브라우저 개발자 도구와 백엔드 도커 로그에서 수집한 에러:

| # | 현상 | 에러 코드 | 심각도 |
|---|------|-----------|--------|
| 1 | 봇 1개 추가 시 UI에 2개가 표시됨 | React key warning | 중간 |
| 2 | 게임 시작 버튼 클릭 시 400 Bad Request | HTTP 400 | 중간 |
| 3 | 게임 시작 후 액션 시 404 Not Found + WS 재연결 루프 | HTTP 404 | 치명적 |

**에러 로그 (브라우저 콘솔)**:
```
Encountered two children with the same key, `Bot (ppo)`. Keys should be unique...
:3000/api/puco/game/47ebfb95-c84e.../start  Failed: 400 Bad Request
:3000/api/puco/game/47ebfb95-c84e.../action  Failed: 404 Not Found
[vite] server connection lost. Polling for restart...
[WS_TRACE] frontend_ws_onclose {intentional: false}
[WS_TRACE] frontend_ws_reconnect {delayMs: 3000}  ← 이후 무한 반복
```

**에러 로그 (백엔드 도커)**:
```
POST /api/puco/game/47ebfb95.../add-bot  → 200 OK
POST /api/puco/game/47ebfb95.../start    → 400 Bad Request
POST /api/puco/game/47ebfb95.../add-bot  → 200 OK  (두 번째 봇 추가)
[BOT_TRACE] players=['94881c94-...', 'BOT_ppo', 'BOT_ppo']
POST /api/puco/game/47ebfb95.../start    → 200 OK   (두 번째 시도)
connection closed   ← lobby WS 종료
WebSocket /api/puco/ws/47ebfb95...  [accepted]
POST /api/puco/game/47ebfb95.../action   → 404 Not Found  ← !!!
```

---

## 2. 시스템 구조 이해

버그를 이해하려면 로비→게임 전환 플로우를 먼저 파악해야 한다.

### 관련 WebSocket 채널 구조

```
프론트엔드
│
├─ Lobby WebSocket (/api/puco/ws/lobby/{room_id})
│    - 로비 화면에서 열림
│    - 플레이어 목록(LOBBY_STATE/LOBBY_UPDATE) 수신
│    - 게임 시작 신호(GAME_STARTED) 수신
│    └─ 게임 시작 시 closeLobbyWs() 호출로 닫힘
│
└─ Game WebSocket (/api/puco/ws/{game_id})
     - 게임 화면 진입 시 열림
     - STATE_UPDATE, GAME_ENDED 수신
```

### 로비→게임 전환 시퀀스 (정상 기대)

```
Host UI                  Backend                  Lobby WS
  │                         │                        │
  │──POST /add-bot──────────>│                        │
  │<─200 OK─────────────────│                        │
  │                    commit to DB                   │
  │                         │──LOBBY_UPDATE──────────>│
  │<═══════════════════════LOBBY_UPDATE (WS)══════════│
  │                         │                        │
  │──POST /start────────────>│                        │
  │                    room.status = PROGRESS         │
  │                         │──GAME_STARTED──────────>│
  │<═══════════════════════GAME_STARTED (WS)══════════│ ← closeLobbyWs() 호출
  │<─200 OK─────────────────│                        │
  │    (setScreen('game'))  │                   WS 종료
  │                         │
  │    [Game WS 열림]        │
  │──POST /action───────────>│
  │<─200 OK─────────────────│
```

---

## 3. Bug 1 — 봇이 UI에서 2개로 표시되는 현상

### 현상

봇을 1개 추가했는데 로비 플레이어 목록에 동일한 봇이 2개 표시된다. React 콘솔에 `Encountered two children with the same key, 'Bot (ppo)'` 경고가 함께 출력된다.

### 근본 원인: 상태 업데이트 경로가 2개

#### 원인 A — 이중 상태 업데이트 (App.tsx)

`handleAddBot` 함수가 두 가지 경로로 동시에 UI를 갱신했다.

```
POST /add-bot 응답
    │
    ├─ [경로 1] App.tsx handleAddBot():
    │    setLobbyPlayers(prev => [...prev, { name: `Bot (${data.bot_type})`, ... }])
    │    → 즉시 로컬에 봇 추가
    │
    └─ [경로 2] 백엔드가 LOBBY_UPDATE 브로드캐스트
         → Lobby WS onmessage: setLobbyPlayers(msg.players ?? [])
         → 서버 목록으로 덮어씀 (봇 포함)
```

두 경로가 거의 동시에 실행되면서:
1. 경로 1에서 로컬에 봇 즉시 추가 → UI에 봇 표시됨
2. 경로 2에서 서버 목록(봇 1개 포함)으로 교체 → 다시 1개로 됨

...이 사이에 React render가 일어나면 잠깐 2개가 보이거나, 타이밍에 따라 경로 1이 경로 2를 **덮어써서** 2개가 고착되기도 한다.

**문제가 되는 코드 (수정 전)**:
```typescript
// App.tsx - handleAddBot()
const data = await res.json();
setLobbyPlayers(prev => [...prev, {
  name: `Bot (${data.bot_type})`,
  player_id: `BOT_${data.bot_type}`,
  is_bot: true,
  connected: true
}]);
// ← 이 줄이 문제: WS LOBBY_UPDATE와 경합
```

#### 원인 B — React key 충돌 (LobbyScreen.tsx)

같은 타입의 봇 2개(예: ppo + ppo)를 추가하면 둘 다 `name: "Bot (ppo)"`가 된다. `key={p.name}`을 사용하면 두 엘리먼트의 key가 동일해진다.

```tsx
// LobbyScreen.tsx (수정 전)
{players.map(p => (
  <div key={p.name} ...>  // ← "Bot (ppo)"가 2개면 key 충돌
```

React는 중복 key를 만나면 하나를 버리거나 DOM을 잘못 재사용한다.

#### 원인 C — 백엔드의 봇 player_id가 null (lobby_manager.py)

백엔드가 LOBBY_UPDATE를 브로드캐스트할 때 봇의 `player_id`를 `None`으로 전송:

```python
# lobby_manager.py _build_lobby_payload() (수정 전)
players_out.append({
    "name": f"Bot ({bot_type})",
    "player_id": None,   # ← 모든 봇이 null
    "is_bot": True,
    ...
})
```

결과: 동일 타입 봇 2개가 `{name: "Bot (ppo)", player_id: null}`로 구분 불가능.

### 진단 과정

1. React 콘솔의 `same key` 경고 확인 → `LobbyScreen.tsx`의 `key={p.name}` 발견
2. 봇이 언제 추가되는지 추적 → `handleAddBot`의 로컬 `setLobbyPlayers` 발견
3. Lobby WS `onmessage`도 `setLobbyPlayers`를 호출함을 확인 → 이중 업데이트 확인
4. 백엔드 `_build_lobby_payload()`에서 봇의 `player_id`가 `None`임을 발견

### 해결

**Fix A — handleAddBot에서 로컬 상태 업데이트 제거** (App.tsx):

```typescript
// 수정 후: Lobby WS LOBBY_UPDATE만을 신뢰하는 단일 경로
const res = await fetch(`.../add-bot`, { ... });
if (!res.ok) { setLobbyError(await res.text()); return; }
await res.json();  // 응답 소비만 하고 상태 업데이트 제거
```

**Fix B — React key를 고유한 값으로 변경** (LobbyScreen.tsx):

```tsx
// 수정 후: player_id를 key로, 없으면 인덱스 fallback
{players.map((p, idx) => (
  <div key={p.player_id ?? `player-${idx}`} ...>
```

**Fix C — 봇 player_id를 고유하게 생성** (lobby_manager.py):

```python
# 수정 후: 슬롯 인덱스를 포함하여 고유한 ID 생성
for idx, raw_pid in enumerate(room.players or []):
    pid = str(raw_pid)
    if pid.startswith("BOT_"):
        bot_type = pid[4:]
        players_out.append({
            "name": f"Bot ({bot_type})",
            "player_id": f"BOT_{bot_type}_{idx}",  # ← 고유 ID
            ...
        })
```

---

## 4. Bug 2 — 게임 시작 400 Bad Request

### 현상

게임 시작 버튼 클릭 시 `POST /start → 400 Bad Request` 발생.

### 근본 원인: UI 상태와 서버 상태 불일치

Bug 1의 원인 A(로컬 상태 선행 업데이트) 때문에 발생한 **파생 버그**다.

```
실제 서버 상태:  players = [human_id, BOT_ppo]         (2명)
UI 표시 상태:   players = [human, Bot(ppo), Bot(ppo)]   (3명 — 로컬 낙관적 업데이트)
```

1. 봇 1개 추가 → `handleAddBot`이 로컬에서 즉시 1명 추가 → UI에 3명으로 보임
2. `canStart` 조건(`connectedActive.length >= 3`)이 true가 됨 → 시작 버튼 활성화
3. 실제 서버에는 2명뿐이므로 `start_game()`에서 `Need at least 3 players` ValueError → 400

**백엔드 검증 코드** (game_service.py):
```python
def start_game(self, game_id: UUID):
    actual_players = len(room.players or [])
    if actual_players < 3:
        raise ValueError(f"Need at least 3 players to start, currently {actual_players}")
```

### 해결

Bug 1의 Fix A(로컬 상태 업데이트 제거)로 자동 해결된다.

서버가 LOBBY_UPDATE를 보내기 전까지 UI의 플레이어 수가 변하지 않으므로, 서버 상태가 실제로 3명이 될 때만 시작 버튼이 활성화된다.

---

## 5. Bug 3 — Action 404 Not Found (치명적)

### 현상

게임이 성공적으로 시작된 후, 첫 번째 액션을 보내면 `POST /action → 404 Not Found`가 발생한다. 이후 Game WebSocket 연결이 끊기고 무한 재연결 루프에 빠진다.

### 진단 과정

#### 1단계: 404의 원인 코드 특정

`perform_action` 엔드포인트에서 404를 반환하는 경우는 단 하나뿐이다:

```python
# backend/app/api/channel/game.py
@router.post("/{game_id}/action")
async def perform_action(...):
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Game not found")  # ← 여기
```

즉, **동일한 game_id로 DB에서 room을 찾지 못했다**. `/start`가 200으로 성공했는데 같은 ID로 room이 없다는 것은 **방이 삭제**되었다는 의미다.

#### 2단계: 무엇이 방을 삭제하는가?

`db.delete(room)`을 호출하는 코드를 추적:

```python
# backend/app/services/lobby_manager.py - handle_leave()
if human_count == 0 or (is_host_leaving and room.status == "WAITING"):
    db.delete(room)  # ← GameSession 삭제
    db.commit()
```

#### 3단계: handle_leave가 언제 호출되는가?

```python
# backend/app/api/channel/lobby_ws.py
@router.websocket("/{room_id}")
async def lobby_websocket(room_id: str, websocket: WebSocket):
    ...
    try:
        ...  # 게임 진행
    except WebSocketDisconnect:
        pass
    finally:
        if player_id:
            lobby_manager.disconnect(room_id, player_id)
            with SessionLocal() as leave_db:
                await handle_leave(room_id, player_id, leave_db, lobby_manager)
                # ↑ WebSocket이 닫히면 무조건 호출됨
```

#### 4단계: Lobby WS는 언제 닫히는가?

게임 시작 시 프론트엔드가 `closeLobbyWs()`를 호출:

```typescript
// App.tsx - handleLobbyStart()
await fetch(`.../start`, ...);
closeLobbyWs();  // ← Lobby WS 강제 종료
setScreen('game');
```

또는 Lobby WS `GAME_STARTED` 핸들러에서도:

```typescript
ws.onmessage = (event) => {
    if (msg.type === 'GAME_STARTED') {
        closeLobbyWs();  // ← 마찬가지로 종료
    }
};
```

#### 5단계: 전체 버그 체인 재구성

```
게임 시작 (POST /start → 200 OK)
    │
    ├─ 백엔드: room.status = "PROGRESS", db.commit()
    │
    ├─ 프론트: handleLobbyStart() → closeLobbyWs() 호출
    │              └─ WebSocket.close() 실행
    │
    └─ 백엔드 lobby_ws.py finally 블록 실행
           └─ handle_leave(room_id, player_id) 호출
                  │
                  ├─ room.players 에서 human player 제거
                  │    players = ["BOT_ppo", "BOT_ppo"]  ← human 제거됨
                  │
                  ├─ human_count = _count_humans(players) = 0  ← 봇만 남음
                  │
                  └─ if human_count == 0:
                         db.delete(room)  ← GameSession 완전 삭제 !!!
                         db.commit()
```

**결론**: 게임이 PROGRESS 상태가 된 후 Lobby WS가 정상 종료되면, `handle_leave`가 호출되어 방에서 인간 플레이어를 제거하고 봇만 남게 되므로 `human_count == 0` 조건이 만족되어 게임 세션 자체가 삭제된다.

이 설계의 원래 의도는 "대기 중인 방에서 모든 인간이 떠나면 방을 정리한다"였지만, 게임 시작 시의 정상적인 Lobby WS 종료를 "인간이 떠남"으로 잘못 해석한 것이다.

### 해결

`handle_leave()`에 상태 가드를 추가:

```python
# lobby_manager.py - handle_leave() (수정 후)
async def handle_leave(room_id, player_id, db, manager):
    room = db.query(GameSession).filter(GameSession.id == room_id)...first()
    if room is None:
        return

    # 핵심 수정: 게임이 이미 시작된 경우 로비 이탈 처리를 하지 않음
    # Lobby WS는 게임 시작 시 정상적으로 닫히기 때문에 이것은 예상된 동작임
    if room.status != "WAITING":
        return   # ← 이 한 줄이 치명적 버그를 막는다

    # 이하 기존 로직 (WAITING 상태에서만 실행)
    ...
```

---

## 6. 수정 요약

| 파일 | 수정 내용 | 해결된 버그 |
|------|-----------|-------------|
| `frontend/src/App.tsx` | `handleAddBot`에서 `setLobbyPlayers` 로컬 업데이트 제거 | Bug 1, Bug 2 |
| `frontend/src/components/LobbyScreen.tsx` | `key={p.name}` → `key={p.player_id ?? \`player-${idx}\`}` | Bug 1 (React key) |
| `backend/app/services/lobby_manager.py` | 봇 `player_id`를 `f"BOT_{bot_type}_{idx}"`로 고유하게 생성 | Bug 1 (key 원천) |
| `backend/app/services/lobby_manager.py` | `handle_leave()`에 `if room.status != "WAITING": return` 추가 | Bug 3 (치명적) |

### 변경된 코드 diff 요약

```diff
# App.tsx - handleAddBot
  await fetch(`.../add-bot`, ...);
  if (!res.ok) { ... }
- const data = await res.json();
- setLobbyPlayers(prev => [...prev, { name: `Bot (${data.bot_type})`, ... }]);
+ await res.json();

# LobbyScreen.tsx
- {players.map(p => (
-   <div key={p.name} ...>
+ {players.map((p, idx) => (
+   <div key={p.player_id ?? `player-${idx}`} ...>

# lobby_manager.py - _build_lobby_payload
- for raw_pid in (room.players or []):
+ for idx, raw_pid in enumerate(room.players or []):
      if pid.startswith("BOT_"):
-         "player_id": None,
+         "player_id": f"BOT_{bot_type}_{idx}",

# lobby_manager.py - handle_leave
  if room is None:
      return
+ if room.status != "WAITING":
+     return
```

---

## 7. 유사하게 발생할 수 있는 문제 패턴

이번 버그들은 특정 코드에만 국한된 것이 아니라, 웹 앱 개발에서 반복적으로 나타나는 설계 패턴의 문제다.

### 패턴 1: 낙관적 UI 업데이트(Optimistic Update)와 서버 이벤트 경합

**설명**: REST API 응답으로 로컬 상태를 먼저 업데이트하고, 이후 실시간 이벤트(WebSocket/SSE)로도 같은 상태를 업데이트하는 구조에서 경합이 발생한다.

**발생하기 쉬운 상황**:
- 채팅 앱: 메시지 전송 후 로컬에 즉시 추가 + 서버 확인 이벤트로도 추가
- 좋아요 버튼: 즉시 카운트 올리기 + SSE로 실제 카운트 수신
- 장바구니: 아이템 추가 즉시 반영 + 재고 변경 이벤트 수신

**올바른 접근**:
- 단일 진실 공급원(Single Source of Truth) 원칙: 서버 이벤트를 신뢰하고, 로컬 업데이트는 순수한 "로딩 인디케이터" 역할만 부여
- 낙관적 업데이트가 필요하다면 서버 응답이 오면 무조건 서버 값으로 교체하는 reconciliation 로직 필수
- React Query, SWR 같은 라이브러리의 `optimisticUpdate + rollback` 패턴 활용

```typescript
// 안전한 낙관적 업데이트 패턴
async function addBot(botType: string) {
  const tempId = `temp-${Date.now()}`;
  // 1. 낙관적으로 추가 (temp ID 부여)
  setPlayers(prev => [...prev, { id: tempId, name: `Bot (${botType})`, temp: true }]);
  try {
    await fetch('/add-bot', ...);
    // 2. 서버 이벤트(LOBBY_UPDATE)가 올 때까지 대기
    // 이벤트 핸들러에서 temp 항목 제거 후 서버 목록으로 교체
  } catch {
    // 3. 실패 시 rollback
    setPlayers(prev => prev.filter(p => p.id !== tempId));
  }
}
```

---

### 패턴 2: WebSocket 생명주기와 비즈니스 로직의 혼합

**설명**: WebSocket 연결 해제 이벤트를 "사용자가 의도적으로 떠난 것"으로 간주하는 로직은, 시스템이 내부적으로 연결을 닫는 경우에도 같은 코드가 실행된다.

**이번 버그의 패턴**:
```
게임 시작 → WS 닫힘(내부 동작) → handle_leave() → 방 삭제(의도치 않은 결과)
```

**다른 사례들**:
- 화상회의: 발표자가 화면 공유 종료 시 WS 채널 닫힘 → "회의 나감" 처리
- 게임 방: 맵 로딩을 위해 WS 재연결 → "이탈" 처리로 방에서 추방
- 인증 갱신: 토큰 만료로 WS 재연결 → "오프라인" 상태로 잘못 표시

**올바른 접근**:
- WebSocket 종료 이유를 구분: 정상 종료(intentional), 오류(error), 시스템에 의한 종료(system)
- `close code`와 `reason`을 활용하여 의도적 종료와 비의도적 종료를 구분
- **상태(status) 가드 패턴**: 비즈니스 상태(WAITING/PROGRESS/FINISHED)에 따라 이벤트 핸들러 동작을 달리함

```python
# 좋은 패턴: 상태로 컨텍스트 구분
async def handle_disconnect(room_id, player_id, db):
    room = get_room(db, room_id)
    if room is None:
        return  # 이미 없음
    if room.status == "PROGRESS":
        # 게임 중 연결 끊김 → 재연결 대기, 방 유지
        mark_player_disconnected(room, player_id)
    elif room.status == "WAITING":
        # 로비에서 이탈 → 방 정리 로직
        remove_player_and_cleanup(room, player_id, db)
    elif room.status == "FINISHED":
        return  # 종료된 게임은 건드리지 않음
```

---

### 패턴 3: React List Key의 안정성 문제

**설명**: `key`가 배열 인덱스나 표시 문자열(name)에 의존할 때, 데이터가 변경되면 React가 컴포넌트를 잘못 재사용한다.

**발생하기 쉬운 상황**:
- `key={index}`: 배열 중간 삭제/삽입 시 이후 항목의 key가 바뀜 → 상태 꼬임
- `key={item.name}`: 동명 항목이 생기면 중복 key
- `key={Math.random()}`: 매 렌더마다 새로 생성 → 강제 리마운트

**올바른 접근**:
- 서버가 안정적이고 고유한 ID를 부여해야 한다
- 프론트엔드에서 임시 ID가 필요하다면 `uuid()` 등을 활용
- 배열에서 같은 타입의 항목이 여러 개 생길 수 있다면, 슬롯 인덱스나 UUID를 key로 사용

```typescript
// 위험한 패턴
players.map(p => <PlayerRow key={p.name} player={p} />)

// 안전한 패턴
players.map((p, idx) => (
  <PlayerRow
    key={p.id ?? `${p.type}-slot-${idx}`}  // 고유 ID 우선, 없으면 타입+슬롯
    player={p}
  />
))
```

---

### 패턴 4: REST + WebSocket 혼용 아키텍처에서의 일관성 문제

**설명**: REST API와 WebSocket이 동일한 데이터를 각각 다른 방식으로 전달할 때, 두 채널의 데이터가 불일치하거나 적용 순서가 달라질 수 있다.

**이번 구조의 위험 지점**:
```
POST /add-bot → 200 OK (bot_type 포함)
      +
Lobby WS → LOBBY_UPDATE (전체 플레이어 목록)
```

둘 다 플레이어 목록을 알려주지만 형태가 다르다. 어느 쪽을 신뢰할지 정하지 않으면 버그가 생긴다.

**올바른 접근**:
- **단방향 데이터 흐름**: 뮤테이션은 REST로, 상태 구독은 WebSocket으로 일원화
- REST 응답에는 최소한의 정보만 반환(성공/실패 여부), 상태는 WS 이벤트로만 수신
- 또는 반대로 REST 응답에 전체 상태를 포함하고 WS를 사용하지 않음

```
[권장 패턴 A - WS 중심]
POST /add-bot → { status: "ok" }  // 최소 응답
          ↓
    WS LOBBY_UPDATE → { players: [...] }  // 상태는 WS에서만

[권장 패턴 B - REST 중심]
POST /add-bot → { players: [...] }  // 전체 상태 포함
          ↓
    WS는 실시간 알림 전용 (선택적)
```

---

### 패턴 5: Finally 블록의 부작용

**설명**: `try/finally` 구조에서 finally 블록은 예외, 정상 종료, 강제 종료 모든 경우에 실행된다. 이것이 "항상 정리(cleanup)해야 한다"는 의도로 사용될 때, 예상치 못한 경로에서 side effect가 발생한다.

**이번 버그**:
```python
try:
    while True:
        await websocket.receive_text()  # 게임 시작 시 이 루프가 종료됨
except WebSocketDisconnect:
    pass
finally:
    await handle_leave(...)  # 모든 종료 경로에서 실행 → 방 삭제
```

**다른 사례들**:
- HTTP 요청 캔슬 시 finally에서 DB 트랜잭션 롤백 → 이미 커밋된 경우 오류
- 파일 업로드 중단 시 finally에서 임시 파일 삭제 → 부분 업로드 데이터 손실
- 게임 라운드 종료 시 finally에서 통계 저장 → 비정상 종료 통계가 섞임

**올바른 접근**:
- finally 블록에서는 순수 리소스 해제(메모리, 연결, 파일 핸들)만
- 비즈니스 로직은 finally에 넣지 말고, 명시적인 조건 분기로 처리
- cleanup 함수에 현재 상태를 전달하여 적절히 처리

```python
# 개선된 패턴
try:
    while True:
        await websocket.receive_text()
except WebSocketDisconnect:
    # 명시적으로 비의도적 종료 처리
    await handle_player_disconnect(room_id, player_id)
else:
    # 정상 종료 (게임 시작 등) 처리
    pass
finally:
    # 순수 리소스 해제만
    manager.disconnect(room_id, player_id)
```

---

### 패턴 6: 데이터베이스 상태와 인메모리 상태의 불일치

**설명**: 게임 엔진이 `GameService.active_engines` 딕셔너리(인메모리)에 저장되고, DB의 `GameSession`과 별도로 존재한다. DB 레코드가 삭제되어도 인메모리 엔진은 남아 있거나, 반대로 DB 레코드는 있는데 엔진이 없는 경우가 생긴다.

**이번 버그와의 관련**:
- DB의 `GameSession`이 삭제되어 `/action`이 404를 반환
- 그러나 `GameService.active_engines[game_id]`는 여전히 존재 → 메모리 누수

**발생하기 쉬운 상황**:
- 서버 재시작: 인메모리 엔진은 초기화되지만 DB의 PROGRESS 상태 방은 남음
- 다중 인스턴스: 인스턴스 A에서 시작한 게임을 인스턴스 B가 모름
- 트랜잭션 실패: DB 커밋 실패했지만 메모리는 업데이트됨

**올바른 접근**:
- 상태를 Redis 등 외부 공유 저장소에 저장하거나, DB를 단일 진실 공급원으로 사용
- 서버 시작 시 DB의 PROGRESS 방들을 복구하거나 INTERRUPTED로 마킹
- 메모리와 DB 상태를 주기적으로 동기화하는 reconciliation 작업 추가

---

## 8. 재발 방지를 위한 설계 원칙

### 원칙 1: 단일 진실 공급원 (Single Source of Truth)

같은 데이터를 여러 경로에서 업데이트하지 않는다. REST 응답과 WebSocket 이벤트 중 하나만 UI 상태를 갱신한다.

### 원칙 2: 상태 기반 이벤트 처리 (State-Based Event Handling)

WebSocket/이벤트 핸들러가 비즈니스 로직을 실행하기 전, 현재 도메인 상태(room.status, game.phase 등)를 반드시 확인한다.

```python
# 원칙 적용 예시
async def on_ws_disconnect(room_id, player_id):
    room = get_room(room_id)
    if room.status in ("PROGRESS", "FINISHED"):
        return  # 비즈니스 로직 실행 금지
    # WAITING 상태에서만 이탈 처리
```

### 원칙 3: 고유 식별자 보장

목록에 넣는 모든 항목은 서버에서 생성하든 클라이언트에서 생성하든 전역 고유 ID를 가져야 한다. 특히 같은 타입의 항목이 여러 개 생길 수 있는 경우(봇, 아이템, 메시지 등).

### 원칙 4: Cleanup과 비즈니스 로직 분리

`finally/disconnect/cleanup` 핸들러에서는 순수 리소스 해제만 수행한다. 비즈니스 로직(방 삭제, 플레이어 제거, 점수 계산)은 명시적인 조건 분기에서 처리한다.

### 원칙 5: 에러 코드로 원인 추적하기

- **404**: 리소스 자체가 없음 → DB에서 레코드가 사라진 것, 삭제 경로 추적
- **403**: 권한 없음 → 플레이어 목록 변경, 인증 토큰 불일치 확인
- **400**: 잘못된 요청 → 서버 상태와 클라이언트 상태의 불일치 확인
- **WS 재연결 루프**: 서버 크래시 또는 프록시 다운 → 백엔드 로그와 함께 확인

---

*작성일: 2026-04-03*  
*조사자: Claude (Sonnet 4.6)*  
*관련 커밋: dev 브랜치*
