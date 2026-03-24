# MLOps Assessment Report
## Puerto Rico AI Battle Platform

> **평가 기준:** MLOps Engineer · ML Pipeline Workflow · Kaizen · Brainstorming
> **평가 대상:** `PuCo_RL/` 학습 파이프라인 + `backend/app/services/` ML 서빙 레이어
> **작성일:** 2026-03-24

---

## 요약 (Executive Summary)

| 등급 | 건수 |
|------|------|
| 🔴 CRITICAL | 2 |
| 🟠 HIGH | 5 |
| 🟡 MEDIUM | 5 |
| 🔵 LOW | 4 |
| ✅ GOOD | 6 |

**전반적 평가:** 학습 코드 품질(PPO self-play, GAE, 클리핑)은 탄탄하지만, **학습 → 검증 → 배포의 전체 파이프라인**이 수동 작업에 의존하고 있습니다. 특히 학습 환경과 서빙 환경의 불일치가 모델 성능에 직접적인 영향을 줍니다.

---

## 현재 ML 파이프라인 (AS-IS)

```
[수동 학습]
train_ppo_selfplay.py
  │ max_game_steps=2000  ← 문제!
  │ TensorBoard → runs/  ← 로컬에만
  │ opponent_pool 메모리  ← 재시작 시 소실
  ▼
ppo_agent_update_N.pth  (수동 파일 관리)
  │
  │ 수동 복사 + .env 수정
  ▼
[서빙]
AgentRegistry (LRU 캐시)
  │ 서버 재시작 필요 (핫스왑 불가)
  ▼
BotService.get_action()
  │ PuertoRicoEnv() 매 호출마다 생성!  ← 문제!
  ▼
game_service.process_action()

[데이터 로깅]
MLLogger → /data/logs/*.jsonl    ← 이중 저장
GameService → PostgreSQL game_logs  ← 이중 저장

[재학습]
(없음 — 완전 수동)
```

---

## 🔴 CRITICAL

### C-01. 학습 환경과 서빙 환경의 max_game_steps 불일치

**파일:** `PuCo_RL/train_ppo_selfplay.py:43` vs `backend/app/engine_wrapper/wrapper.py:17`

```python
# 학습 시
def make_env():
    return PuertoRicoEnv(num_players=NUM_PLAYERS, max_game_steps=2000)  # 학습

# 서빙 시
class EngineWrapper:
    def __init__(self, num_players=3, max_game_steps=50000):              # 서빙!
```

**문제:**
- PPO/HPPO 모델은 2000스텝에서 truncation되는 환경에서 학습됨
- 실제 게임은 ~11,000스텝까지 진행 (자연 종료 조건)
- 학습된 policy가 경험하지 못한 후반부 게임 상태에서 추론해야 함
- reward 분포, value function 추정 모두 틀려짐 → **policy degradation**

**수정 방법:**
```python
# 학습과 서빙 동일하게 설정
MAX_GAME_STEPS = int(os.environ.get("MAX_GAME_STEPS", "50000"))

def make_env():
    return PuertoRicoEnv(num_players=NUM_PLAYERS, max_game_steps=MAX_GAME_STEPS)
```

**Kaizen 우선순위:** Phase 1 (즉시) — 재학습 필요

---

### C-02. MLLogger 로그 데이터가 실제 재학습에 사용 불가

**파일:** `backend/app/services/ml_logger.py`

```python
# MLLogger가 저장하는 형식
record = {
    "state_before": raw_dict_obs,   # ← 중첩 dict (flatten 안 됨)
    "action": action,
    "reward": reward,
    ...
}
```

```python
# train_ppo_selfplay.py가 사용하는 형식
flat_obs = flatten_dict_observation(obs_dict, obs_space)
obs_tensor = torch.Tensor(flat_obs).to(DEVICE).unsqueeze(0)
# ← 1차원 float 벡터가 필요
```

**문제:**
- `MLLogger`는 raw dict를 저장하지만 학습 스크립트는 flatten된 벡터 필요
- 두 형식 간 변환 파이프라인이 없음
- `/data/logs/*.jsonl` 파일이 쌓이지만 **실제로 재학습에 사용된 적이 없음**
- 데이터 수집이 학습에 연결되지 않는 Dead Code 파이프라인

