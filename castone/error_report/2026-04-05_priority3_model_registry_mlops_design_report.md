# Priority 3 Model Registry / MLOps Detailed Design Report

작성일: 2026-04-05

기준 문서:
- `TODO.md`
- `PuCo_RL/train/train_ppo_selfplay_server.py`
- `PuCo_RL/env/pr_env.py`
- `backend/app/services/agent_registry.py`
- `backend/app/services/agents/factory.py`
- `backend/app/services/bot_service.py`
- `backend/app/services/game_service.py`
- `backend/app/services/ml_logger.py`
- `backend/app/db/models.py`
- `PuCo_RL/logs/replay/replay_seed42_1775006136.json`

## 0. 요약 결론

이번 설계의 단기 목표는 `PPO_PR_Server_~.pth` 계열을 실제 게임에서 안정적으로 사용할 수 있게 등록 구조를 만드는 것이다.

다만 구현 방식은 단순한 `env var + 파일명 하드코딩`이 아니라, 이후 `candidate / benchmark / canary`로 확장 가능한 `registry + policy tag` 구조를 전제로 잡는다.

핵심 결정은 아래와 같다.

1. 사용자와 API가 선택하는 bot label은 당분간 계속 `ppo`로 유지한다.
2. 내부에서는 `bot_type=ppo -> family=ppo + policy_tag=champion` 으로 해석한다.
3. 현재는 `PPO_PR_Server_~.pth`만 sidecar JSON 없이 bootstrap 등록을 허용한다.
4. bootstrap 등록된 모델은 `metadata_source=bootstrap_derived` 로 명시해 일반 sidecar 등록과 구분한다.
5. 다음 모델부터는 `.pth`와 같은 basename의 `.json` 메타데이터를 반드시 같이 받는다.
6. PostgreSQL은 운영용 조회와 감사 추적의 원본이고, `data/logs/*.jsonl`은 고용량 transition 수집용 원본이다.
7. replay JSON은 원본이 아니라 파생 산출물이다.
8. Redis는 pub/sub, connection 상태, short-lived state cache 용도만 유지하고 로그 원본이 되지 않는다.

## 1. 현재 구조 진단

### 1-1. 모델 서빙 구조

현재 [agent_registry.py](../backend/app/services/agent_registry.py) 는 정적 registry를 사용한다.

- `ppo`, `hppo`, `random` 이 코드에 고정되어 있다.
- `ppo`는 기본적으로 `ppo_agent_update_100.pth` 를 가리킨다.
- 실제 선택 기준은 `bot_type -> wrapper_cls + env var model filename` 이다.

현재 [factory.py](../backend/app/services/agents/factory.py) 의 동작은 아래와 같다.

- `model_path` 옆의 `.json`이 있으면 읽는다.
- `.json`이 없으면 `legacy_ppo` 로 가정한다.
- `architecture == "ppo"` 인 경우에도 내부 구현은 `hidden_dim=512` 고정에 가깝고, architecture-specific config를 풍부하게 받지 못한다.

이 구조는 모델 수가 적을 때는 괜찮지만, 앞으로 잠재함수 변경과 self-play 변형으로 모델이 많이 생기면 아래 문제가 생긴다.

- 어떤 `.pth`가 어떤 환경/관측 스키마/잠재함수에서 학습됐는지 추적이 어렵다.
- `.json`이 없는 순간 `legacy_ppo` 추정 로딩으로 빠질 수 있다.
- champion 교체, 롤백, 비교 실험, canary 라우팅을 코드 수정 없이 하기 어렵다.

### 1-2. 현재 self-play PPO 산출물의 특성

[train_ppo_selfplay_server.py](../PuCo_RL/train/train_ppo_selfplay_server.py) 를 보면 현재 최신 PPO 학습 모델은 아래 특성을 가진다.

