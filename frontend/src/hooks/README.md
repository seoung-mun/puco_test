# frontend/src/hooks

상태 부트스트랩과 실시간 통신을 담당하는 React 훅 폴더입니다.

## 하위 문서

- [__tests__/README.md](__tests__/README.md)

## 주요 파일

- [useAuthBootstrap.ts](useAuthBootstrap.ts): 토큰/유저/닉네임 bootstrap
- [useGameWebSocket.ts](useGameWebSocket.ts): 현재 기본 실시간 게임 상태 수신
- [useGameSSE.ts](useGameSSE.ts): 레거시 SSE 경로
- [useReplayList.ts](useReplayList.ts): 종료 게임 리플레이 목록 페이지네이션/필터
- [useReplayPlayer.ts](useReplayPlayer.ts): 리플레이 재생 상태 (재생/일시정지/스텝 이동)

## 의존성

- inbound: [../App.tsx](../App.tsx)
- outbound: backend auth/game/lobby API, browser `localStorage`, WebSocket

## 메모

- 새 실시간 기능은 WebSocket 기준으로 먼저 붙이는 편이 안전합니다.