**수정 방법:**
```python
# ml_logger.py에 flattened 형태로 저장 추가
from utils.env_wrappers import flatten_dict_observation

flat_obs_before = flatten_dict_observation(state_before, obs_space).tolist()
record["flat_obs_before"] = flat_obs_before  # 학습 준비 완료 형태 추가
```

또는 오프라인 변환 스크립트:
```python
# scripts/convert_logs_to_training_data.py
for record in jsonl_records:
    flat_obs = flatten_dict_observation(record["state_before"], obs_space)
    # → numpy array로 저장 (npy/npz)
```

---

## 🟠 HIGH

### H-01. 모델 레지스트리 없음 — 수동 파일 관리

**파일:** `PuCo_RL/models/`, `backend/app/services/agent_registry.py`

```
PuCo_RL/models/
├── ppo_agent_update_10.pth    ← 버전 관리 없음
├── ppo_agent_update_20.pth    ← 성능 지표 없음
├── ...
├── ppo_agent_update_100.pth   ← "최신"이 최고라는 보장 없음
└── HPPO_PR_Server_1774241514_step_14745600.pth  ← 타임스탬프가 버전
```

**문제:**
- 어떤 모델이 어떤 성능을 냈는지 알 수 없음
- 배포 기록 없음 → 롤백 불가
- `PPO_MODEL_FILENAME` 환경변수를 수동으로 바꿔야 배포됨
- 모델 학습 파라미터, 학습 데이터 정보가 `.pth` 파일에 없음

**수정 방법 (Kaizen Level 2):**
```python
# 모델 저장 시 메타데이터 같이 저장
torch.save({
    "model_state_dict": agent.state_dict(),
    "metadata": {
        "version": run_name,
        "timestamp": int(time.time()),
        "total_steps": global_step,
        "win_rate": float(win_rate),
        "avg_score": stats["avg_score"],
        "hyperparams": {
            "lr": LEARNING_RATE,
            "gamma": GAMMA,
            "max_game_steps": MAX_GAME_STEPS,
        }
    }
}, model_path)
```

---

### H-02. 모델 핫스왑 불가 — LRU 캐시로 잠김

**파일:** `backend/app/services/agent_registry.py:59`

```python
@functools.lru_cache(maxsize=None)
def get_wrapper(bot_type: str, obs_dim: int) -> AgentWrapper:
    """bot_type 별 AgentWrapper 싱글턴을 반환한다 (LRU 캐시로 1회만 생성)."""
    return cfg["wrapper_cls"](model_path=model_path, obs_dim=obs_dim)
```

**문제:**
- 새 모델 배포 시 **서버 재시작 필수**
- 롤백도 서버 재시작 필요
- 다운타임 없는 모델 교체 불가
- A/B 테스트, 카나리 배포 불가

**수정 방법:**
```python
# LRU 캐시 대신 재로드 가능한 레지스트리
class AgentRegistry:
    _instances: Dict[str, AgentWrapper] = {}
    _model_hashes: Dict[str, str] = {}

    @classmethod
    def get_wrapper(cls, bot_type: str, obs_dim: int) -> AgentWrapper:
        model_path = _resolve_model_path(AGENT_REGISTRY[bot_type])
        current_hash = _file_hash(model_path)  # MD5/SHA256

        if bot_type not in cls._instances or cls._model_hashes.get(bot_type) != current_hash:
            cls._instances[bot_type] = ...  # 재로드
            cls._model_hashes[bot_type] = current_hash

        return cls._instances[bot_type]
```

---

### H-03. BotService에서 매 추론마다 환경 인스턴스 생성

**파일:** `backend/app/services/bot_service.py:103-105`

```python
@staticmethod
def get_action(bot_type: str, game_context: Dict[str, Any]) -> int:
    obs_dim = BotService._get_obs_dim()
    wrapper = get_wrapper(bot_type, obs_dim)

    raw_obs = game_context["vector_obs"]
    action_mask = game_context["action_mask"]

    # ← 매 액션마다 더미 환경 생성 (obs_space 얻기 위해)
    dummy_env = PuertoRicoEnv(num_players=3)
    obs_space = dummy_env.observation_space("player_0")["observation"]
    flat_obs = flatten_dict_observation(raw_obs, obs_space)
```