- 파일명 prefix: `PPO_PR_Server`
- 학습 스크립트: `PuCo_RL/train/train_ppo_selfplay_server.py`
- 환경: `PuCo_RL/env/pr_env.py`
- `NUM_PLAYERS = 3`
- rollout env: `PuertoRicoEnv(num_players=3, max_game_steps=1200)`
- policy architecture: `agents.ppo_agent.Agent`
- 기본 network: `hidden_dim=512`, `num_res_blocks=3`
- action dim: `200`
- save format: `torch.save(agent.state_dict(), ...)`
- sidecar JSON 저장 없음

[pr_env.py](../PuCo_RL/env/pr_env.py) 기준으로 현재 환경 정보는 아래와 같다.

- action space: `Discrete(200)`
- 기본 potential mode: `option3`
- shaping gamma: `0.99`
- 기본 reward weights: `w_ship=1.0`, `w_bldg=1.0`, `w_doub=1.0`

중요한 점은 현재 코드로 실제 flattened observation dimension을 계산하면 `211` 이 나온다는 것이다.

- 확인 기준: `PuertoRicoEnv(num_players=3)` + `get_flattened_obs_dim(...)`
- 결과: `obs_dim = 211`, `action_dim = 200`

그런데 현재 repo에 있는 예시 sidecar [ppo_agent_update_100.json](../PuCo_RL/models/ppo_agent_update_100.json) 은 `obs_dim = 210` 이다.

이 차이는 매우 중요하다.

- 현재 예시 JSON은 legacy PPO용이고 최신 self-play PPO와 동일 계약이 아니다.
- "파일명만 보고 대충 로드" 하는 방식은 관측 스키마 drift를 숨긴다.
- 따라서 최신 self-play PPO 계열은 별도 metadata contract가 필요하다.

### 1-3. 현재 로그 저장 구조

현재 서비스는 이미 세 종류의 로그를 동시에 가지고 있다.

1. PostgreSQL `game_logs`
2. 로컬 JSONL `data/logs/transitions_YYYY-MM-DD.jsonl`
3. offline replay JSON `PuCo_RL/logs/replay/*.json`

현재 [game_service.py](../backend/app/services/game_service.py) 를 보면 한 액션 처리 시:

- `GameLog` row가 DB에 저장된다.
- `MLLogger.log_transition()` 이 JSONL row를 추가한다.
- Redis에는 최신 state cache와 pub/sub 메시지만 보낸다.

현재 [models.py](../backend/app/db/models.py) 의 `GameLog` 는 아래 필드를 가진다.

- `game_id`
- `round`
- `step`
- `actor_id`
- `action_data`
- `available_options`
- `state_before`
- `state_after`
- `state_summary`

현재 [ml_logger.py](../backend/app/services/ml_logger.py) 의 transition JSONL 은 아래 필드를 가진다.

- `timestamp`
- `game_id`
- `actor_id`
- `state_before`
- `action`
- `reward`
- `done`
- `state_after`
- `info`
- optional: `action_mask_before`
- optional: `phase_id_before`
- optional: `current_player_idx_before`

현재 replay JSON 예시 [replay_seed42_1775006136.json](../PuCo_RL/logs/replay/replay_seed42_1775006136.json) 은 아래 성격을 가진다.

- 사람 읽기 좋은 설명이 붙어 있다.
- `top_actions`, `value_estimate`, `commentary`, `role_selected` 같은 분석 필드가 있다.
- 현재 서비스 런타임 로그보다 더 풍부한 해설용 포맷이다.

즉 현재 저장 구조는 다음과 같이 나뉜다.

- DB `GameLog`: 운영 조회와 step-by-step audit에 적합
- JSONL transition: 학습/분석용 raw transition 수집
- replay JSON: 분석/시각화용 파생 artifact

## 2. 이번 설계의 목표와 비목표

### 목표

- `PPO_PR_Server_~.pth` 를 실제 게임에서 안전하게 champion bot으로 붙일 수 있게 한다.
- 다음 모델부터는 `.json` sidecar를 강제하는 intake contract를 만든다.
- `ppo` 라는 사용자-facing bot label은 유지하되 내부는 registry 기반으로 바꾼다.
- 모델 provenance가 게임 로그와 연결되도록 한다.
- Priority 3의 로그 구조를 `운영 로그`, `ML transition`, `replay export` 로 분리 설계한다.
- 향후 `candidate / benchmark / canary` 실험 흐름으로 확장하기 쉬운 구조를 만든다.
- TDD로 drift를 먼저 고정하고 이후 구현한다.

