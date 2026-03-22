# puertorico UI 브릿지 레이어 구현 계획

## 배경
- `castone` RL 엔진은 PettingZoo AEC 환경으로, WebSocket으로 구조화된 JSON [observation](file:///Users/seoungmun/Documents/agent_dev/castone/PuCo_RL/env/pr_env.py#51-53)을 전송
- `puertorico` 프론트엔드는 [GameState](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/types/gameState.ts#195-203) 타입 인터페이스 기반으로 설계된 16개 React 컴포넌트 보유
- **목표**: 백엔드 무수정으로, 브릿지 훅 하나로 두 시스템을 연결

---

## 결정 사항

| 항목 | 결정 |
|:---|:---|
| 데이터 소스 | castone WebSocket (JSON) |
| 매핑 방향 | [observation](file:///Users/seoungmun/Documents/agent_dev/castone/PuCo_RL/env/pr_env.py#51-53) → [GameState](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/types/gameState.ts#195-203) |
| 이식 범위 | 핵심 컴포넌트 6개 선별 이식 |
| 3인 게임 | Prospector/Prospector2 역할 UI 완전 제거 |

---

## 새로 생성할 파일 구조

```
castone/frontend/src/
├── types/
│   └── [NEW] gameState.ts          # puertorico 타입 그대로 복사 (prospector 제거)
├── lib/
│   └── [NEW] obsToGameState.ts     # observation → GameState 매퍼
├── hooks/
│   └── [NEW] useGameBridge.ts      # WebSocket + 매핑 + 액션 전송 훅
└── components/
    └── game/
        ├── [NEW] IslandGrid.tsx    (from puertorico)
        ├── [NEW] CityGrid.tsx      (from puertorico)
        ├── [NEW] CargoShips.tsx    (from puertorico)
        ├── [NEW] TradingHouse.tsx  (from puertorico)
        ├── [NEW] RolePanel.tsx     (커스텀: Prospector 없음, 6개 역할만)
        └── [NEW] GameBoard.tsx     (조합 컨테이너)
```

---

## 주요 변경 사항

### [NEW] [types/gameState.ts](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/types/gameState.ts)
[puertorico/frontend/src/types/gameState.ts](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/types/gameState.ts)에서 복사. 변경 사항:
- [RoleName](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/types/gameState.ts#2-3)에서 `'prospector'`, `'prospector_2'` 제거
- `Meta.num_players`를 `3`으로 고정 기본값 처리

### [NEW] `lib/obsToGameState.ts`
[observation](file:///Users/seoungmun/Documents/agent_dev/castone/PuCo_RL/env/pr_env.py#51-53) JSON → [GameState](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/types/gameState.ts#195-203) 변환 매퍼.

**매핑 키:**

| castone observation | GameState |
|:---|:---|
| `global_state.current_phase` (int) | `meta.phase` (string) |
| `global_state.governor_idx` | `meta.governor` ("player_N") |
| `global_state.roles_available[0..5]` | `common_board.roles` |
| `global_state.cargo_ships_good[N]` | `common_board.cargo_ships[N].good` |
| `global_state.trading_house[0..3]` | `common_board.trading_house.goods` |
| `players.player_N.island_tiles[0..11]` | `players["player_N"].island.plantations` |
| `players.player_N.city_buildings[0..11]` | `players["player_N"].city.buildings` |

**Phase 인덱스 매핑** (engine.py의 [Phase](file:///Users/seoungmun/Documents/agent_dev/castone/PuCo_RL/configs/constants.py#3-13) enum 기준):
```
0 = SETTLER → 'settler_action'
1 = MAYOR   → 'mayor_action'
2 = BUILDER → 'builder_action'
3 = CRAFTSMAN → 'craftsman_action'
4 = TRADER  → 'trader_action'
5 = CAPTAIN → 'captain_action'
6 = CAPTAIN_STORE → 'captain_discard'
9 = END_ROUND → 'role_selection'
```

### [NEW] `hooks/useGameBridge.ts`
```typescript
const { gameState, actionMask, sendAction, isMyTurn } = useGameBridge(wsUrl, myPlayerIdx);
```
- WebSocket 연결 및 메시지 수신
- `obsToGameState()` 적용하여 `gameState` 노출
- `actionMask` (200-dim `int8[]`) 노출
- `sendAction(index: number)` — WebSocket으로 액션 인덱스 전송

### [NEW] `components/game/RolePanel.tsx`
3인 게임용 역할 패널 (6개 역할):
- `action_mask[0..5]` 기반으로 클릭 가능 여부 결정
- Prospector 버튼 없음

### [COPY] [IslandGrid.tsx](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/components/IslandGrid.tsx), [CityGrid.tsx](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/components/CityGrid.tsx), [CargoShips.tsx](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/components/CargoShips.tsx), [TradingHouse.tsx](file:///Users/seoungmun/Documents/agent_dev/castest/puertorico/frontend/src/components/TradingHouse.tsx)
`puertorico/frontend/src/components/`에서 직접 복사. 수정 최소화.

---

## 검증 계획

### 자동화
- `obsToGameState()` 함수에 대한 유닛 테스트 (`lib/__tests__/obsToGameState.test.ts`)
  - 각 Phase int → string 변환 정확성
  - islands/city 슬롯 패딩 정확성

### 수동
1. `castone` 게임 세션 시작
2. 보드에 초기 농장(인디고2개, 옥수수1개)이 올바르게 표시되는지 확인
3. 역할 선택 패널에서 6개 역할만 나타나는지 확인
4. 역할 클릭 시 `action_mask` 기반으로 활성화/비활성화 제대로 동작하는지 확인