**문제:**
- `PuertoRicoEnv()` 생성 비용 (게임 초기화) × 봇 액션 수 = **수만 번**
- 3인 봇 게임 (~11,000스텝) × 2/3 봇 = ~7,300번 환경 생성
- obs_space는 동일한 구조이므로 **한 번만 생성하면 됨**

**수정 방법:**
```python
# bot_service.py
_cached_obs_space = None

@classmethod
def _get_obs_space(cls):
    if cls._cached_obs_space is None:
        dummy = PuertoRicoEnv(num_players=3)
        dummy.reset()
        cls._cached_obs_space = dummy.observation_space("player_0")["observation"]
    return cls._cached_obs_space
```

---

### H-04. 실험 추적이 로컬 TensorBoard뿐

**파일:** `PuCo_RL/train_ppo_selfplay.py:249`

```python
run_name = f"PPO_PuertoRico_{NUM_PLAYERS}P_{int(time.time())}"
writer = SummaryWriter(f"runs/{run_name}")  # ← 로컬 파일에만
```

**문제:**
- 학습은 Docker 외부 또는 별도 머신에서 실행
- `runs/` 디렉토리가 공유되지 않으면 실험 이력 없음
- 여러 학습 실행 간 비교 불가
- 모델 선택 근거 없음 (어떤 checkpoint가 최고 성능인지 불명)
- HPPO 파일명이 `HPPO_PR_Server_1774241514_step_14745600.pth` — 타임스탬프 외 정보 없음

**수정 방법 (Kaizen Level 2):**
```python
# W&B 또는 MLflow 연동 (선택적 — 없으면 TensorBoard fallback)
try:
    import wandb
    wandb.init(project="puco-rl", name=run_name, config={...})
    USE_WANDB = True
except ImportError:
    USE_WANDB = False
```

---

### H-05. 학습-배포 파이프라인 완전 수동

현재 배포 절차:
```
1. train_ppo_selfplay.py 로컬 실행 (수시간)
2. 최고 성능 checkpoint 수동 선택
3. .pth 파일을 PuCo_RL/models/에 수동 복사
4. .env의 PPO_MODEL_FILENAME 수동 수정
5. docker compose restart (다운타임 발생)
```

**문제:**
- 재학습 주기 없음 (데이터가 쌓여도 자동 트리거 없음)
- 배포 승인 프로세스 없음
- 성능 검증 없이 배포 가능
- 롤백 절차 없음

---

## 🟡 MEDIUM

### M-01. 이중 데이터 저장 — 동기화 없음

**파일:** `game_service.py` + `ml_logger.py`

```python
# game_service.py → PostgreSQL
game_log = GameLog(state_before=..., state_after=..., ...)
self.db.add(game_log)

# ml_logger.py → /data/logs/*.jsonl (동시에)
await f.write(json.dumps(record) + "\n")
```

**문제:**
- 동일 데이터가 두 곳에 저장 (디스크 낭비)
- PostgreSQL이 단일 진실의 원천이어야 하는데 JSONL도 존재
- JSONL 실패 시 → PostgreSQL에는 있지만 훈련 데이터에는 없음
- JSONL은 회전(rotation) 없어 무한 성장

**수정 방법 (Kaizen):**
```python
# MLLogger 대신 PostgreSQL game_logs를 직접 사용
# 오프라인 학습 시 DB에서 export:
# SELECT game_id, actor_id, action_data, state_before, state_after
# FROM game_logs WHERE game_id IN (...)
# → .parquet 또는 .npy로 변환
```

---

### M-02. 학습 하이퍼파라미터 하드코딩

**파일:** `PuCo_RL/train_ppo_selfplay.py:19-38`

```python
LEARNING_RATE = 2.5e-4
NUM_STEPS = 500 if _TEST_MODE else 4096
GAMMA = 0.99
ENT_COEF = 0.01
# ... 모두 코드에 박힘
```

**문제:**
- 하이퍼파라미터 탐색 시 코드 수정 필요
- 실험 간 파라미터 추적 불가
- 재현성 보장 어려움

