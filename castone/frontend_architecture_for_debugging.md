# Frontend Architecture For Debugging

이 문서는 현재 `frontend/` 코드베이스를 빠르게 이해하고, 특히 멀티플레이어 로비, 게임 상태 반영, WebSocket, UI 정지처럼 보이는 문제를 디버깅할 때 알아야 하는 내용을 정리한 문서다.

기준 경로:
- [frontend/src/main.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/main.tsx)
- [frontend/src/App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx)
- [frontend/src/hooks/useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)
- [frontend/src/components/LobbyScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/LobbyScreen.tsx)
- [frontend/src/components/RoomListScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/RoomListScreen.tsx)
- [frontend/src/types/gameState.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/types/gameState.ts)

## 1. 전체 구조

프론트는 전형적인 다중 페이지 라우터 구조가 아니라, `App.tsx` 하나가 거의 모든 앱 상태를 들고 `screen` 값으로 화면을 전환하는 구조다.

핵심 흐름:
1. `main.tsx`에서 `GoogleOAuthProvider`와 `App`을 띄운다.
2. `App.tsx`가 로그인 상태, 현재 화면, 로비 상태, 게임 상태를 모두 소유한다.
3. 로비는 별도 WebSocket으로 동기화된다.
4. 게임 진행 상태는 별도 game WebSocket으로 동기화된다.
5. 각 세부 컴포넌트는 대부분 `App.tsx`가 내려주는 props만 렌더하는 presentational component에 가깝다.

즉, 프론트 구조를 이해하려면 대부분 [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx) 하나를 먼저 읽어야 한다.

## 2. 엔트리포인트

### [main.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/main.tsx)

역할:
- React root 생성
- Google OAuth provider 초기화
- i18n 초기화

여기서 중요한 점:
- Google 로그인은 프론트에서 `credential`만 받고, 실제 인증 처리는 백엔드 `/api/puco/auth/google`로 넘긴다.
- 앱 전역 라우팅이나 전역 상태 라이브러리는 없다. Redux, Zustand 같은 저장소도 없다.

## 3. 앱의 실제 컨트롤 타워

### [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx)

이 파일이 사실상 프론트 애플리케이션 전체의 컨트롤러다.

크게 보면 상태가 5종류 있다.

1. 인증 상태
- `authToken`
- `authUser`
- `nicknameInput`
- `nicknameError`

2. 화면 전환 상태
- `screen`
- 가능한 값:
  - `loading`
  - `login`
  - `home`
  - `rooms`
  - `join`
  - `lobby`
  - `game`

3. 현재 세션/방 상태
- `gameId`
- `myName`
- `myPlayerId`
- `isMultiplayer`
- `isSpectator`

4. 로비 상태
- `lobbyPlayers`
- `lobbyHost`
- `lobbyError`
- `lobbyWsRef`

5. 게임 상태
- `state` (`GameState | null`)
- `error`
- `saving`
- 각종 UI 보조 state:
  - `buildConfirm`
  - `pendingSettlement`
  - `sellingGood`
  - `mayorPending`
  - `finalScores`
  - popup 관련 refs/state

이 구조의 장점:
- 디버깅할 때 대부분의 상태를 한 파일에서 따라갈 수 있다.

이 구조의 단점:
- 한 파일에 로직이 많이 몰려 있어, 화면/네트워크/게임 인터랙션이 섞여 있다.
- 상태 업데이트가 서로 간섭하기 쉽다.
- 로비 상태와 게임 상태, WS 상태가 한 곳에 섞여 있어 stale state가 남기 쉽다.

## 4. 화면 전환 구조

`App.tsx`는 별도 라우터 없이 `screen` 값으로 분기한다.

렌더 흐름:
- `loading` → 초기 인증 확인
- `login` → [LoginScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/LoginScreen.tsx)
- `home` → [HomeScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/HomeScreen.tsx)
- `rooms` → [RoomListScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/RoomListScreen.tsx)
- `join` → [JoinScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/JoinScreen.tsx)
- `lobby` → [LobbyScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/LobbyScreen.tsx)
- `game` → 게임 보드 렌더