### 비목표

- 이번 단계에서 학습 파이프라인 자체를 이 repo 안에 완전 통합하지 않는다.
- 이번 단계에서 모든 과거 `.pth` 모델을 자동 일반화하지 않는다.
- 이번 단계에서 실험 라우팅 UI를 바로 노출하지 않는다.
- 이번 단계에서 object storage나 feature store를 도입하지 않는다.

## 3. 핵심 설계 원칙

1. `bot label` 과 `실제 서빙 아티팩트` 를 분리한다.
2. `.pth` 는 불충분한 artifact이며, 장기적으로는 `.json` sidecar가 표준이다.
3. sidecar 없는 bootstrap 허용은 예외 정책이며 영구 기본 정책이 아니다.
4. 게임 로그와 ML transition 로그는 서로 연결되지만 저장 목적이 다르므로 분리한다.
5. Redis는 절대 로그 원본이 아니다.
6. replay는 원본 저장이 아니라 export 결과물이다.
7. 실험 확장은 `version 직접 노출` 보다 `policy tag` 레이어가 더 안전하다.
8. 테스트는 "지금 실제 저장되는 구조" 를 먼저 고정한 뒤 schema/registry를 확장한다.

## 4. 목표 아키텍처

### 4-1. 용어 정의

- `family`: 알고리즘 계열. 예: `ppo`, `hppo`, `random`
- `artifact`: 실제 가중치 파일과 그 메타데이터를 묶은 단위
- `policy_tag`: `champion`, `candidate`, `benchmark`, `canary` 같은 라우팅 별칭
- `registry alias`: `family + policy_tag -> artifact` 매핑
- `metadata_source`: `sidecar`, `bootstrap_derived`, `legacy_flat_json`
- `validation_status`: `pending`, `passed`, `failed`, `revoked`

### 4-2. 단기 서빙 해석 규칙

초기 운영에서는 아래처럼 해석한다.

- 사용자/API 입력: `ppo`
- 내부 해석: `family=ppo`, `policy_tag=champion`
- registry resolve 결과: 현재 승인된 `PPO_PR_Server_~.pth`
- 실제 wrapper: PPO residual wrapper

즉 지금은 겉으로는 `ppo` 하나만 보여도 내부적으로는 이미 `champion alias` 를 쓰는 구조가 된다.

### 4-3. 장기 확장 규칙

향후 실험형으로 갈 때는 UI/API를 아래처럼 자연스럽게 열 수 있다.

- `ppo` -> default champion
- `ppo:candidate`
- `ppo:benchmark`
- 특정 내부 API에서만 `family + policy_tag` 지정

이 구조의 장점은 지금 API를 거의 바꾸지 않고도 나중에 실험 라우팅이 가능하다는 점이다.

## 5. 모델 등록 구조 설계

### 5-1. Bootstrap 허용 범위

이번 단계에서 sidecar JSON 없이 등록을 허용하는 모델은 아래 규칙에 한정한다.

- 파일명 정규식: `^PPO_PR_Server_.*\\.pth$`
- source profile: `train_ppo_selfplay_server.py`
- env profile: `pr_env.py`
- family: `ppo`
- architecture: `ppo_residual`

이 bootstrap 규칙은 예외 정책이다.

등록 시 시스템은 아래를 수행해야 한다.

1. 파일명이 allowlist pattern과 맞는지 검증
2. 현재 bootstrap profile에서 파생 가능한 metadata를 생성
3. registry에 `metadata_source=bootstrap_derived` 로 저장
4. local/container serving smoke validation 통과 후에만 `champion` 으로 승격 허용

allowlist 밖의 `.pth` 는 sidecar가 없으면 등록 거부가 맞다.

### 5-2. Bootstrap 파생 메타데이터

현재 코드 기준 bootstrap metadata 초안은 아래 값으로 파생 가능하다.