**수정 방법:**
```yaml
# configs/ppo_config.yaml
learning_rate: 2.5e-4
num_steps: 4096
gamma: 0.99
ent_coef: 0.01
max_game_steps: 50000  # ← 서빙과 동일하게
```

---

### M-03. Self-play Opponent Pool 영속성 없음

**파일:** `PuCo_RL/train_ppo_selfplay.py:268`

```python
opponent_pool = []  # 메모리에만 존재
# FIFO, maxsize=20
```

**문제:**
- 학습 중단/재시작 시 opponent pool 소실
- Checkpoint에서 재시작 시 pool이 비어 있어 다양성 손실
- 학습 이력이 끊김

**수정 방법:**
```python
# Checkpoint와 함께 opponent pool 저장
torch.save({
    "model_state_dict": agent.state_dict(),
    "opponent_pool": opponent_pool[-5:],  # 최근 5개만
    "global_step": global_step,
    "optimizer_state_dict": optimizer.state_dict(),
}, checkpoint_path)
```

---

### M-04. `strict=False` 가중치 로딩 — 조용한 실패

**파일:** `PuCo_RL/agents/wrappers.py:36`

```python
agent.load_state_dict(state, strict=False)
logger.info("가중치 로드 완료 (strict=False): %s", model_path)
```

**문제:**
- 모델 아키텍처 변경 시 일부 레이어가 무작위로 초기화됨
- 경고 없이 부분 로드 → 성능 저하를 디버깅하기 매우 어려움
- 어떤 레이어가 로드되고 어떤 레이어가 스킵됐는지 기록 없음

**수정 방법:**
```python
missing, unexpected = agent.load_state_dict(state, strict=False)
if missing:
    logger.warning("로드 누락 레이어 (%d개): %s", len(missing), missing[:5])
if unexpected:
    logger.warning("예상 외 레이어 (%d개): %s", len(unexpected), unexpected[:5])
```

---

### M-05. 데이터 품질 검증 없음

수집된 게임 로그에 대한 검증이 없습니다:

```python
# 현재: 검증 없이 저장
game_log = GameLog(
    state_before=result["state_before"],  # 정합성 검사 없음
    state_after=result["state_after"],
    ...
)
```

**필요한 검증:**
- `state_before[N+1]` == `state_after[N]` (연속성)
- action이 해당 시점의 mask에 유효했는지
- round/step이 단조증가하는지
- 게임 ID별 완전성 (중간에 끊긴 게임 제외)

---

## 🔵 LOW

### L-01. GPU 활용 없는 추론

```python
# wrappers.py: 항상 CPU
checkpoint = torch.load(model_path, map_location="cpu")

# bot_service.py
obs_tensor = torch.Tensor(flat_obs).unsqueeze(0)  # CPU tensor
```

3인 봇 게임 ~11,000스텝에서 전부 CPU 추론. GPU가 있다면 배치 추론으로 처리 가능.

---

### L-02. 학습/추론 간 obs_dim 하드코딩

```python
# wrappers.py
self._agent = Agent(obs_dim=obs_dim, action_dim=200)  # action_dim 하드코딩

# bot_service.py
dummy_env = PuertoRicoEnv(num_players=3)  # num_players 하드코딩
```

게임 규칙/관측 공간 변경 시 여러 파일을 동시에 수정해야 함.

---

### L-03. TensorBoard runs/ 디렉토리 관리 없음

```python
writer = SummaryWriter(f"runs/{run_name}")
```

`runs/` 디렉토리가 무한 증가. 오래된 실험 자동 삭제 없음.

---

### L-04. train_hppo_selfplay.py와 train_ppo_selfplay.py 중복

```
PuCo_RL/train_hppo_selfplay.py  ← HPPO 전용
PuCo_RL/train_ppo_selfplay.py   ← PPO 전용
```

공통 로직(collect_rollout, GAE, PPO update)이 중복될 가능성이 높음. 공통 학습 프레임워크로 통합 권장.

---

## ✅ 잘 구현된 MLOps 사항

