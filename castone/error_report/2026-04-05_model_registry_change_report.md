# 2026-04-05 Model Registry Change Report

## 1. 왜 UI에서 확인이 어려운가

이번 변경의 핵심은 화면 레이아웃보다 `backend -> engine/model -> logging` 경로를 정리한 것입니다.  
즉 사용자가 바로 눈으로 보는 버튼/패널보다, 다음과 같은 내부 계약이 바뀌었습니다.

- `ppo` bot type이 더 이상 막연한 legacy checkpoint가 아니라 실제 champion artifact로 resolve됨
- `PPO_PR_Server_~.pth` 계열을 bootstrap metadata로 읽을 수 있게 됨
- 게임 시작 시 어떤 플레이어가 어떤 모델 버전으로 플레이하는지 `model_versions` snapshot이 생성됨
- DB GameLog와 transition JSONL에 `model_info`가 같이 기록됨
- 이후 UI, replay, 분석 스크립트가 같은 provenance를 따라갈 수 있게 됨

이 변화는 게임 화면에 큰 시각적 차이를 만들지 않기 때문에, 별도 보고서 없이 확인하기 어렵습니다.

---

## 2. 실제로 무엇을 바꿨는가

### 2-1. `ppo -> champion artifact` 해석 경로 추가

대상 파일:

- `backend/app/services/agent_registry.py`
- `backend/app/services/model_registry.py`
- `backend/app/services/agents/factory.py`

변경 내용:

- `ppo` 기본 모델을 `PPO_PR_Server_20260401_214532_step_99942400.pth` 로 해석하도록 고정
- `PPO_PR_Server_~.pth` 파일은 sidecar JSON이 없어도 bootstrap metadata를 유도해서 등록 가능하게 처리
- 다음 모델부터는 `.pth` 옆의 `.json` sidecar metadata를 우선 사용하도록 경로 마련
- wrapper 생성 전에 `architecture`, `obs_dim`, `action_dim` 검증을 추가

의미:

- 모델이 많아져도 `env var + 추측 로딩`이 아니라 provenance가 있는 아티팩트 기준으로 서빙 가능
- 잘못된 관측 차원/액션 차원의 체크포인트가 조용히 로드되는 위험 감소

### 2-2. 게임 시작 시 모델 provenance snapshot 저장

대상 파일:

- `backend/app/services/game_service.py`

변경 내용:

- 게임 시작 시 `room.model_versions` 를 생성
- 각 `player_n` 슬롯에 대해 human/bot 여부, bot type, artifact name, checkpoint filename, architecture, metadata source 등을 snapshot으로 저장
- rich state에도 `model_versions`를 포함시켜 이후 소비자(UI, replay, inspection)가 같은 정보를 참조 가능하게 함

의미:

- “이 게임에서 누가 어떤 모델로 플레이했는가?”를 게임 단위로 추적 가능
- 이후 canary/champion/benchmark tag 기반 실험형 구조로 확장하기 쉬움

### 2-3. DB 로그와 transition JSONL에 model provenance 추가

대상 파일:

- `backend/app/services/game_service.py`
- `backend/app/services/ml_logger.py`

변경 내용:

- `GameLog.action_data.model_info` 저장
- transition JSONL에 `model_info`, `action_mask_before`, `phase_id_before`, `current_player_idx_before` 기록

의미:

- MLOps 관점에서 “모델이 어떤 입력 마스크를 보고 어떤 액션을 냈는지”를 사후 분석 가능
- 이후 reward/potential function 변경 실험과 행동 차이를 비교할 때 provenance 연결점이 생김

---

## 3. 이번 구조가 장기적으로 중요한 이유

현재는 외부 학습 서버가 `.pth`를 만들고, 이 프로젝트는 실제 플레이/시각화/로그 확인에 집중합니다.  
이때 가장 위험한 구조는 “파일은 늘어나는데 어떤 모델인지 기록이 없다”는 상태입니다.

이번 변경으로 다음 운영 규칙을 만들 기반이 생겼습니다.

- 단기: `PPO_PR_Server_~.pth` bootstrap 허용
- 중기: 모든 신규 모델은 `.pth + same-basename .json` mandatory
- 장기: `family + policy_tag(champion/candidate/benchmark)` 기반 registry 운영

---

## 4. 검증 결과

### 프론트

- 관련 UI 변화는 거의 없어서 기존 화면만으로는 확인이 어려움
- 이 보고서의 목적이 바로 그 gap을 메우는 것

### 백엔드/테스트

검증된 항목:

- bootstrap registry 해석
- `ppo` champion artifact resolve
- `model_versions` snapshot 생성
- ML logger provenance 기록

테스트 결과:

- model registry / snapshot / ml logger 관련 테스트 통과

주의:

- 이 변경은 주로 내부 데이터 경로 변경이므로, 실제 체감 확인은 DB/JSONL/관리자용 inspection에서 더 잘 드러남

---

## 5. 팀에 요청해야 할 운영 규칙

앞으로 새 모델은 아래 두 파일을 항상 같이 전달받는 것이 좋습니다.

- `model_name.pth`
- `model_name.json`

권장 최소 JSON 필드:

```json
{
  "schema": "model-metadata.v1",
  "name": "PPO_PR_Server_20260405_120000_step_12345678",
  "architecture": "ppo",
  "obs_dim": 211,
  "action_dim": 200,
  "hidden_dim": 512,
  "num_res_blocks": 3,
  "num_players": 3,
  "potential_mode": "option3",
  "training_script": "PuCo_RL/train/train_ppo_selfplay_server.py",
  "created_at": "2026-04-05T12:00:00Z",
  "run_id": "selfplay-20260405-01",
  "artifact_sha256": "..."
}
```

이유:

- wrapper 선택을 추측하지 않기 위해
- observation schema 호환성을 체크하기 위해
- 잠재함수/보상 버전과 행동 로그를 연결하기 위해
- 나중에 champion/candidate 승격 이력을 남기기 위해

---

## 6. 결론

이번 변경은 UI보다 운영 내부 품질에 가까운 작업입니다.

- `ppo` 모델 로딩이 artifact-aware 해졌고
- 게임 단위 모델 provenance snapshot이 생겼고
- ML logging 경로에 model provenance가 들어갔고
- 향후 registry/canary 구조로 확장할 토대가 마련됐습니다.

즉 “학습된 모델을 실제 agent로 붙이고, 나중에 어떤 모델이 어떤 행동을 했는지 다시 설명할 수 있는 상태”로 한 단계 이동한 작업입니다.