- `family = "ppo"`
- `architecture = "ppo_residual"`
- `training_script = "PuCo_RL/train/train_ppo_selfplay_server.py"`
- `env_module = "PuCo_RL/env/pr_env.py"`
- `num_players = 3`
- `obs_dim = 211`
- `action_dim = 200`
- `network.hidden_dim = 512`
- `network.num_res_blocks = 3`
- `environment.max_game_steps = 1200`
- `reward.potential_mode = "option3"`
- `reward.shaping_gamma = 0.99`
- `reward.weights.ship = 1.0`
- `reward.weights.building = 1.0`
- `reward.weights.doubloon = 1.0`
- `training.self_play = true`

이 값들은 현재 코드 기준으로 추론 가능하지만, 장기적으로는 학습 시점의 진실 소스가 아니다.

그래서 bootstrap record는 반드시 아래 플래그를 가진다.

- `metadata_source = "bootstrap_derived"`
- `bootstrap_profile = "ppo_pr_server_v1"`
- `requires_sidecar_for_next_versions = true`

## 6. Sidecar JSON 표준

### 6-1. 왜 JSON이 필요한가

팀원에게 `.json` sidecar를 요청해야 하는 이유는 아래와 같다.

1. `.pth` 파일만으로는 어떤 환경/관측 스키마/잠재함수에서 학습됐는지 안정적으로 알 수 없다.
2. 현재처럼 `.json`이 없으면 `legacy_ppo` 로 추정하는 fallback은 최신 self-play PPO에 위험하다.
3. `obs_dim`, `num_players`, `potential_mode` 가 바뀌었을 때 drift를 바로 감지할 수 있어야 한다.
4. 실험이 많아질수록 `이 모델이 정확히 어떤 버전인가` 를 로그와 연결해야 한다.
5. 롤백과 champion 교체를 하려면 provenance가 필요하다.

### 6-2. Sidecar 필수 요구사항

다음 모델부터는 `.pth` 와 같은 basename의 `.json` 파일을 같이 받는다.

예:

- `PPO_PR_Server_20260405_120000_step_99942400.pth`
- `PPO_PR_Server_20260405_120000_step_99942400.json`

### 6-3. 권장 JSON v1 포맷

```json
{
  "schema_version": "model-metadata.v1",
  "artifact_name": "PPO_PR_Server_20260405_120000_step_99942400",
  "family": "ppo",
  "architecture": "ppo_residual",
  "training_script": "PuCo_RL/train/train_ppo_selfplay_server.py",
  "env_module": "PuCo_RL/env/pr_env.py",
  "obs_dim": 211,
  "action_dim": 200,
  "num_players": 3,
  "network": {
    "hidden_dim": 512,
    "num_res_blocks": 3
  },
  "environment": {
    "max_game_steps": 1200
  },
  "reward": {
    "potential_mode": "option3",
    "shaping_gamma": 0.99,
    "weights": {
      "ship": 1.0,
      "building": 1.0,
      "doubloon": 1.0
    }
  },
  "training": {
    "self_play": true,
    "snapshot_step": 99942400,
    "total_timesteps": 100000000
  },
  "provenance": {
    "run_name": "PPO_PR_Server_20260405_120000",
    "created_at": "2026-04-05T12:00:00Z",
    "git_commit": "abcdef1234567890"
  },
  "notes": "Potential function option3 baseline"
}
```

### 6-4. 필수 필드와 이유

아래 필드는 실제 운영 기준으로 필수다.

| 필드 | 이유 |
| --- | --- |
| `schema_version` | parser 버전 호환성을 위해 필요 |
| `artifact_name` | registry와 로그에서 사람이 읽는 식별자 |
| `family` | `ppo`, `hppo` 등 서빙 계열 구분 |
| `architecture` | 어떤 wrapper/model class로 로드할지 결정 |
| `training_script` | 어떤 학습 코드에서 나왔는지 추적 |
| `env_module` | 환경 계약 추적 |
| `obs_dim` | 관측 차원 mismatch 차단 |
| `action_dim` | action head shape mismatch 차단 |
| `num_players` | 환경 구성 drift 차단 |
| `network.hidden_dim` | checkpoint shape 검증 |
| `network.num_res_blocks` | architecture drift 검증 |
| `environment.max_game_steps` | truncation semantics 추적 |
| `reward.potential_mode` | 잠재함수 버전 추적 |
| `reward.shaping_gamma` | shaped reward 해석 일관성 유지 |

