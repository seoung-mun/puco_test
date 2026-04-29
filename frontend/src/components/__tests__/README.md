# frontend/src/components/__tests__

컴포넌트 단위 UI 계약을 검증하는 테스트 폴더입니다.

## 현재 검증 축

- `MayorSequentialPanel.test.tsx`: Mayor slot 버튼, disabled state, `engine_action_index`+`canonical_id` 사용
- `AvailablePlantations.test.tsx`: Hacienda pending 보호 + face_up `engine_action_index`+`canonical_id`
- `GameScreen.test.tsx`: 게임 화면 통합 (배속/일시정지 컨트롤 포함)
- `RoomListScreen.test.tsx`, `LobbyScreen.test.tsx`, `LoginScreen.test.tsx`: 방/로비/로그인 흐름
- `CommonBoardPanel.test.tsx`, `EndGamePanel.test.tsx`, `SanJuan.test.tsx`: 핵심 패널 렌더링
- `Pagination.test.tsx`: 공통 페이지네이션
- `ReplayConfirmModal.test.tsx`, `ReplayListScreen.test.tsx`, `ReplayViewScreen.test.tsx`: 리플레이 흐름

## 의존성

- 대상 컴포넌트: [../README.md](../README.md)
- 상위 통합 테스트: [../../__tests__/README.md](../../__tests__/README.md)
