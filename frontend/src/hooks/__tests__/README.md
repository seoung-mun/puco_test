# frontend/src/hooks/__tests__

커스텀 훅의 연결/수명주기 계약을 검증하는 폴더입니다.

## 현재 테스트

- `useGameWebSocket.test.ts`: auth-first message, dedupe, reconnect, cleanup

## 메모

- socket lifecycle을 바꾸면 이 테스트가 가장 먼저 깨져야 합니다.