### 6-5. 있으면 좋은 필드

아래 필드는 sidecar에 있으면 좋지만, 없으면 registry가 일부 보완할 수 있다.

| 필드 | 설명 |
| --- | --- |
| `reward.weights.*` | shaping 세부 가중치 추적 |
| `training.self_play` | self-play vs 일반 학습 구분 |
| `training.snapshot_step` | checkpoint 단계 추적 |
| `training.total_timesteps` | 전체 학습 budget 추적 |
| `provenance.run_name` | TensorBoard / 학습 폴더 연결 |
| `provenance.created_at` | 학습 산출 시각 |
| `provenance.git_commit` | 정확한 코드 버전 |
| `notes` | 실험 메모 |

### 6-6. sidecar에 없어도 registry가 계산 가능한 필드

아래 필드는 sidecar에 없어도 intake 시 로컬에서 계산 가능하다.

- `checkpoint_filename`
- `artifact_sha256`
- `file_size_bytes`
- `registered_at`
- `registered_by`

즉 팀원에게는 "운영적으로 의미 있는 학습 계약" 을 sidecar로 달라고 하고, 파일 해시 같은 건 이 repo가 intake 시 계산하면 된다.

### 6-7. 파서 호환성 정책

향후 [factory.py](../backend/app/services/agents/factory.py) 는 아래 세 형식을 모두 읽을 수 있게 설계하는 것이 좋다.

1. 기존 flat legacy JSON
2. 신규 nested `model-metadata.v1`
3. sidecar 없음 + bootstrap allowlist 모델

우선순위는 아래와 같다.

1. sidecar JSON
2. bootstrap profile
3. 그 외는 등록 실패

## 7. Registry 저장 스키마 제안

### 7-1. 새 테이블: `model_artifacts`

`model_artifacts` 는 실제 서빙 가능한 artifact registry의 원본이다.

권장 컬럼:

- `id` UUID PK
- `family` string
- `architecture` string
- `artifact_name` string unique
- `checkpoint_filename` string
- `checkpoint_path` string
- `artifact_sha256` string
- `file_size_bytes` bigint
- `metadata_json` JSONB
- `metadata_source` string
- `bootstrap_profile` string nullable
- `validation_status` string
- `validation_error` text nullable
- `created_at` timestamptz
- `registered_at` timestamptz
- `registered_by` string nullable
- `is_active` boolean

### 7-2. 새 테이블: `model_registry_aliases`

`family + policy_tag -> artifact` 매핑 테이블이다.

권장 컬럼:

- `id` UUID PK
- `family` string
- `policy_tag` string
- `artifact_id` FK -> `model_artifacts.id`
- `status` string
- `activated_at` timestamptz
- `deactivated_at` timestamptz nullable
- `notes` text nullable

예:

- `ppo + champion -> PPO_PR_Server_20260401_214532_step_99942400`
- 나중에 `ppo + candidate -> another artifact`

### 7-3. 새 테이블: `model_validation_runs`

artifact 등록 직후 수행한 smoke validation 결과를 남긴다.

권장 컬럼:

- `id` UUID PK
- `artifact_id` FK
- `validation_type` string
- `status` string
- `result_json` JSONB
- `created_at` timestamptz

validation type 예:

- `load_checkpoint`
- `dummy_inference`
- `docker_bot_game_smoke`

## 8. 실제 서빙 경로 설계

### 8-1. Bot selection

현재 사용자-facing 선택지는 유지한다.

- API 입력: `ppo`
- registry resolution: `family=ppo`, `policy_tag=champion`
- artifact load: champion alias가 가리키는 `model_artifacts` row

### 8-2. Wrapper cache key

현재 `get_wrapper(bot_type, obs_dim)` 캐시는 `bot_type` 수준이다.

