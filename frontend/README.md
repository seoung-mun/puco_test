# Frontend

이 디렉터리는 Puerto Rico 웹 클라이언트입니다.  
React 19 + TypeScript + Vite 기반 SPA이며, 로그인, 방 생성/입장, 로비, 실시간 게임 화면, 종료 결과 화면까지 모두 담당합니다.

## 역할

- Google OAuth 기반 로그인 및 닉네임 초기 설정
- 대기방 목록 조회, 방 생성/입장/퇴장
- 로비 WebSocket 연결 및 `GAME_STARTED` 수신
- 게임 WebSocket 연결 및 상태 반영
- 실시간 액션 UI 렌더링
- 최종 점수 조회와 기록 화면 표시
- 관리자 파라미터 디버그 화면 노출 (`?admin`)

## 기술 스택

- React 19
- TypeScript
- Vite 7
- Vitest + Testing Library
- i18next
- Google OAuth (`@react-oauth/google`)

## 현재 구조 요약

실제 진입점은 [main.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/main.tsx) 이고, 대부분의 애플리케이션 흐름은 [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx) 에 집중되어 있습니다.

주요 파일:

- [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx)
  - 전체 화면 상태 머신
  - 인증 토큰 보관
  - 방/로비/게임 전환
  - 채널 액션 인덱스 매핑
  - 시장/선장/시장/Mayor 특수 UI 제어
- [hooks/useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)
  - 게임 실시간 상태 수신
  - 인증 메시지 전송
  - 재연결 및 중복 상태 제거
- [hooks/useGameSSE.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameSSE.ts)
  - 레거시 SSE 훅
  - 현재 채널 모드에서는 기본 경로가 아님
- [i18n.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/i18n.ts)
  - 다국어 초기화
  - `localStorage`에서 언어를 읽음
- [components/](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/components)
  - 화면별 UI 조각

## 화면 흐름

`App.tsx`는 명시적인 라우터 대신 내부 `screen` 상태로 화면을 전환합니다.

- `loading`
- `login`
- `home`
- `rooms`
- `join`
- `lobby`
- `game`

현재 실제 기본 진입은 `home`이 아니라 `rooms` 입니다.  
`home` 화면 컴포넌트는 남아 있지만, 인증 성공 후 `initializeApp()`은 바로 방 목록으로 이동합니다.

이 구조는 단순하지만, 한 파일에 책임이 많이 모여 있습니다.  
화면 추가나 흐름 변경 시에는 `screen` 전이와 관련 side effect를 같이 확인해야 합니다.

## 통신 구조

### 1. 인증

- 프론트는 Google 로그인 성공 후 credential을 백엔드 `POST /api/puco/auth/google` 으로 전송합니다.
- 백엔드는 JWT를 발급하고, 프론트는 이를 `localStorage.access_token`에 저장합니다.
- 닉네임이 없으면 `PATCH /api/puco/auth/me/nickname` 을 호출합니다.

### 2. REST API

프론트는 방 목록, 방 생성/입장, 게임 시작, 액션 요청, 최종 점수 조회 등에 REST를 사용합니다.

중요:

- 일부 레거시 write endpoint는 `X-API-Key` 헤더를 기대합니다.
- 프론트는 [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx) 의 `apiFetch()`에서 `VITE_INTERNAL_API_KEY`를 자동 주입합니다.
- 봇 타입 목록은 아직 legacy `GET /api/bot-types`를 사용합니다.
- 즉시 시작 봇전은 `POST /api/puco/rooms/bot-game` 으로 만들고, 사용자는 플레이어가 아니라 host spectator처럼 입장합니다.

### 3. 로비 WebSocket

- 게임 시작 전에는 로비 소켓을 별도로 연결합니다.
- `GAME_STARTED` 메시지를 받으면 게임 화면으로 전환합니다.

### 4. 게임 WebSocket

- 게임 화면에서는 [useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts) 가 `/api/puco/ws/{gameId}` 에 연결합니다.
- 연결 직후 첫 메시지로 JWT를 전송합니다.
- `STATE_UPDATE`, `GAME_ENDED`, `PLAYER_DISCONNECTED` 를 처리합니다.

## 액션 인덱스 계약

프론트 액션 버튼은 사람이 읽는 UI 이벤트를 백엔드 정수 action index로 변환합니다.

핵심 매핑은 [App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx) 의 `channelActionIndex`에 있습니다.

이 값들은 반드시 아래와 일치해야 합니다.

- [PuCo_RL/env/pr_env.py](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/pr_env.py)
- [backend/app/services/state_serializer.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py)

특히 다음 구간이 중요합니다.

- `39~43`: Trader
- `44~58`: Captain load
- `59~63`: Wharf
- `64~68`: Windrose
- `69~92`: Mayor 관련
- `93~97`: Craftsman privilege
- `105`: Hacienda
- `106~110`: Warehouse

프론트와 RL 환경의 액션 계약이 어긋나면 UI는 정상처럼 보여도 전혀 다른 행동이 서버에 전달될 수 있습니다.

