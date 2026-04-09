# Frontend

`frontend/`는 Castone의 React SPA입니다. 로그인, 방/로비, 실시간 게임 화면, 관전 흐름, 종료 화면까지 모두 여기서 조립합니다.

## 하위 문서

- [src/README.md](src/README.md)
- [public/README.md](public/README.md)

## 역할

- Google OAuth 로그인과 nickname bootstrap
- 방 생성/입장/봇전 생성
- 로비 WebSocket 연결과 게임 시작 전환
- 게임 WebSocket 상태 수신과 액션 dispatch
- strategy-first Mayor를 포함한 인간 플레이 UI
- 관리자 디버그 패널과 최종 결과 화면 표시

## 실행

로컬 직접 실행:

```bash
cd frontend
npm ci
npm run dev
```

검증 명령:

```bash
npm run test
npm run build
npm run lint
```

Docker 실행은 루트 문서를 기준으로 봅니다.

- dev compose: [../README.md](../README.md)
- prod compose: [../README.md](../README.md)

## 필수 환경 변수

- `VITE_GOOGLE_CLIENT_ID`
- `VITE_INTERNAL_API_KEY`
- `VITE_API_TARGET`

프로덕션 이미지는 정적 빌드이므로 위 값이 바뀌면 이미지를 다시 빌드해야 합니다.

## 현재 구조 요약

1. [src/main.tsx](src/main.tsx)가 Provider와 앱을 mount합니다.
2. [src/App.tsx](src/App.tsx)가 screen 상태, REST 호출, 게임 액션 orchestration을 담당합니다.
3. [src/hooks/useAuthBootstrap.ts](src/hooks/useAuthBootstrap.ts)가 토큰/사용자 초기화를 맡습니다.
4. [src/components/AppScreenGate.tsx](src/components/AppScreenGate.tsx)가 login/rooms/lobby/game 화면을 분기합니다.
5. [src/components/GameScreen.tsx](src/components/GameScreen.tsx)가 실제 게임 화면을 조립합니다.
6. [src/hooks/useGameWebSocket.ts](src/hooks/useGameWebSocket.ts)가 실시간 상태 수신을 담당합니다.
7. [src/utils/devOrigin.ts](src/utils/devOrigin.ts)가 개발 환경 origin 계산을 보조합니다.

## 의존성

- 상위 문서: [../README.md](../README.md)
- backend contract: [../backend/README.md](../backend/README.md)
- action/state source: [../PuCo_RL/README.md](../PuCo_RL/README.md), [../contract.md](../contract.md)

## 현재 핵심 계약과 주의점

- 기본 실시간 경로는 WebSocket이며 SSE는 레거시 보조 경로입니다.
- Mayor는 `69-71` strategy action 중 하나를 단일 제출합니다.
- `GameState`는 backend serializer가 만든 rich state shape를 기준으로 유지합니다.
- `JoinScreen`에는 spectator 선택 UI가 있지만, 현재 channel API 직접 참가 흐름에서는 완전 지원되지 않습니다.
- 일부 경로는 여전히 `display_name === myName` 비교로 내 플레이어를 추론하므로, 장기적으로는 안정적인 player id 기준 정리가 필요합니다.

## 테스트

컨테이너 안에서:

```bash
docker compose exec frontend npm run test
docker compose exec frontend npm run build
```

## 변경 시 체크

- 액션 인덱스를 손대면 `App.tsx`, `GameScreen.tsx`, `types/gameState.ts`, backend serializer, `PuCo_RL/env/pr_env.py`를 함께 확인합니다.
- `screen` 전이, socket lifecycle, auth bootstrap을 바꾸면 [src/__tests__/README.md](src/__tests__/README.md)와 [src/hooks/__tests__/README.md](src/hooks/__tests__/README.md)의 테스트도 같이 손봅니다.
- `i18n.ts`의 `localStorage` 접근은 테스트 환경 가드가 계속 중요합니다.

## 추가 참고 문서

- [backend/README.md](../backend/README.md)
- [PuCo_RL/README.md](../PuCo_RL/README.md)
- [src/README.md](src/README.md)