registry 도입 후에는 cache key를 아래처럼 바꾸는 것이 안전하다.

- `artifact_id`
- 또는 `artifact_sha256`

이유:

- `ppo champion` 이 교체되면 같은 `bot_type=ppo` 라도 실제 가중치가 바뀐다.
- cache가 `bot_type` 만 보면 stale wrapper를 재사용할 수 있다.

### 8-3. `GameSession.model_versions` 활용

현재 [models.py](../backend/app/db/models.py) 에 이미 `GameSession.model_versions` JSONB가 있다.

이 컬럼은 registry snapshot을 denormalized 형태로 저장하는 용도로 유지하는 것이 좋다.

권장 저장 예시는 아래와 같다.

```json
{
  "player_0": {
    "bot_type": "ppo",
    "family": "ppo",
    "policy_tag": "champion",
    "artifact_id": "uuid-1",
    "artifact_name": "PPO_PR_Server_20260401_214532_step_99942400",
    "checkpoint_filename": "PPO_PR_Server_20260401_214532_step_99942400.pth",
    "metadata_source": "bootstrap_derived",
    "architecture": "ppo_residual"
  },
  "player_1": {
    "bot_type": "random",
    "family": "random",
    "policy_tag": "champion",
    "artifact_id": null,
    "artifact_name": "random"
  }
}
```

이 정보는 매우 중요하다.

- 한 판이 어떤 champion/candidate 버전으로 실행됐는지 고정할 수 있다.
- 이후 champion alias가 바뀌어도 과거 게임은 재현 가능하다.
- `GameLog` 나 transition JSONL 과 연결할 기준이 된다.

## 9. Priority 3 로그 저장 구조 설계

### 9-1. Source of truth 결정

권장 원본 계층은 아래와 같다.

1. PostgreSQL: 운영 조회와 감사 추적의 원본
2. JSONL transition: 고용량 ML 학습/분석 원본
3. replay JSON: 파생 산출물

의미는 아래와 같다.

- DB는 "운영자가 확인하고 질의하는" 원본이다.
- JSONL은 "모델 학습/분석 파이프라인이 소비하는" 원본이다.
- replay는 필요 시 export하는 사람 친화적 보기다.

### 9-2. `game_logs` 의 역할

`game_logs` 는 row-per-action 운영 audit log 로 유지한다.

추가를 권장하는 필드:

- `phase_id`
- `current_player_idx`
- `bot_type`
- `policy_tag`
- `artifact_id`
- `artifact_name`
- `action_valid` boolean
- `action_mask_digest` optional

이렇게 하면 Adminer/SQL 기준으로 아래 질문에 답할 수 있다.

- 어느 step에서 어떤 모델이 움직였는가
- 그때 phase와 current player가 무엇이었는가
- invalid output/retry가 있었는가

### 9-3. `games` 또는 최종 summary

최종 게임 결과는 `games` row에 요약 저장하는 편이 실용적이다.

권장 필드:

- `started_at`
- `finished_at`
- `end_reason`
- `final_scores` JSONB
- `winner_snapshot` JSONB optional
- `replay_export_status`

이렇게 하면 "한 판 요약" 과 "step log" 의 역할이 분리된다.

### 9-4. transition JSONL 의 역할

`MLLogger` 는 raw transition 수집기로 유지하되 provenance를 강화해야 한다.

추가 권장 필드:

- `bot_type`
- `policy_tag`
- `artifact_id`
- `artifact_name`
- `metadata_source`
- `obs_schema_version`
- `reward_profile`
- `selected_action_valid`

이 필드가 있으면 MLOps 관점에서 아래를 증명할 수 있다.

- 어떤 모델이 어떤 입력을 보고 어떤 행동을 냈는가
- 그 행동이 현재 action mask 기준 유효했는가
- 어떤 reward profile을 가진 데이터인지

### 9-5. replay export 원칙

replay JSON은 서비스 원본 저장이 아니라 export artifact로 두는 것이 좋다.

이유:

