# 새 에이전트 추가 가이드

Puerto Rico AI Battle Platform의 에이전트 시스템은 플러그인 구조입니다.
**파일 3곳만 건드리면** 어떤 알고리즘이든 봇으로 등록할 수 있습니다.

---

## 파일 구조

```
PuCo_RL/agents/
├── base.py           ← AgentWrapper ABC (공통 인터페이스)
├── wrappers.py       ← 구체 Wrapper 구현체 (PPO, HPPO, Random ...)
├── ppo_agent.py      ← 표준 PPO 신경망 (Agent, HierarchicalAgent)
├── random_agent.py   ← 순수 랜덤 (참고용)
└── ADDING_AGENTS.md  ← 이 파일

backend/app/services/
└── agent_registry.py ← bot_type → AgentWrapper 매핑 테이블
```

---

## 추가 절차 (3단계)

### Step 1 — `wrappers.py`에 Wrapper 클래스 작성

`AgentWrapper`를 상속해 `act()` 메서드 하나만 구현합니다.

```python
# PuCo_RL/agents/wrappers.py

class MyAlgoWrapper(AgentWrapper):
    """내 알고리즘 래퍼."""

    def __init__(self, model_path: str | None, obs_dim: int):
        # 1. 신경망 인스턴스 생성
        self._agent = MyAlgoNet(obs_dim=obs_dim, action_dim=200)
        self._agent.eval()
        # 2. 가중치 로드 (없으면 무작위 초기화)
        if model_path:
            _load_weights(self._agent, model_path)

    def act(self, obs: torch.Tensor, mask: torch.Tensor, phase_id: int = 9) -> int:
        """
        Args:
            obs      : (1, obs_dim)  — 현재 관측값 (평탄화된 벡터)
            mask     : (1, 200)      — 유효 행동 마스크 (1=유효, 0=금지)
            phase_id : int           — 현재 게임 페이즈 (Phase IntEnum 0–8, 9=폴백)
        Returns:
            int — 선택된 행동 인덱스 (0–199)
        """
        with torch.no_grad():
            action, *_ = self._agent.get_action_and_value(obs, mask)
        return int(action.item())
```

**phase_id가 필요한 계층형 모델 (HPPO 등):**

```python
    def act(self, obs, mask, phase_id=9) -> int:
        phase_tensor = torch.tensor([phase_id], dtype=torch.long)
        with torch.no_grad():
            action, *_ = self._agent.get_action_and_value(obs, mask, phase_tensor)
        return int(action.item())
```

**가중치가 필요 없는 알고리즘 (MCTS, 휴리스틱 등):**

```python
    def __init__(self, model_path=None, obs_dim=0):
        pass  # 모델 없음

    def act(self, obs, mask, phase_id=9) -> int:
        valid = (mask.squeeze(0) > 0.5).nonzero(as_tuple=True)[0]
        return int(valid[torch.randint(len(valid), (1,))].item())
```

---

### Step 2 — `agent_registry.py`에 한 줄 등록

```python
# backend/app/services/agent_registry.py

AGENT_REGISTRY: dict[str, dict] = {
    "ppo":    {...},   # 기존
    "hppo":   {...},   # 기존
    "random": {...},   # 기존

    # ↓ 추가 — 이 한 블록만 넣으면 됩니다
    "my_algo": {
        "name": "My Algo Bot",                      # UI에 표시될 이름
        "wrapper_cls": MyAlgoWrapper,               # Step 1에서 만든 클래스
        "model_env_key": "MY_ALGO_MODEL_FILENAME",  # .env 키 (없으면 None)
        "model_default": "my_algo_v1.pth",          # 기본 파일명 (없으면 None)
    },
}
```

파일 상단 import도 추가:

```python
from agents.wrappers import HPPOWrapper, MyAlgoWrapper, PPOWrapper, RandomWrapper
```

---

### Step 3 — `.env`에 모델 파일명 추가 (가중치 있을 경우)

```
# castone/.env
MY_ALGO_MODEL_FILENAME=my_algo_v1.pth
```

가중치 파일은 `PuCo_RL/models/` 디렉터리에 놓습니다.

---

## 등록 후 반영

```bash
docker restart puco_backend
```

이후 프론트엔드 새 게임 화면에서 **"My Algo Bot"** 항목이 자동으로 나타납니다.

`BotService` / `legacy.py` 수정은 **불필요**합니다.

---

## Phase IntEnum 참조

| 값 | 이름 | 설명 |
|----|------|------|
| 0 | `SETTLER`       | 정착민 페이즈 |
| 1 | `MAYOR`         | 시장 페이즈 |
| 2 | `BUILDER`       | 건설자 페이즈 |
| 3 | `CRAFTSMAN`     | 장인 페이즈 |
| 4 | `TRADER`        | 상인 페이즈 |
| 5 | `CAPTAIN`       | 선장 페이즈 |
| 6 | `CAPTAIN_STORE` | 선장 창고 페이즈 |
| 7 | `PROSPECTOR`    | 탐사가 페이즈 |
| 8 | `END_ROUND`     | 라운드 종료 |
| 9 | _(폴백)_        | 페이즈 미확인 시 기본값 |

---

## obs / mask 형태

| 인자 | dtype | shape | 설명 |
|------|-------|-------|------|
| `obs`  | `float32` | `(1, obs_dim)` | 게임 상태 벡터 (약 400–600차원) |
| `mask` | `float32` | `(1, 200)`     | 유효 행동 마스크 (1.0=허용, 0.0=금지) |

> `obs_dim`은 환경마다 다를 수 있으므로 하드코딩 금지.
> `AgentWrapper.__init__(self, model_path, obs_dim)`의 `obs_dim` 인자를 그대로 사용하세요.

---

## 현재 등록된 에이전트

| `bot_type` | 클래스 | 특징 |
|------------|--------|------|
| `ppo`      | `PPOWrapper`    | 표준 PPO, `phase_id` 무시 |
| `hppo`     | `HPPOWrapper`   | 계층형 PPO, 페이즈별 Actor Head |
| `random`   | `RandomWrapper` | 랜덤 선택, 가중치 불필요 |