## 로컬 실행

### 개발 서버

```bash
cd frontend
npm install
npm run dev
```

기본 Vite 개발 서버는 `http://localhost:5173` 이고, `/api` 요청은 Vite proxy를 통해 백엔드로 전달됩니다.

### Docker 기반 실행

루트에서:

```bash
docker compose up -d --build
```

일반적으로 접근 포트는 다음과 같습니다.

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`
- Adminer: `http://127.0.0.1:8080`

## 환경 변수

주요 변수:

- `VITE_API_TARGET`
  - Vite dev proxy 대상
- `VITE_GOOGLE_CLIENT_ID`
  - Google OAuth Provider 설정
- `VITE_INTERNAL_API_KEY`
  - 레거시 write endpoint용 API key

관련 파일:

- [.env.example](/Users/seoungmun/Documents/agent_dev/castest/castone/.env.example)
- [vite.config.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/vite.config.ts)
- [nginx.conf](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/nginx.conf)

## 테스트

```bash
cd frontend
npm run test
```

Vitest는 `jsdom` 환경을 사용합니다.

관련 파일:

- [vite.config.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/vite.config.ts)
- [src/test/setup.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/test/setup.ts)

현재 주의점:

- [i18n.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/i18n.ts) 가 import 시점에 `localStorage`를 직접 읽기 때문에, 브라우저 전역이 없는 환경에서는 테스트가 쉽게 깨질 수 있습니다.
- 이 문제는 2026-04-05 Docker 테스트 보고서에도 기록되어 있습니다.

## 프론트 개발 시 꼭 알아야 할 점

### `App.tsx`가 사실상 앱 컨트롤 타워입니다

현재는 화면 전환, 인증, 게임 진행, 일부 도메인 로직이 한 파일에 모여 있습니다.  
버그 수정 시 UI만 보지 말고 다음 세 가지를 같이 봐야 합니다.

- 현재 `screen` 전이
- 현재 `state.meta.phase`
- 현재 내 turn 여부와 action mask

### SSE는 남아 있지만 기본은 WebSocket입니다

`useGameSSE()`가 존재하지만, 현재 멀티플레이어의 핵심 경로는 WebSocket입니다.  
새 기능은 WebSocket 기준으로 먼저 생각하는 편이 안전합니다.

### Mayor UI는 일반 액션보다 복잡합니다

Mayor는 단순 버튼 클릭이 아니라, 임시 배치 상태를 프론트에서 모았다가 서버로 보내는 흐름이 섞여 있습니다.  
관련 상태는 `mayorPending`, `lastMayorDistRef`, `buildMayorPlacements()` 등을 함께 봐야 합니다.

또한 실제 channel API의 Mayor 제출은 legacy 24칸 배열이 아니라 `slot_id` + `count` 목록을 `POST /api/puco/game/{game_id}/mayor-distribute` 로 보내는 계약입니다.

### 언어/인증 상태가 `localStorage`에 남습니다

- `lang`
- `access_token`
- 일부 멀티플레이어 키

테스트나 디버깅 시 예전 브라우저 상태가 버그처럼 보일 수 있으므로 먼저 저장 상태를 확인하는 편이 좋습니다.

### 현재 내 플레이어 식별은 표시 이름에 의존하는 경로가 있습니다

`App.tsx`는 일부 경로에서 `GameState.players`를 순회하며 `display_name === myName` 으로 `myPlayerId`를 추론합니다.  
따라서 중복 표시 이름이 생기면 멀티플레이어에서 취약할 수 있습니다. 계약상 `display_name`은 UI용 이름이지 안정적인 식별자와 동일하지 않습니다.

### `JoinScreen`의 spectator 선택은 아직 완전 지원이 아닙니다

화면에는 player/spectator 선택이 있지만, 현재 channel API의 직접 참가 흐름에서는 spectator가 실질적으로 활성화되어 있지 않습니다.  
반대로 `bot-game` 경로는 별도 계약으로 spectator-host를 허용합니다.

## 추천 개선 방향

- `App.tsx`를 화면 상태 머신과 게임 도메인 훅으로 분리
- 채널 액션 매핑을 프론트 상수 파일로 분리하고 서버/RL과 계약 문서화
- `i18n.ts`의 `localStorage` 접근을 런타임 가드 처리하여 테스트 안정화
- 로비/게임 WebSocket 전환 책임을 훅 또는 provider로 분리

## 추가 참고 문서

- [backend/readme.md](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/readme.md)
- [PuCo_RL/README.MD](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/README.MD)
- [docker_test_report_2026-04-05.md](/Users/seoungmun/Documents/agent_dev/castest/castone/docs/docker_test_report_2026-04-05.md)
- [2026-04-05_error_priority_tdd_architecture_plan.md](/Users/seoungmun/Documents/agent_dev/castest/castone/error_report/2026-04-05_error_priority_tdd_architecture_plan.md)
