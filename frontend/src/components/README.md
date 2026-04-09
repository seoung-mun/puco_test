# frontend/src/components

게임 화면과 주변 UI를 구성하는 React 컴포넌트 폴더입니다.

## 하위 문서

- [__tests__/README.md](__tests__/README.md)

## 구성

- 화면 shell
  - `AppScreenGate.tsx`
  - `GameScreen.tsx`
  - `HomeScreen.tsx`, `LoginScreen.tsx`, `JoinScreen.tsx`, `LobbyScreen.tsx`, `RoomListScreen.tsx`
- 게임 정보 패널
  - `MetaPanel.tsx`, `HistoryPanel.tsx`, `CommonBoardPanel.tsx`, `EndGamePanel.tsx`
- 플레이어/보드 표현
  - `PlayerPanel.tsx`, `PlayerAdvantages.tsx`, `CityGrid.tsx`, `IslandGrid.tsx`, `SanJuan.tsx`
- 액션 서브패널
  - `AvailablePlantations.tsx`, `CargoShips.tsx`, `TradingHouse.tsx`, `ColonistShip.tsx`, `MayorStrategyPanel.tsx`
- 운영 보조
  - `AdminPanel.tsx`

## 의존성

- outbound: [../types/README.md](../types/README.md), [../hooks/README.md](../hooks/README.md), [../../../imgs/README.md](../../../imgs/README.md)
- 상위 조립점: [../App.tsx](../App.tsx)

## 설계 메모

- `GameScreen.tsx`가 현재 게임 화면의 container 역할을 하고, 나머지는 주로 presentational or focused interaction component입니다.
- Mayor 관련 UI는 `MayorStrategyPanel.tsx` 하나로 strategy-first contract를 드러냅니다.
