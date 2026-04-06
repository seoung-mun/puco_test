# 🏝️ Puerto Rico — Board Game RL Balancing

보드게임 **푸에르토리코**를 인간 이상의 수준으로 플레이하는 **강화학습(RL) Agent**를 개발하고, 이를 통해 게임 내 **전략적 균형**을 분석하는 프로젝트입니다.

## 📋 프로젝트 목표

| 목표 | 설명 |
|------|------|
| 🎮 **게임 환경** | 푸에르토리코의 전체 규칙을 충실히 구현한 Gymnasium-compatible 환경 |
| 🤖 **RL Agent** | 고도의 전략적 판단이 가능한 강화학습 기반 AI Agent |
| 📊 **밸런스 분석** | Agent를 활용한 역할/건물/전략 간 균형 통계 분석 |

## 🏗 프로젝트 구조

```
PuertoRico-BoardGame-RL-Balancing/
├── configs/
│   └── constants.py          # 게임 상수, Enum(Phase, Role, Good, TileType, BuildingType), BUILDING_DATA
├── env/
│   ├── components.py          # 데이터 클래스 (IslandTile, CityBuilding, CargoShip)
│   ├── player.py              # Player 클래스 (보드, 자원, 건물 관리)
│   ├── engine.py              # 게임 엔진 (PuertoRicoGame) — 전체 규칙 및 상태 머신
│   └── pr_env.py              # Gymnasium 환경 래퍼 (PuertoRicoEnv)
├── agents/
│   └── random_agent.py        # Random Agent (mask 기반 랜덤 행동 선택)
├── tests/                     # 테스트 코드
├── utils/                     # 유틸리티
├── rules.txt                  # 푸에르토리코 공식 규칙서 (텍스트 추출)
├── puerto-rico-rules-en.pdf   # 공식 규칙서 원본 PDF
├── extract_pdf.py             # PDF → 텍스트 추출 스크립트
└── test_pr_env.py             # 환경 테스트 스크립트
```

## 🎲 게임 개요 — 푸에르토리코

> *Andreas Seyfarth* 디자인, 3~5인 플레이, BoardGameGeek 역대 최고 순위 보드게임 중 하나.

각 라운드마다 플레이어가 **역할**을 선택하면, 해당 역할의 행동을 **모든 플레이어**가 시계 방향으로 수행합니다. 역할을 선택한 플레이어에게는 **특권**이 주어집니다.

### 7가지 역할

| 역할 | 행동 | 특권 |
|------|------|------|
| **Settler** | 농장 타일 배치 | Quarry 선택 가능 |
| **Mayor** | 식민자 배치 | 추가 식민자 1명 |
| **Builder** | 건물 건설 | 건설 비용 -1 |
| **Craftsman** | 물건 생산 | 추가 물건 1개 |
| **Trader** | 물건 판매 | 판매 수익 +1 |
| **Captain** | 물건 선적 (VP 획득) | 추가 VP +1 |
| **Prospector** | 없음 | 더블론 +1 |

### 종료 조건 (하나라도 충족 시)

- 식민자 공급 부족으로 식민자 선박 보충 불가
- 한 플레이어가 12칸 도시를 모두 채움
- VP 칩 소진

## 🔧 기술 스택