중요한 점:
- URL 기반 라우팅이 아니라 상태 기반 라우팅이다.
- 그래서 “삭제된 방인데 화면은 그대로”, “예전 gameId가 남아 있음”, “로비에서 게임 화면으로 넘어갔는데 일부 상태가 남음” 같은 문제는 router보다 `App.tsx` 내부 state reset 경로에서 자주 생긴다.

## 5. 인증 흐름

### 로그인
- [LoginScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/LoginScreen.tsx)에서 Google OAuth credential을 받는다.
- `handleGoogleLogin()`이 백엔드 `/api/puco/auth/google`로 POST한다.
- 응답으로 받은 `access_token`을 `localStorage.setItem('access_token', ...)`로 저장한다.

### 앱 시작 시 인증 확인
- `initializeApp()`이 `/api/puco/auth/me`를 호출한다.
- token이 유효하면 `screen`을 `home`으로 바꾼다.
- 유효하지 않으면 `access_token`을 지우고 `login`으로 보낸다.

중요한 디버깅 포인트:
- 로그인 문제는 대체로 `localStorage access_token` 유무와 `/auth/me` 응답만 확인하면 된다.
- 별도 refresh token 로직은 없다.

## 6. 방 목록과 로비 진입

### [RoomListScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/RoomListScreen.tsx)

역할:
- 방 목록 fetch
- 방 생성
- 공개방/비밀방 참가
- bot-game 생성 버튼

실제 API:
- `GET /api/puco/rooms/`
- `POST /api/puco/rooms/`
- `POST /api/puco/rooms/{roomId}/join`

여기서 중요한 점:
- 이 컴포넌트는 자체적으로 room 목록만 가진다.
- 실제로 어느 방에 들어갔는지, lobby WS를 붙일지, game 화면으로 넘길지는 전부 `App.tsx`가 결정한다.

### 로비 진입

`App.tsx` 기준:
- `handleCreateRoom()`
- `handleJoinRoom()`
- `handleJoin()`

가 `gameId`, `myName`, `isMultiplayer`, `lobbyPlayers`, `screen='lobby'` 등을 세팅하고 `connectLobbyWs(roomId)`를 호출한다.

즉 로비 진입은 “HTTP 성공 후 state 전환 + lobby websocket 연결”의 조합이다.

## 7. 로비 WebSocket 구조

### 연결 함수
- [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx)의 `connectLobbyWs(roomId)`

동작:
1. 기존 로비 WS가 있으면 닫음
2. `ws://${window.location.host}/api/puco/ws/lobby/${roomId}`에 연결
3. `onopen`에서 `{ token: authToken }` 전송
4. `onmessage`에서 메시지 타입별 처리

처리하는 메시지:
- `LOBBY_STATE`
- `LOBBY_UPDATE`
- `ROOM_DELETED`
- `GAME_STARTED`

메시지별 effect:
- `LOBBY_STATE`, `LOBBY_UPDATE`
  - `setLobbyPlayers(msg.players ?? [])`
  - host 플레이어를 찾아 `setLobbyHost(...)`
- `ROOM_DELETED`
  - `closeLobbyWs()`
  - `setScreen('rooms')`
  - `setLobbyError('방이 삭제되었습니다.')`
- `GAME_STARTED`
  - `setState(gs)`
  - 내 `display_name`과 일치하는 human player를 찾아 `setMyPlayerId(...)`
  - `closeLobbyWs()`
  - `setScreen('game')`

중요한 점:
- 로비 플레이어 목록의 authoritative source는 원래 서버의 lobby websocket 메시지다.
- 그런데 `handleAddBot()`와 `handleRemoveBot()`도 프론트 로컬 `lobbyPlayers`를 직접 건드리고 있어서, 이 부분이 desync의 주요 원인 후보다.

## 8. 로비 UI에서 자주 생기는 문제

### [LobbyScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/LobbyScreen.tsx)

역할:
- 로비 인원 렌더
- host 여부 판단
- start 버튼 활성화 판단
- bot 추가/제거 버튼 렌더