| 항목 | 위치 | 설명 |
|------|------|------|
| Self-play Opponent Pool | `train_ppo_selfplay.py:268` | FIFO 20개, 80%최신/20%과거 다양성 유지 |
| GAE 구현 | `train_ppo_selfplay.py:163` | proper bootstrap, nextnonterminal 처리 |
| 클리핑 정책/가치 손실 | `train_ppo_selfplay.py:215` | PPO clipped 목적함수 정확하게 구현 |
| 선형 LR 감소 | `train_ppo_selfplay.py:292` | `frac = 1.0 - (update-1)/num_updates` |
| AgentWrapper 추상화 | `agents/base.py` | 새 알고리즘 추가 시 1파일만 수정 |
| lru_cache 싱글턴 | `agent_registry.py:59` | 모델 중복 로드 방지 |

---

## 목표 ML 파이프라인 (TO-BE)

```
[자동화된 학습 트리거]
PostgreSQL game_logs에 N개 누적 → Cron or 웹훅
  │
  ▼
[오프라인 데이터 준비]
scripts/export_training_data.py
  → game_logs → flat_obs numpy 변환
  → train/val split (game_id 기준)
  → 데이터 품질 검증
  │
  ▼
[학습]
train_ppo_selfplay.py
  config: configs/ppo_config.yaml (max_game_steps=50000 ← 서빙과 동일)
  실험 추적: TensorBoard + (선택) W&B
  Checkpoint: model + opponent_pool + optimizer + metadata
  │
  ▼
[자동 검증]
scripts/validate_model.py
  → 무작위 봇 대비 win_rate > 임계값?
  → 이전 모델 대비 성능 회귀 없음?
  │ 통과
  ▼
[배포]
PuCo_RL/models/best_model.pth  (심볼릭 링크)
AgentRegistry 파일 해시 감지 → 자동 재로드 (서버 재시작 없음)
  │
  ▼
[모니터링]
game_logs state_summary → 봇 승률, 평균 게임 길이, VP 추이 추적
```

---

## Kaizen 로드맵

```
즉시 (이번 주)
  ├── C-01: train_ppo_selfplay.py max_game_steps=50000 로 수정 + 재학습
  ├── C-02: MLLogger flat_obs 추가 저장 또는 JSONL 제거
  ├── H-03: BotService obs_space 캐싱 (성능)
  └── M-04: strict=False 경고 로깅 강화

이번 달
  ├── H-01: 모델 저장 시 메타데이터 포함
  ├── H-02: AgentRegistry 파일 해시 기반 핫스왑
  ├── M-01: MLLogger 제거 → PostgreSQL 단일 진실
  ├── M-02: configs/ppo_config.yaml 도입
  └── M-03: Checkpoint에 opponent_pool 포함

중기
  ├── H-04: W&B 또는 MLflow 실험 추적 연동
  ├── H-05: 자동 학습-검증-배포 파이프라인 스크립트
  ├── M-05: 데이터 품질 검증 파이프라인
  └── L-04: 공통 학습 프레임워크 통합
```

---

## BFRI 평가 (MLOps 수정 항목)

### C-01 환경 불일치 수정 (코드 1줄 + 재학습)
`BFRI = (5+5) - (1+3+1) = 5` → ⚠️ Moderate — 재학습 시간 비용 있음

### H-03 obs_space 캐싱 (성능 개선)
`BFRI = (5+5) - (1+1+1) = 7` → ✅ Safe — 즉시 적용 가능

### H-02 모델 핫스왑 (AgentRegistry 리팩터)
`BFRI = (4+4) - (2+1+2) = 3` → ⚠️ Moderate — 테스트 필요

---

## 추가 분석: 데이터 수집 가치 평가

```
현재 수집 현황:
  PostgreSQL game_logs: state_before, state_after, action, mask 저장 ← RL 학습에 충분
  MLLogger JSONL: 동일 데이터를 raw dict로 중복 저장 ← 학습 파이프라인 연결 없음

권장:
  1. JSONL 제거 (중복 제거)
  2. DB에서 직접 학습 데이터 export
  3. export 시 flatten 변환 + 품질 검증 적용
  4. game이 자연 종료된 경우만 사용 (truncated=True 제외)
```

---

*이 보고서는 코드 정적 분석 기반입니다. C-01(환경 불일치)이 모델 성능에 가장 큰 영향을 주는 문제로 즉시 재학습을 권장합니다.*