| 구성 요소 | 기술 |
|-----------|------|
| 게임 엔진 | Pure Python (상태 머신 기반) |
| RL 환경 | [Gymnasium](https://gymnasium.farama.org/) (`gym.Env` 호환) |
| Action Masking | `valid_action_mask()` — 현재 Phase/상태에서 유효한 행동만 허용 |
| Agent | NumPy 기반 (추후 PPO/MaskablePPO 적용 예정) |

## 🧠 MDP 설계

### State Space (Observation)

```python
observation = {
    "global_state": {
        "vp_chips":             Discrete(150),           # 남은 VP 칩
        "colonists_supply":     Discrete(100),           # 식민자 공급
        "colonists_ship":       Discrete(30),            # 식민자 선박
        "goods_supply":         MultiDiscrete([15]*5),   # 5종 물건 공급
        "cargo_ships_good":     MultiDiscrete([6]*3),    # 화물선 적재 물건 종류
        "cargo_ships_load":     MultiDiscrete([15]*3),   # 화물선 적재량
        "trading_house":        MultiDiscrete([6]*4),    # 교역소
        "role_doubloons":       MultiDiscrete([20]*8),   # 역할별 보너스 더블론
        "roles_available":      MultiBinary(8),          # 선택 가능한 역할
        "face_up_plantations":  MultiDiscrete([7]*(N+1)),# 공개 농장 타일
        "quarry_stack":         Discrete(9),             # 남은 Quarry
        "current_player":       Discrete(N),             # 현재 플레이어
        "current_phase":        Discrete(10),            # 현재 Phase
    },
    "players": Tuple([  # × N players
        {
            "doubloons":          Discrete(100),
            "vp_chips":           Discrete(100),
            "goods":              MultiDiscrete([15]*5),
            "island_tiles":       MultiDiscrete([7]*12),
            "island_occupied":    MultiBinary(12),
            "city_buildings":     MultiDiscrete([24]*12),
            "city_colonists":     MultiDiscrete([4]*12),
            "unplaced_colonists": Discrete(20),
        }
    ])
}
```

### Action Space (Discrete(200))

| 범위 | 행동 | Phase |
|:----:|------|:-----:|
| 0-7 | 역할 선택 (Settler~Prospector2) | END_ROUND |
| 8-13 | 공개 농장 타일 선택 (index 0~5) | SETTLER |
| 14 | Quarry 선택 | SETTLER |
| 15 | Pass (Phase별 패스) | ALL |
| 16-38 | 건물 건설 (BuildingType 0~22) | BUILDER |
| 39-43 | 물건 판매 (Good 0~4) | TRADER |
| 44-58 | 화물선 적재 (ship×5 + good) | CAPTAIN |
| 59-63 | Wharf 적재 (Good 0~4) | CAPTAIN |
| 64-68 | 물건 보관 (Good 0~4) | CAPTAIN_STORE |
| 69-80 | Mayor Island 토글 (slot 0~11) | MAYOR |
| 81-92 | Mayor City 토글 (slot 0~11) | MAYOR |
| 93-97 | Craftsman 특권 물건 선택 (Good 0~4) | CRAFTSMAN |
| 98-103 | Settler + Hacienda 조합 (face-up 0~5) | SETTLER |
| 104 | Settler + Hacienda + Quarry | SETTLER |
| 105 | Settler + Hacienda + Pass | SETTLER |
| 106-199 | (Reserved) | — |

## 🚀 빠른 시작

### 설치

```bash
git clone https://github.com/dae-hany/PuertoRico-BoardGame-RL-Balancing.git
cd PuertoRico-BoardGame-RL-Balancing
pip install gymnasium numpy
```

### Random Agent 시뮬레이션

```bash
python -m agents.random_agent
```

100판의 4인 게임을 Random Agent로 시뮬레이션합니다:

```
Completed 10/100 games. Winner dist: [3, 2, 3, 2]
Completed 20/100 games. Winner dist: [5, 5, 5, 5]
...
Simulation complete in 12.34 seconds.
Final Wins: [25, 24, 26, 25]
```

### Gymnasium 환경 사용 예시

```python
from env.pr_env import PuertoRicoEnv
import numpy as np

env = PuertoRicoEnv(num_players=4)
obs, info = env.reset()

done = False
while not done:
    mask = env.valid_action_mask()
    valid_actions = np.where(mask)[0]
    action = np.random.choice(valid_actions)
    obs, reward, done, truncated, info = env.step(action)

# 게임 종료 시 최종 점수
print(info.get("final_scores"))
```

## 📊 밸런스 분석 (Balance Analysis)

학습된 모델을 기반으로 게임 밸런스를 분석할 수 있는 도구가 포함되어 있습니다.

```bash
python evaluate_balance.py --model_path models/ppo_checkpoint_update_50.pth --num_games 1000
```

### 분석 지표
- **Seat Bias**: 턴 순서(1~4번)에 따른 승률 편향
- **Strategy Type**: 승리 시 VP 구성 비율 (Shipping 위주 vs Building 위주)
- **Building Tier**: 승리자가 가장 많이 구매한 건물 순위

## 🏛️ 아키텍처

```
┌─────────────────────────────────────────────┐
│                  Agent                       │
│         (Random / RL Policy)                 │
│     select_action(obs, valid_mask)            │
└────────────┬───────────────┬────────────────┘
             │  action       │  obs, reward, mask
             ▼               │
┌────────────────────────────┴────────────────┐
│           PuertoRicoEnv (pr_env.py)          │
│  ┌──────────────────────────────────────┐   │
│  │  step(action)                         │   │
│  │  valid_action_mask()                  │   │
│  │  _get_obs() / _calculate_reward()     │   │
│  └──────────────┬───────────────────────┘   │
│                 │                            │
│  ┌──────────────▼───────────────────────┐   │
│  │    PuertoRicoGame (engine.py)         │   │
│  │  ┌───────────────────────────────┐   │   │
│  │  │  select_role()                 │   │   │
│  │  │  action_settler()              │   │   │
│  │  │  action_mayor_pass()           │   │   │
│  │  │  action_builder()              │   │   │
│  │  │  action_craftsman()            │   │   │
│  │  │  action_trader()               │   │   │
│  │  │  action_captain_load/pass()    │   │   │
│  │  │  action_captain_store()        │   │   │
│  │  │  get_scores() / check_game_end()│  │   │
│  │  └───────────────────────────────┘   │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  configs/constants.py   ← Enum, BUILDING_DATA│
│  env/components.py      ← IslandTile, Ship   │
│  env/player.py          ← Player             │
└──────────────────────────────────────────────┘
```

## 📜 구현된 건물 특수 능력

| 건물 | 효과 | 구현 |
|------|------|:----:|
| Small Market | 판매 시 +1 더블론 | ✅ |
| Large Market | 판매 시 +2 더블론 | ✅ |
| Hacienda | Settler Phase에서 추가 타일 드로우 | ✅ |
| Construction Hut | 비특권자도 Quarry 선택 가능 | ✅ |
| Small Warehouse | Captain Store에서 1종 전량 보관 | ✅ |
| Large Warehouse | Captain Store에서 2종 전량 보관 | ✅ |
| Hospice | 타일 배치 시 식민자 자동 배치 | ✅ |
| Office | Trading House 중복 물건 판매 가능 | ✅ |
| Factory | 다품종 생산 시 보너스 더블론 | ✅ |
| University | 건물 건설 시 식민자 자동 배치 | ✅ |
| Harbor | 선적 시 추가 VP +1 | ✅ |
| Wharf | 가상 선박으로 전량 선적 (1회/Captain) | ✅ |
| Guildhall | 종료 시 생산 건물당 보너스 VP | ✅ |
| Residence | 종료 시 채워진 섬 공간당 보너스 VP | ✅ |
| Fortress | 종료 시 식민자 3명당 +1 VP | ✅ |
| Customs House | 종료 시 VP칩 4개당 +1 VP | ✅ |
| City Hall | 종료 시 보라색 건물당 +1 VP | ✅ |

## 🗺️ 로드맵

- [x] 게임 엔진 (`env/engine.py`) — 전체 규칙 구현
- [x] Gymnasium 환경 래퍼 (`env/pr_env.py`) — Action Masking 포함
- [x] Random Agent 시뮬레이션 (`agents/random_agent.py`)
- [x] Action Space 정밀 설계 (Hacienda 조합, Craftsman 특권, Builder 열별 할인)
- [ ] MaskablePPO 기반 RL 학습 파이프라인
- [ ] Self-Play 프레임워크 (Multi-Agent)
- [ ] Reward Shaping 실험
- [ ] 역할/건물/전략 밸런스 통계 분석
- [ ] 하이퍼파라미터 튜닝 및 학습 곡선 시각화

## 📄 참고

- 게임 디자인: Andreas Seyfarth (2002)
- 공식 규칙서: `puerto-rico-rules-en.pdf` (repo 내 포함)

## 📝 라이선스

이 프로젝트는 학술 연구 및 개인 학습 목적으로 제작되었습니다.
'푸에르토리코'의 지적재산권은 원 저작자 및 퍼블리셔에게 있습니다.