중요 포인트:
- `players.map(p => <div key={p.name}>...)` 형태로 렌더한다.
- 즉 이름이 같으면 React key 충돌이 난다.
- bot 이름이 `Bot (ppo)`처럼 반복되면 duplicate key 문제가 생길 수 있다.

또한:
- `autoName(type)`으로 bot 이름을 만들지만, 이 함수는 현재 `players.map(p => p.name)` 기준으로만 중복 회피를 한다.
- 서버가 보내는 실제 식별자 `player_id`와 분리되어 있다.

디버깅할 때 꼭 봐야 할 것:
- `players` 배열에 실제 몇 명이 들어있는지
- 화면상 몇 개가 렌더되는지
- key 충돌 warning이 있는지
- `handleAddBot()` 이후 즉시 local append와 lobby WS update가 동시에 오는지

## 9. 게임 진입과 게임 상태 수신 구조

게임 상태는 현재 SSE가 아니라 WebSocket이 주 경로다.

### 비활성화된 레거시 경로
- [useGameSSE.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameSSE.ts)

현재 `App.tsx`에서는:
- `sessionKey: null`

로 호출되어 사실상 사용하지 않는다.

### 실제 경로
- [useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)

이 훅이 실제 게임 상태 수신의 핵심이다.

## 10. 게임 WebSocket 구조

### 연결 조건
`useGameWebSocket()`은 다음 두 조건이 있어야 연결한다.
- `gameId`
- `token`

`App.tsx`에서는:
- `gameId: screen === 'game' ? gameId : null`

로 넣고 있으므로, `screen`이 `game`이 아닐 때는 game websocket이 아예 안 붙는다.

### 연결 URL
- `ws://${location.host}/api/puco/ws/${gameId}`
- 또는 https면 `wss://...`

즉, 프론트 dev server를 쓰는 개발 환경에서는 `location.host`가 `localhost:3000`이고, Vite proxy가 websocket upgrade를 backend로 넘겨줘야 한다.

### 인증 방식
- `onopen`에서 `ws.send(JSON.stringify({ token }))`

즉, game websocket은 HTTP header auth가 아니라 “첫 메시지로 JWT 보내기” 방식이다.

### 수신 처리
처리하는 타입:
- `STATE_UPDATE`
- `GAME_ENDED`
- `PLAYER_DISCONNECTED`

`STATE_UPDATE` 처리 순서:
1. raw JSON parse
2. `action_mask`를 top-level 또는 embedded state에서 읽음
3. 로그 출력
4. `{data, mask}`를 JSON stringify해서 dedupe
5. 동일 state면 무시
6. 다르면 `onStateUpdateRef.current(richState, actionMask)` 호출

중요한 점:
- dedupe는 이 훅 안에서 이미 한 번 하고 있다.
- 따라서 상위 `App.tsx`에서 또 대충 skip해버리면 실제 필요한 state 변화가 사라질 수 있다.

## 11. App.tsx에서 게임 상태를 어떻게 쓰는가

`useGameWebSocket()`의 `onStateUpdate` 안에서 결국 `setState(gs)`를 한다.

현재 로그 포인트:
- `frontend_set_state_before`
- `frontend_set_state_applied`
- `frontend_render_state`
- `frontend_ui_block_state`

이 로그들로 확인 가능한 것:
- websocket이 실제로 상태를 받고 있는지
- React state 적용이 실제로 일어나는지
- 렌더에 사용되는 `active_player`, `phase`, `bot_thinking`이 무엇인지
- UI가 왜 blocked로 간주되는지

## 12. 프론트가 “봇이 안 움직인다”고 느끼게 되는 이유

이 코드베이스에서 사용자가 그렇게 느끼는 이유는 대체로 세 가지다.

1. 실제 backend stall
- 현재까지의 로그 기준으로는 주원인이 아닐 때가 많다.

2. websocket은 상태를 받고 있지만, 프론트가 일부 update를 skip
- `useGameWebSocket()`의 dedupe
- `App.tsx`의 별도 skip
- 둘 다 겹치면 화면이 덜 움직이는 것처럼 보일 수 있다.

