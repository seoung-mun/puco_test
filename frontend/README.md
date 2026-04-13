# Frontend

`frontend/`는 Castone의 React SPA입니다. 로그인, 방/로비, 실시간 게임 화면, spectator 흐름, 종료 화면까지 모두 여기서 조립합니다.

## 하위 문서

- [src/README.md](src/README.md)
- [public/README.md](public/README.md)

## 역할

- Google OAuth 로그인과 nickname bootstrap
- 방 생성/입장/봇전 생성
- 로비 WebSocket 연결과 게임 시작 전환
- 게임 WebSocket 상태 수신과 액션 dispatch
- slot-direct Mayor를 포함한 인간 플레이 UI
- 관리자 디버그 패널과 최종 결과 화면 표시

## 현재 구조 요약

프론트의 흐름은 이제 아래처럼 나뉩니다.

1. [src/main.tsx](src/main.tsx)가 Provider와 앱을 mount
2. [src/App.tsx](src/App.tsx)가 screen 상태, REST 호출, 게임 액션 orchestration 담당
3. [src/hooks/useAuthBootstrap.ts](src/hooks/useAuthBootstrap.ts)가 토큰/사용자 초기화 담당
4. [src/components/AppScreenGate.tsx](src/components/AppScreenGate.tsx)가 login/rooms/lobby/game 화면 분기
5. [src/components/GameScreen.tsx](src/components/GameScreen.tsx)가 실제 게임 화면 조립
6. [src/hooks/useGameWebSocket.ts](src/hooks/useGameWebSocket.ts)가 실시간 상태 수신

## 의존성

- 상위 문서: [../README.md](../README.md)
- backend contract: [../backend/README.md](../backend/README.md)
- action/state source: [../PuCo_RL/README.md](../PuCo_RL/README.md), [../contract.md](../contract.md)

## 현재 핵심 계약

- 기본 실시간 경로는 WebSocket이며 SSE는 레거시 보조 경로입니다.
- Mayor는 `120-131` island / `140-151` city action 중 하나를 매번 제출합니다.
- 프론트는 `mayor_legal_island_slots`, `mayor_legal_city_slots`, `action_mask`를 함께 사용해 slot-direct Mayor UI를 렌더링합니다.
- `GameState`는 backend serializer가 만든 rich state shape를 기준으로 유지합니다.

## 실행

```bash
cd frontend
npm install
npm run dev
```

또는 루트에서:

```bash
docker compose up -d --build
```

## 테스트

```bash
docker compose exec frontend npm test
docker compose exec frontend npm run build
```

## 변경 시 체크

- 액션 인덱스를 손대면 `App.tsx`, `GameScreen.tsx`, `types/gameState.ts`, backend serializer, `PuCo_RL/env/pr_env.py`를 함께 확인합니다.
- `screen` 전이나 socket lifecycle을 바꾸면 [src/__tests__/README.md](src/__tests__/README.md)와 [src/hooks/__tests__/README.md](src/hooks/__tests__/README.md)의 테스트도 같이 손봅니다.

### 현재 내 플레이어 식별은 표시 이름에 의존하는 경로가 있습니다

`App.tsx`는 일부 경로에서 `GameState.players`를 순회하며 `display_name === myName` 으로 `myPlayerId`를 추론합니다.  
따라서 중복 표시 이름이 생기면 멀티플레이어에서 취약할 수 있습니다. 계약상 `display_name`은 UI용 이름이지 안정적인 식별자와 동일하지 않습니다.

### `JoinScreen`의 spectator 선택은 아직 완전 지원이 아닙니다

화면에는 player/spectator 선택이 있지만, 현재 channel API의 직접 참가 흐름에서는 spectator가 실질적으로 활성화되어 있지 않습니다.  
반대로 `bot-game` 경로는 별도 계약으로 spectator-host를 허용합니다.

## 남은 구조 메모

- 일부 경로에서 `display_name === myName` 기반 식별을 아직 사용하므로, 장기적으로는 안정적인 player id 기준으로 정리하는 편이 안전합니다.
- `JoinScreen`의 spectator 선택 UI와 실제 channel contract 지원 범위는 아직 완전히 일치하지 않습니다.
- `i18n.ts`의 `localStorage` 접근은 테스트 환경 가드가 계속 중요합니다.

## 추가 참고 문서

- [backend/README.md](../backend/README.md)
- [PuCo_RL/README.md](../PuCo_RL/README.md)
- [docker_test_report_2026-04-05.md](/Users/seoungmun/Documents/agent_dev/castest/castone/docs/docker_test_report_2026-04-05.md)
- [2026-04-05_error_priority_tdd_architecture_plan.md](/Users/seoungmun/Documents/agent_dev/castest/castone/error_report/2026-04-05_error_priority_tdd_architecture_plan.md)