- 현재 replay 포맷은 `top_actions`, `value_estimate`, `commentary` 등 분석용 필드가 많다.
- 모든 게임 step마다 이 수준의 human-readable payload를 DB 원본으로 바로 저장하면 비용이 커진다.
- 대신 DB step log + transition trace를 기반으로 필요 시 export하면 된다.

### 9-6. replay 품질을 위한 future hook

향후 PPO 계열 wrapper는 단순 `action int` 반환 대신 `DecisionTrace` 반환으로 확장하는 것이 좋다.

예:

- `selected_action`
- `value_estimate`
- `top_k_actions`
- `masked_logits_checksum`

이 확장이 들어가면 replay export의 품질이 크게 올라간다.

## 10. Redis 역할 정의

Redis의 권장 책임 경계는 아래와 같다.

- `game:{id}:state`: 최신 state cache
- `game:{id}:events`: WS pub/sub
- `game:{id}:players`: 연결 상태
- `game:{id}:meta`: disconnect/timeout용 메타

Redis가 하지 말아야 하는 일:

- 영구 로그 저장
- replay 원본 저장
- model registry 원본 저장

즉 Priority 3-D 결론은 아래 한 줄로 정리된다.

> Redis는 전달과 임시 상태를 담당하고, 운영/학습 로그의 원본은 PostgreSQL과 JSONL이다.

## 11. TDD 설계

### 11-1. 먼저 고정할 현재 상태 테스트

1. `GameLog` 에 현재 어떤 필드가 저장되는지 characterization test 추가
2. `MLLogger` JSONL 에 현재 어떤 필드가 남는지 characterization test 추가
3. replay JSON 예시와 서비스 로그가 왜 다른지 schema diff fixture 추가

이 단계는 "지금 구조를 설명 가능한 상태로 고정" 하는 것이다.

### 11-2. Registry / metadata 테스트

권장 테스트 파일:

- `backend/tests/test_model_registry_bootstrap_intake.py`
- `backend/tests/test_model_sidecar_schema.py`
- `backend/tests/test_model_alias_resolution.py`

핵심 red 테스트:

1. `PPO_PR_Server_~.pth` 는 sidecar 없이 bootstrap 등록 가능해야 한다.
2. bootstrap 등록 결과는 `metadata_source=bootstrap_derived` 여야 한다.
3. sidecar 없는 non-allowlist `.pth` 는 등록 거부되어야 한다.
4. sidecar JSON 필수 필드가 누락되면 등록 거부되어야 한다.
5. `ppo` alias는 `champion` artifact를 resolve 해야 한다.
6. champion 교체 후 wrapper cache는 새 artifact 기준으로 갱신되어야 한다.

### 11-3. Serving contract 테스트

권장 테스트 파일:

- `backend/tests/test_bot_serving_registry_contract.py`
- `backend/tests/test_game_model_snapshot_logging.py`

핵심 red 테스트:

1. `bot_type=ppo` 로 시작한 방은 `champion` artifact snapshot을 `GameSession.model_versions` 에 저장해야 한다.
2. 한 판 시작 후 champion alias가 바뀌어도 진행 중 게임은 기존 snapshot artifact를 계속 사용해야 한다.
3. `GameLog` row는 actor, phase, current player, artifact provenance를 함께 남겨야 한다.
4. transition JSONL 도 같은 artifact provenance를 남겨야 한다.

### 11-4. Priority 3 로그 테스트

권장 테스트 파일:

- `backend/tests/test_priority3_log_contract.py`
- `backend/tests/test_replay_export_contract.py`

핵심 red 테스트:

1. 한 액션 후 `game_logs` row가 정확히 1개 늘어야 한다.
2. 같은 액션에 대해 transition JSONL 도 정확히 1 row 기록되어야 한다.
3. DB `GameLog.step` 와 transition `info.step` 이 같은 step를 가리켜야 한다.
4. `artifact_id`, `artifact_name`, `policy_tag` 가 DB와 JSONL 모두에 남아야 한다.
5. replay export는 DB row + transition trace만으로 재생 가능해야 한다.

### 11-5. PostgreSQL 확인 절차 테스트/문서