3. UI 차단 조건이 체감상 “멈춤”처럼 보이게 만듦
- `App.tsx`의 `isBlocked`
- `isMyTurn`
- `isBotTurn`
- `bot_thinking`

현재 렌더에서 실제 영향:
- 액션 카드가 `!isBlocked`일 때만 보이기도 함
- 주요 버튼이 `disabled={... || isBlocked}`가 됨
- 하단 sticky bar에서 기다리는 턴 배너가 계속 보임

즉, state는 계속 변하는데 사용자는 “내가 할 수 있는 게 없고, 화면도 크게 달라지지 않는다”고 느낄 수 있다.

## 13. 게임 화면 렌더 계층

게임 화면은 [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx) 안에서 큰 화면 레이아웃을 직접 구성한다.

주요 하위 컴포넌트:
- [MetaPanel.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/MetaPanel.tsx)
- [CommonBoardPanel.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/CommonBoardPanel.tsx)
- [PlayerPanel.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/PlayerPanel.tsx)
- [SanJuan.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/SanJuan.tsx)
- [HistoryPanel.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/HistoryPanel.tsx)
- [PlayerAdvantages.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/PlayerAdvantages.tsx)

### MetaPanel
- round
- phase
- governor
- active player
- vp supply

즉 최상단 메타 상태를 빠르게 보는 패널이다.

### CommonBoardPanel
- 역할 선택 테이블
- 이주민 배
- trading house
- goods supply
- cargo ships
- plantation 선택 영역

상호작용 prop:
- `onSelectRole`
- `onSettlePlantation`
- `onUseHacienda`

이 값들이 `undefined`면 UI는 보이지만 클릭 동작은 없다.

### PlayerPanel
- 플레이어별 goods
- production
- island
- city
- mayor 배치 토글
- bot type 아이콘

즉 플레이어별 상세 상태는 대부분 여기서 렌더된다.

## 14. 게임 액션 송신 구조

게임 액션은 거의 전부 `channelAction(actionIndex)`로 수렴한다.

### 핵심 함수
- [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx)의 `channelAction()`

실제 API:
- `POST /api/puco/game/{gameId}/action`

payload:
```json
{
  "payload": {
    "action_index": 15
  }
}
```

즉 프론트는 고수준 명령이 아니라 “엔진 action_index”를 서버에 보내는 thin client에 가깝다.

### action index helper
- `channelActionIndex`

예:
- `sell(good)`
- `loadShip(good, shipIndex)`
- `craftsmanPriv(good)`
- `mayorIsland(slotIndex)`
- `mayorCity(slotIndex)`

이 방식의 장점:
- 프론트가 게임 규칙을 깊게 재구현하지 않아도 된다.

이 방식의 단점:
- index mapping이 틀리면 UI는 멀쩡해 보여도 전혀 다른 액션이 나간다.
- 디버깅할 때 숫자 index의 의미를 같이 봐야 한다.

## 15. 타입 모델: 프론트가 실제로 믿는 서버 응답 형태

### [types/gameState.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/types/gameState.ts)

이 파일은 프론트가 서버 응답을 어떤 shape로 기대하는지 보여준다.

특히 중요:
- `GameState`
- `Meta`
- `Decision`
- `LobbyPlayer`
- `CommonBoard`
- `Player`

디버깅 시 핵심 필드:
- `state.meta.phase`
- `state.meta.active_player`
- `state.meta.bot_thinking`
- `state.decision.type`
- `state.decision.player`
- `state.bot_players`
- `state.history`

프론트 렌더에서 자주 혼동되는 필드:
- `meta.active_player`
- `decision.player`

둘이 항상 완전히 같은 의미로 쓰이지 않을 수 있으므로, UI/로그에서 둘 다 확인하는 게 좋다.

## 16. i18n 구조

### [i18n.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/i18n.ts)

특징:
- `localStorage.getItem('lang') ?? 'ko'`
- 한국어 기본
- `ko`, `en`, `it` 번역 파일 사용

