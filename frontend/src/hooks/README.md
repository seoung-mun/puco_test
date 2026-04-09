# frontend/src/hooks

상태 부트스트랩과 실시간 통신을 담당하는 React 훅 폴더입니다.

## 하위 문서

- [__tests__/README.md](__tests__/README.md)

## 주요 파일

- [useAuthBootstrap.ts](useAuthBootstrap.ts): 토큰/유저/닉네임 bootstrap
- [useGameWebSocket.ts](useGameWebSocket.ts): 현재 기본 실시간 게임 상태 수신
- [useGameSSE.ts](useGameSSE.ts): 레거시 SSE 경로

## 의존성

- inbound: [../App.tsx](../App.tsx)
- outbound: backend auth/game/lobby API, browser `localStorage`, WebSocket

## 메모

- 새 실시간 기능은 WebSocket 기준으로 먼저 붙이는 편이 안전합니다.