Priority 3-C 용으로 아래를 문서화하고 필요하면 smoke query test로 만든다.

- 특정 game_id 의 step log 조회
- 특정 artifact_name 으로 실행된 게임 조회
- 특정 player slot 의 model snapshot 확인
- state_summary 기반 최종 점수/자원 추적 확인

### 11-6. Redis 책임 경계 테스트

핵심 red 테스트:

1. Redis publish 성공 시 direct broadcast fallback을 타지 않아야 한다.
2. Redis 장애가 나도 DB `GameLog` 와 JSONL transition 기록은 남아야 한다.
3. Redis 재시작 후에도 로그 원본은 유실되지 않아야 한다.

## 12. Docker / 시스템 검증 계획

설계 구현 후 실제 검증은 아래 순서가 좋다.

1. backend unit/integration test 실행
2. DB migration 적용
3. registry에 bootstrap artifact 등록
4. `ppo champion` alias 지정
5. docker compose 기동
6. bot-game 생성
7. 실제 플레이 진행
8. DB, JSONL, WS, replay export 경로 확인

구체 체크리스트:

- `/health` 가 정상인지
- `ppo` bot-game 생성 시 `GameSession.model_versions` 에 champion snapshot이 들어가는지
- `GameLog` 에 `artifact_name`, `phase_id`, `current_player_idx` 가 남는지
- transition JSONL 에도 동일 provenance가 남는지
- Redis 없이도 fallback으로 게임은 진행되지만 로그는 DB/JSONL 에 남는지
- replay export가 같은 artifact name을 출력하는지

## 13. 구현 순서 제안

권장 구현 순서는 아래와 같다.

1. `3-A 현재 저장 구조 characterization test`
2. `registry intake + bootstrap allowlist`
3. `sidecar JSON schema validator`
4. `ppo -> champion alias resolution`
5. `GameSession.model_versions snapshot 강화`
6. `GameLog / transition provenance 필드 확장`
7. `PostgreSQL 확인 절차 문서화`
8. `replay export contract`

이 순서가 좋은 이유는 아래와 같다.

- 먼저 현재 로그 계약을 고정해야 리팩터링 중 데이터 drift를 잡을 수 있다.
- 그 다음 artifact 등록/resolve 구조를 만들어야 서빙 경로를 안정적으로 바꿀 수 있다.
- provenance가 안정된 뒤에야 replay export 품질을 올릴 수 있다.

## 14. 팀원에게 요청할 sidecar 규칙

팀원에게는 아래 문장을 그대로 전달해도 된다.

> 다음 모델부터는 `.pth` 파일과 같은 basename의 `.json` 메타데이터 파일을 같이 주세요.  
> 최소한 `schema_version`, `artifact_name`, `family`, `architecture`, `training_script`, `env_module`, `obs_dim`, `action_dim`, `num_players`, `network.hidden_dim`, `network.num_res_blocks`, `environment.max_game_steps`, `reward.potential_mode`, `reward.shaping_gamma` 는 꼭 필요합니다.  
> 이유는 이 정보가 없으면 현재 서비스가 모델을 어떤 wrapper로 읽어야 하는지, 현재 환경과 관측 차원이 맞는지, 잠재함수 버전이 무엇인지 안전하게 검증할 수 없기 때문입니다.

## 15. 이번 단계의 최종 권고안

이번 단계에서 가장 현실적인 권고안은 아래와 같다.

1. 지금은 `PPO_PR_Server_~.pth` 만 bootstrap registry로 붙인다.
2. 사용자-facing bot 선택지는 계속 `ppo` 로 유지한다.
3. 내부는 이미 `ppo champion` 구조로 바꾼다.
4. 다음 모델부터는 sidecar JSON을 mandatory로 한다.
5. Priority 3 로그 구조는 `DB audit + JSONL transition + replay export` 삼분 구조로 고정한다.
6. Redis는 전달 계층으로만 남기고 로그 원본에서 제외한다.

이 구조면 지금 운영 복잡도를 과도하게 늘리지 않으면서도, 나중에 실험형 모델 운영으로 확장할 때 재설계를 최소화할 수 있다.