중요한 점:
- 화면 텍스트는 번역 key를 거치므로, 디버깅할 때 텍스트 literal 검색이 안 잡히는 경우가 많다.
- 예를 들어 버튼 라벨은 `t('lobby.start')`, `t('game.waitingTurn')`처럼 렌더된다.

## 17. 테스트 구조

현재 테스트는 많지 않다.

확인된 테스트:
- [useGameWebSocket.test.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/__tests__/useGameWebSocket.test.ts)
- [vite.config.test.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/vite.config.test.ts)

즉 현재 프론트는:
- websocket hook 수준 테스트는 일부 있음
- 화면 상태 머신이나 로비/게임 전환 통합 테스트는 거의 없음

그래서 지금 같은 문제는 브라우저 재현과 console log 의존도가 높다.

## 18. 지금 이 프로젝트에서 프론트를 볼 때 우선순위

### 가장 먼저 읽어야 할 파일 순서
1. [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx)
2. [useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)
3. [types/gameState.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/types/gameState.ts)
4. [LobbyScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/LobbyScreen.tsx)
5. [RoomListScreen.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/RoomListScreen.tsx)
6. [CommonBoardPanel.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/CommonBoardPanel.tsx)
7. [PlayerPanel.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components/PlayerPanel.tsx)

### 멀티플레이/봇 문제를 볼 때 꼭 확인할 상태
- `screen`
- `gameId`
- `myPlayerId`
- `isMultiplayer`
- `isSpectator`
- `state.meta.active_player`
- `state.decision.player`
- `state.meta.bot_thinking`
- `state.bot_players`
- `lobbyPlayers`

### 자주 문제 나는 경계면
1. HTTP 성공 후 로컬 state 전환
2. 로비 WS 연결/종료
3. 게임 WS 연결/인증
4. WS 수신 후 dedupe
5. `setState` 이후 UI 차단 조건
6. 로비 상태와 게임 상태 사이의 stale state

## 19. 현재 디버깅에 직접 유효한 관찰 포인트

### bot이 안 움직이는 것처럼 보일 때
다음을 순서대로 본다.

1. 브라우저 콘솔
- `frontend_ws_onopen`
- `frontend_ws_auth_send`
- `frontend_ws_message_type`
- `frontend_state_update_received`
- `frontend_set_state_applied`
- `frontend_render_state`
- `frontend_ui_block_state`

2. state 값
- `active_player`
- `decision.player`
- `phase`
- `bot_thinking`

3. 렌더 gating
- `isMyTurn`
- `isBlocked`
- 액션 카드가 렌더되는 조건

### bot이 두 배로 보일 때
다음을 본다.

1. `lobbyPlayers`의 실제 배열 길이
2. `LOBBY_UPDATE` 직후 값
3. `handleAddBot()`의 local append 여부
4. `LobbyScreen.tsx`의 React key

### 삭제된 방 문제를 볼 때
다음을 본다.

1. `ROOM_DELETED` 수신 여부
2. 그 직후 `gameId`, `state`, `lobbyPlayers`가 초기화되는지
3. `screen`만 바뀌고 예전 state가 남는지

## 20. 요약

이 프론트는 “얇은 화면”처럼 보이지만 실제로는 `App.tsx`에 상태와 흐름이 많이 몰려 있는 stateful app이다.

핵심적으로 기억할 것:
- 라우터가 아니라 `screen` state가 화면 전환을 담당한다.
- 로비와 게임은 서로 다른 websocket을 쓴다.
- 게임 state의 진실원은 backend가 보내는 `STATE_UPDATE`다.
- 프론트는 `GameState` 전체를 들고 렌더하며, `meta`, `decision`, `bot_players` 조합으로 UI를 차단하거나 활성화한다.
- 지금 같은 버그는 대체로 backend 엔진보다도
  - 로컬 상태를 프론트가 임의로 덧붙이는 곳
  - websocket 수신 후 중복 제거 로직
  - stale `gameId`/`screen`/`state`
  - blocked UI 조건
에서 생긴다.

실무적으로는 [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx)와 [useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts) 두 파일을 먼저 완전히 이해하면, 현재 프론트 문제의 대부분은 따라갈 수 있다.
