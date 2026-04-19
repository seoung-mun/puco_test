# Model Bundle Adapter Serving Design

작성일: 2026-04-19  
관점: Brainstorming + MLOps Engineer  
대상 저장소: `castone`  
관련 코드:
- `PuCo_RL/env/pr_env.py`
- `backend/app/services/model_registry.py`
- `backend/app/services/agents/wrappers.py`
- `backend/app/services/bot_service.py`
- `backend/app/services/action_translator.py`
- `backend/app/services/state_serializer.py`

## 1. Understanding Summary

- `PuCo_RL`의 최신 개발 기준은 `main`이 아니라 `feature/obs-encoding-onehot` 브랜치다.
- 앞으로 `pr_env.py`의 관측 공간과 일부 행동 의미는 계속 변할 가능성이 높다.
- 사용자가 원하는 목표는 새 모델이 재학습되더라도 `backend/app` 파일을 매번 같이 수정하지 않는 운영 구조다.
- 웹/백엔드 계약은 가능한 한 안정적으로 유지하고, 모델별 차이는 모델 번들 쪽에서 흡수하고 싶다.
- 모델 가중치는 학습 당시의 관측 공간, 행동 공간, 아키텍처와 함께 버전 관리되어야 한다.
- 룰 기반 파일형 봇은 코드로 유지하되, 모델 파일형 봇은 새 학습 모델을 따로 공급하는 방향을 전제로 한다.
- 이번 문서의 핵심 질문은 "한 번의 구조 개편 이후, 이후부터는 새 모델 추가만으로 서빙이 가능한가?"에 대한 설계 답변이다.

## 2. Assumptions

- 현재 웹이 요구하는 공개 계약은 Castone backend가 생성하는 rich game state와 action API다.
- 사용자 의도는 "영구적으로 backend/app 무수정"이 아니라, "한 번의 구조 개편 이후 future model onboarding 때 backend/app 무수정"에 가깝다.
- 모델 파일형 봇은 앞으로 sidecar 또는 번들 형태의 메타데이터를 함께 전달할 수 있다.
- 모델별 adapter 코드는 backend 프로세스에서 import 가능한 Python 모듈로 배포 가능하다.
- `PuCo_RL` 엔진 자체는 계속 사용할 수 있지만, backend 서빙 경계는 `pr_env.py`의 flatten 규칙에 직접 의존하지 않는 방향이 바람직하다.
- 보안과 운영 안정성을 위해 임의 pickle 전체를 무조건 실행하는 구조는 피해야 한다.

## 3. Explicit Non-Goals

- 이번 문서는 지금 당장 모든 legacy 모델을 자동 마이그레이션하는 구현 계획이 아니다.
- 이번 문서는 BentoML 전면 도입 결정 문서가 아니다.
- 이번 문서는 프론트 UI 계약 자체를 새 모델마다 바꾸는 방향을 제안하지 않는다.
- 이번 문서는 RL 알고리즘 자체 변경이나 재학습 하이퍼파라미터 튜닝을 다루지 않는다.

## 4. Current State Diagnosis

## 4.1 현재 backend는 env 스키마에 직접 결합되어 있다

현재 backend는 모델 입력 계약을 자체적으로 고정하지 못하고, 런타임 `PuertoRicoEnv`의 observation/action space를 직접 읽는다.

- `backend/app/services/bot_service.py`
  - dummy env를 만들어 `observation_space`와 `obs_dim`을 계산한다.
- `backend/app/services/model_registry.py`
  - fingerprint와 bootstrap profile을 특정 upstream commit 기준으로 계산한다.
- `backend/app/services/agents/wrappers.py`
  - 현재 호환 로직은 사실상 `210 <-> 211` 차원 patch 수준이다.

이 구조의 의미:

- `pr_env.py`가 semantic obs로 바뀌거나
- flatten 순서가 바뀌거나
- `current_phase` 표현 방식이 바뀌거나
- Mayor action semantics가 바뀌면

backend는 모델 파일만 교체해서는 안전하게 계속 서빙할 수 없다.

## 4.2 최신 `PuCo_RL` feature 브랜치는 이미 관측/행동 계약이 이동 중이다

실제 최신 개발 브랜치 `feature/obs-encoding-onehot` 기준으로 관찰된 변화:

- raw scalar/slot 기반 obs에서 semantic one-hot/count 기반 obs로 이동
- flattened obs dim이 기존 210/211 계열이 아니라 293으로 증가
- 일부 휴리스틱/평가 코드가 새 semantic obs 전제를 갖도록 변경
- Mayor placement도 slot 중심 사고에서 type 중심 사고가 섞인 방향으로 이동

즉, "환경 변경 -> 새 모델 재학습 -> 파일만 교체"가 성립하려면
backend가 더 이상 `pr_env.py`의 현재 shape를 신뢰하면 안 된다.

## 4.3 현재 sidecar는 좋은 시작점이지만 아직 충분하지 않다

현재 `model_registry.py`의 sidecar는 아래 정도를 제공한다.

- family
- architecture
- obs_dim / action_dim
- num_players
- fingerprint 일부

하지만 아직 부족한 정보:

- obs schema version
- action schema version
- adapter identifier
- canonical state version
- decode policy
- compatibility target
- promotion gate 결과

즉, 현재 sidecar는 "신분증" 역할은 하지만 "실행 가능한 호환성 계약"까지는 아니다.

## 5. Design Goal

한 번의 구조 개편 이후 다음을 만족하는 것이 목표다.

1. 새로운 `pr_env.py` 기준으로 새 모델이 재학습되어도, 모델 온보딩 시 `backend/app` 코드 수정이 없어야 한다.
2. 기존 모델과 신규 모델이 동시에 공존 가능해야 한다.
3. 웹/공개 API 계약은 가능한 한 안정적으로 유지되어야 한다.
4. 모델 가중치는 학습 당시의 입력/출력 계약과 함께 버전 관리되어야 한다.
5. 행동 공간이 바뀌더라도, 현재 canonical API action으로 매핑 가능한 범위에서는 adapter가 변환을 책임져야 한다.
6. 모델 승격, 롤백, replay parity, 운영 감사가 가능한 MLOps 경로를 가져야 한다.

## 6. Design Options

## Option A. 현 구조 유지 + 차원 patch 확장

정의:

- backend가 계속 `PuertoRicoEnv`에서 obs/action shape를 읽는다.
- wrapper에서 `210 -> 211 -> 293` 같은 patch를 계속 추가한다.

장점:

- 초기 변경량이 작다.

단점:

- env 스키마가 또 바뀔 때마다 backend 수정이 다시 필요하다.
- patch가 누적될수록 디버깅이 어려워진다.
- action semantics가 바뀌는 순간 구조가 무너진다.
- 장기 운영 관점에서 비권장이다.

## Option B. sidecar 강화 + backend generic flatten 유지

정의:

- sidecar에 obs_dim/action_dim/schema_version을 더 넣는다.
- 하지만 backend는 계속 runtime env flatten을 수행한다.

장점:

- 현재 구조를 비교적 덜 깨뜨린다.

단점:

- flatten 순서와 feature 의미가 backend/runtime env에 여전히 묶여 있다.
- "학습 당시 obs spec"과 "현재 env obs spec"이 다르면 sidecar만으로는 해결되지 않는다.
- action decode도 여전히 backend 하드코딩이 남는다.

## Option C. Recommended: Canonical State + Model Bundle Adapter Registry

정의:

- backend는 모델 입력 벡터를 직접 만들지 않는다.
- backend는 오직 안정적인 `canonical serving state`와 `canonical legal action set`만 만든다.
- 각 모델 번들은 자신의 adapter를 통해
  - `canonical state -> model obs`
  - `canonical legal actions -> model mask`
  - `model output -> canonical engine/web action`
  를 수행한다.

장점:

- 이후 새 모델 온보딩 시 backend 코드 수정이 필요 없다.
- old/new 모델 공존이 가능하다.
- obs/action 의미 변경을 번들 단위로 격리할 수 있다.
- replay parity와 승격 기준을 명시하기 쉽다.

단점:

- 초기 구조 개편 비용이 있다.
- adapter 버전 관리 체계가 필요하다.
- canonical state를 잘 설계해야 한다.

결론:

- 장기적으로 원하는 운영 목표를 만족하는 유일한 구조는 Option C다.

## 7. Selected Design

이 문서의 추천안은 `Canonical State + Model Bundle Adapter Registry`다.

핵심 원칙:

- backend는 게임 상태를 "표준 입력"으로만 노출한다.
- 모델은 자기 번들 안의 adapter를 통해서만 추론된다.
- `pr_env.py` 변화는 학습 코드와 번들 생성 쪽에 흡수되고, backend 공개 계약은 고정한다.

## 8. Target Architecture

```text
Web / Public API
    |
    v
Castone Backend
    |- EngineWrapper / Game State
    |- CanonicalStateBuilder
    |- CanonicalActionCatalog
    |- ModelBundleRegistry
    |- AdapterRuntime
    |
    v
Model Bundle
    |- checkpoint.pth
    |- manifest.json
    |- obs_spec.json
    |- action_spec.json
    |- adapter module
    |- optional assets (lookup tables, vocab, scalers)
```

### 역할 분리

- Backend core
  - 현재 게임 상태 생성
  - canonical state 생성
  - legal action catalog 생성
  - bundle/adapter 로드
  - adapter 결과 action 실행

- Model bundle
  - 학습 당시 아키텍처
  - 학습 당시 obs schema
  - 학습 당시 action schema
  - encode/decode 로직
  - optional auxiliary assets

## 9. Canonical Serving Boundary

## 9.1 Canonical state란 무엇인가

canonical state는 모델 독립적인 backend 표준 상태다.

이 상태는 다음 조건을 만족해야 한다.

- 웹이 이해하는 현재 게임 상태를 충분히 표현한다.
- 특정 모델의 flatten 순서에 의존하지 않는다.
- raw env internal slot order가 바뀌어도 최대한 의미를 보존한다.
- Python dict/JSON으로 직렬화 가능하다.
- replay/logging/audit에도 재사용 가능하다.

예시 필드:

- global
  - phase
  - current_player
  - governor_idx
  - vp_supply
  - colonist_supply
  - goods_supply
  - trading_house contents
  - cargo ship states
  - available roles
  - role bonuses

- players[*]
  - doubloons
  - vp_chips
  - goods
  - island tiles
  - tile occupancy
  - buildings
  - building colonists
  - unplaced colonists
  - derived public stats

중요:

- canonical state는 "웹 표시와 게임 판단에 충분한 구조화 상태"이지,
  "특정 PPO 입력 벡터"가 아니다.

## 9.2 Canonical legal action catalog란 무엇인가

현재처럼 단순 0/1 mask만 들고 있는 대신, backend는 legal action을 의미 단위로도 보유해야 한다.

예시:

```json
[
  {
    "canonical_id": "role:settler",
    "public_action_id": "role:settler",
    "model_semantic_id": "role:settler",
    "engine_action": 0
  },
  {
    "canonical_id": "settler:take_tile:coffee",
    "public_action_id": "settler:take_tile:coffee",
    "model_semantic_id": "settler:take_tile:coffee",
    "engine_action": 8
  },
  {
    "canonical_id": "mayor:island_slot:3",
    "public_action_id": "mayor:island_slot:3",
    "model_semantic_id": "mayor:island_slot:3",
    "engine_action": 123
  }
]
```

이 catalog가 필요한 이유:

- model adapter가 semantic decode를 하기 쉽다.
- slot 방식과 type 방식 사이의 매핑이 가능해진다.
- replay, debugging, safety guard에 활용 가능하다.

추가 원칙:

- `public_action_id`
  - 웹/API와 사람이 이해하는 공개 식별자
- `model_semantic_id`
  - adapter 내부 semantic matching용 식별자
- `engine_action`
  - 현재 엔진이 실제로 consume 하는 정수 action

세 식별자를 분리해두면
"공개 계약은 유지하지만 엔진 구현이나 모델 의미가 달라지는 상황"을 더 안전하게 흡수할 수 있다.

## 10. Model Bundle Specification

## 10.1 Bundle 구성

모델 파일형 봇은 최소 아래 파일을 가진 하나의 논리 번들로 관리한다.

```text
bundle/
  checkpoint.pth
  manifest.json
  obs_spec.json
  action_spec.json
  adapter.py
  assets/
    ...
```

## 10.2 `manifest.json` 초안

```json
{
  "schema_version": "model-bundle.v2",
  "bundle_id": "ppo-pr-server-feature-obs-onehot-20260419",
  "family": "ppo",
  "policy_tag": "candidate",
  "architecture": "ppo_residual",
  "checkpoint_file": "checkpoint.pth",
  "checkpoint_sha256": "....",
  "adapter_id": "puco.semantic293.type_mayor.v1",
  "adapter_module": "common.adapter:Semantic293TypeMayorAdapter",
  "adapter_version": "1.0.0",
  "canonical_state_version": "castone.canonical-state.v1",
  "canonical_action_version": "castone.canonical-action.v1",
  "obs_schema_version": "puco.obs.semantic293.v1",
  "action_schema_version": "puco.action.type-mayor.v1",
  "obs_dim": 293,
  "action_dim": 200,
  "num_players": 3,
  "network": {
    "hidden_dim": 512,
    "num_res_blocks": 3
  },
  "training": {
    "source_repo": "dae-hany/PuertoRico-BoardGame-RL-Balancing",
    "source_branch": "feature/obs-encoding-onehot",
    "source_commit": "c08089c",
    "training_script": "PuCo_RL/train/train_ppo_hybrid_server.py"
  },
  "compatibility": {
    "backend_min_bundle_runtime": "1.0.0",
    "supported_canonical_state_versions": ["castone.canonical-state.v1"],
    "supported_canonical_action_versions": ["castone.canonical-action.v1"]
  }
}
```

## 10.3 `obs_spec.json`

목적:

- 모델 입력 생성 규칙을 선언적으로 기록
- flatten 순서, derived feature, normalization 여부를 명시

포함 예시:

- feature list
- ordering
- dtype
- normalization
- optional defaults
- optional derived feature definitions

주의:

- derived feature 로직 전체를 JSON으로만 표현하려 하면 과도하게 복잡해질 수 있다.
- 따라서 핵심 계약은 JSON에 두고, 실제 복잡한 계산은 adapter 코드가 수행하는 hybrid 방식이 적절하다.

## 10.4 `action_spec.json`

목적:

- 모델이 출력하는 action index가 어떤 의미인지 기록
- decode 시 tie-break나 legal mapping 규칙을 명시

포함 예시:

- output head size
- action index to semantic action
- canonical mapping strategy
- illegal action fallback policy
- phase-specific decode mode

## 11. Adapter Interface

## 11.1 권장 인터페이스

```python
class PolicyAdapter:
    adapter_id: str
    canonical_state_version: str
    canonical_action_version: str
    obs_schema_version: str
    action_schema_version: str

    def validate_compatibility(self, manifest: dict, runtime_versions: dict) -> None:
        ...

    def encode_obs(self, state: dict, player_idx: int) -> "np.ndarray":
        ...

    def encode_action_mask(self, state: dict, legal_actions: list[dict]) -> "np.ndarray":
        ...

    def decode_action(
        self,
        model_action_idx: int,
        state: dict,
        legal_actions: list[dict],
    ) -> int:
        ...
```

## 11.2 Adapter 책임

- manifest와 runtime canonical version의 호환성 사전 검증
- 학습 당시 입력 형식과 현재 canonical state 사이의 변환
- legal action subset을 모델 action space mask로 투영
- 모델 output을 현재 engine action으로 복원
- 불법 action 또는 ambiguity 발생 시 deterministic fallback 적용

## 11.3 Adapter가 하지 말아야 할 일

- 엔진 상태를 직접 mutate
- 웹 payload를 직접 생성
- DB 조회 의존
- 학습 코드와 runtime code가 다른 의미를 갖도록 drift 유발

## 12. Action Mapping Strategy

## 12.1 행동 공간이 바뀌어도 항상 호환되는 것은 아니다

중요한 제한:

- adapter는 "매핑 가능한 변화"만 흡수할 수 있다.
- 모델이 표현할 수 없는 새 행동 의미가 생기면 old model은 그대로 재사용할 수 없다.

### 흡수 가능한 변화

- 단순 index 재배열
- slot -> type 매핑
- type -> slot 매핑
- action band 일부 재구성
- phase별 legal subset 변화

### 흡수 불가능한 변화

- 모델 output 차원이 표현력 자체를 잃은 경우
- 새 행동 의미가 old model output space에 존재하지 않는 경우
- decode에 필요한 정보가 canonical state에 없는 경우

## 12.2 Mayor 예시

### Case A. 모델은 type 기반, backend/engine은 slot 기반

모델 output:

- `mayor:island_tile_type:coffee`

현재 legal action catalog:

- `mayor:island_slot:1`
- `mayor:island_slot:4`

adapter는 canonical state를 보고 slot 1과 4가 모두 coffee라면
사전에 정한 정책으로 하나를 고른다.

권장 tie-break:

1. 가장 낮은 slot index
2. deterministic stable order

### Case B. 모델은 slot 기반, backend/engine은 type 기반

slot 3이 coffee plantation이면 adapter는
`mayor:island_tile_type:coffee`로 encode/decode 가능하다.

단, type action이 하나인데 slot 후보가 여러 개인 경우는
정보 손실 여부를 검토해야 한다.

## 12.3 Decode fallback policy

decode 실패 시 정책을 명시해야 한다.

권장 순서:

1. exact semantic match
2. same category 내 deterministic fallback
3. legal action 중 safest deterministic fallback
4. error + request reject

random fallback은 운영 replay와 parity 분석을 어렵게 하므로 비권장이다.

추가 원칙:

- fallback이 발생하면 반드시 `fallback_reason`을 enum으로 기록한다.
- 예시 enum:
  - `exact_match_missing`
  - `multi_slot_ambiguity`
  - `phase_band_mismatch`
  - `illegal_model_action`
  - `adapter_guard_triggered`

이 값은 replay, audit, promotion gate에서 집계 가능한 필드로 남겨야 한다.

## 13. Runtime Flow

## 13.1 Inference flow

```text
1. EngineWrapper가 현재 게임 상태를 읽는다.
2. CanonicalStateBuilder가 canonical state를 만든다.
3. CanonicalActionCatalog가 legal action catalog를 만든다.
4. ModelBundleRegistry가 모델 번들을 로드한다.
5. AdapterRuntime이 adapter를 초기화한다.
6. adapter.encode_obs()가 모델 입력을 생성한다.
7. adapter.encode_action_mask()가 모델 mask를 생성한다.
8. model forward 실행
9. adapter.decode_action()이 engine action int를 반환한다.
10. backend가 해당 action을 실행한다.
```

## 13.2 Replay / audit flow

replay logger에는 다음을 같이 남긴다.

- canonical state version
- canonical action version
- bundle id
- adapter id
- obs/action schema version
- decode result
- fallback 사용 여부

이렇게 해야 "왜 이 모델이 이 행동을 했는지"를 사후 추적할 수 있다.

## 14. One-Time Backend Refactor Scope

future model onboarding 때 backend 수정이 없으려면, 먼저 아래 한 번의 구조 개편이 필요하다.

## 14.1 변경 대상

- `backend/app/engine_wrapper/wrapper.py`
  - current phase / current player / raw state 추출 경계 정리
- `backend/app/services/bot_service.py`
  - runtime env flatten 의존 제거
- `backend/app/services/agents/wrappers.py`
  - `_adapt_obs_dim` patch 중심 구조 제거
- `backend/app/services/model_registry.py`
  - bundle manifest v2 지원
- `backend/app/services/action_translator.py`
  - canonical action descriptor 대응
- `backend/app/services/state_serializer.py`
  - canonical state builder와의 역할 경계 정리
- replay/logger/parity 경로
  - adapter/bundle metadata 기록

## 14.2 개편 후 바뀌는 책임

- backend는 "게임 상태 제공자"
- adapter는 "모델 계약 변환기"
- bundle registry는 "모델 온보딩 진입점"

즉, 이후부터 새 모델 추가 작업은 backend 코드 수정이 아니라
"새 bundle 등록" 작업이 된다.

## 15. MLOps Lifecycle Design

## 15.1 Training output

학습 완료 시 산출물은 단일 `.pth`가 아니라 아래 세트여야 한다.

- `checkpoint.pth`
- `manifest.json`
- `obs_spec.json`
- `action_spec.json`
- `adapter.py` 또는 import 가능한 adapter module reference
- optional metrics report
- optional evaluation summary

## 15.2 Registration

모델 레지스트리 등록 시 검증 항목:

- manifest schema validation
- checkpoint load success
- declared obs_dim/action_dim consistency
- adapter import success
- canonical version compatibility
- smoke inference success
- replay parity scenario pass

## 15.3 Promotion states

권장 상태:

- `draft`
- `candidate`
- `shadow`
- `champion`
- `rollback`
- `retired`

현재 Castone의 `family + policy_tag` 구조는 유지 가능하지만,
실제 내부 해석 단위는 `bundle_id`가 되어야 한다.

## 15.4 Promotion gate

승격 전 자동 검증 권장 항목:

- schema validation
- checkpoint architecture compatibility
- adapter compatibility
- golden scenario inference parity
- illegal action rate
- fallback decode rate
- fallback reason distribution
- replay logging integrity
- basic head-to-head evaluation

## 15.5 Rollback

롤백은 가장 쉬워져야 한다.

원칙:

- 이전 `champion bundle_id`를 다시 활성화하는 것만으로 롤백 가능해야 한다.
- backend 코드를 되돌리는 방식은 롤백 경로로 사용하지 않는다.

## 16. Repository Ownership Boundary

이 설계는 `castone`과 `PuCo_RL` 원본 저장소의 책임을 의도적으로 분리한다.

### 16.1 Castone 팀이 주로 수정하는 영역

목적:

- canonical runtime 제공
- bundle/adapter 로딩
- 서빙 안전장치
- replay/audit/promotion gate 운영

주요 경로:

- `backend/app/engine_wrapper/`
- `backend/app/services/model_registry.py`
- `backend/app/services/agents/wrappers.py`
- `backend/app/services/bot_service.py`
- `backend/app/services/action_translator.py`
- `backend/app/services/state_serializer.py`
- `backend/app/services/replay_logger.py`
- 관련 테스트 경로

즉, Castone 팀은 "모델을 직접 학습"하는 팀이라기보다
"모델 번들을 안전하게 서빙하고 운영하는 런타임 팀"에 가깝다.

### 16.2 `PuCo_RL` 원본 저장소 팀이 주로 수정하는 영역

원본 저장소:

- [dae-hany/PuertoRico-BoardGame-RL-Balancing](https://github.com/dae-hany/PuertoRico-BoardGame-RL-Balancing.git)

실제 최신 개발 기준:

- `main`이 아니라 `feature/obs-encoding-onehot`

목적:

- env/obs/action 의미 변경
- 모델 아키텍처 변경
- 학습 파이프라인 변경
- 번들 산출물 생성
- 오프라인 평가 및 모델 품질 검증

주요 수정 경로:

- `PuCo_RL/env/`
  - `pr_env.py`, `engine.py`, `player.py`, `components.py`
  - obs/action semantics 변화의 원천
- `PuCo_RL/agents/`
  - `ppo_agent.py`
  - heuristic bot들
  - 학습 상대, offline evaluator, architecture 관련 변경
- `PuCo_RL/train/`
  - `train_ppo_selfplay_server.py`
  - `train_ppo_hybrid_server.py`
  - checkpoint + manifest/spec export의 핵심 진입점
- `PuCo_RL/utils/`
  - flatten/evaluation/helper
- `PuCo_RL/utils/evaluation/`
  - benchmark, parity, league 검증
- `PuCo_RL/common/`
  - adapter/bundle export helper가 들어가기 가장 자연스러운 위치
- `PuCo_RL/models/`
  - 산출물 저장 위치

### 16.3 `PuCo_RL` 내에서 이번 설계로 새로 생기거나 확장될 가능성이 큰 파일

권장 추가/수정 지점:

- `PuCo_RL/common/adapter.py`
  - adapter base class
  - bundle export helper
  - manifest/spec validation helper
- `PuCo_RL/common/bundle.py` 또는 유사 신규 파일
  - bundle writer / loader utility
- `PuCo_RL/train/train_ppo_selfplay_server.py`
  - 학습 종료 후 bundle export 호출
- `PuCo_RL/train/train_ppo_hybrid_server.py`
  - 학습 종료 후 bundle export 호출
- `PuCo_RL/agents/ppo_agent.py`
  - architecture metadata 노출이 필요하면 보강
- `PuCo_RL/utils/env_wrappers.py`
  - training-side flatten spec와 bundle export 연결 시 보강 가능
- `PuCo_RL/models/`
  - 기존 단일 checkpoint 저장 대신 bundle directory 또는 sidecar 세트 저장

### 16.4 협업 경계 원칙

- `PuCo_RL` 팀은 "학습된 모델이 어떤 입력/출력 계약을 요구하는지"를 bundle로 명시해서 넘긴다.
- `castone` 팀은 "그 bundle을 읽어 canonical runtime에 연결하는 책임"을 가진다.
- future onboarding 시 backend 코드를 안 바꾸려면,
  새로운 모델 semantics는 반드시 `PuCo_RL` 쪽 번들/adapter에서 흡수되어야 한다.

### 16.5 팀별 deliverable

`PuCo_RL` 팀 deliverable:

- `checkpoint.pth`
- `manifest.json`
- `obs_spec.json`
- `action_spec.json`
- adapter module
- evaluation summary

`castone` 팀 deliverable:

- bundle registry support
- adapter runtime support
- canonical state/action runtime
- replay/audit logging
- promotion/rollback controls

## 17. BentoML Positioning

BentoML은 이 설계에서 "필수"는 아니지만 "번들 배포 컨테이너"로는 유용하다.

적합한 사용 위치:

- model bundle 저장
- metadata 부착
- custom_objects 또는 external_modules 동봉
- runner/service packaging

하지만 주의:

- 계약의 source of truth는 Bento 내부 Python 객체가 아니라 `manifest.json`이어야 한다.
- `pickle/cloudpickle` 객체를 정본 계약으로 삼으면 가시성과 이식성이 떨어진다.

즉, BentoML을 쓰더라도 구조는 다음이 바람직하다.

- 정본 계약: JSON manifest/spec
- 실행 구현: adapter module
- 보조 자산: optional pickle/custom objects

## 18. Recommended Compatibility Policy

## 18.1 Backend compatibility promise

backend는 아래 버전만 장기적으로 안정적으로 유지한다.

- `castone.canonical-state.v1`
- `castone.canonical-action.v1`
- `model-bundle.v2`

모델별 세부 obs/action schema는 backend가 보장하지 않는다.
그 책임은 bundle adapter에 있다.

## 18.2 Adapter support window

운영 정책 예시:

- champion + previous champion adapters는 무조건 지원
- retired bundle은 로딩 가능하되 기본 라우팅에서는 제외
- canonical version breaking change 시 major version을 올리고 migration guide 제공

## 19. Risks and Mitigations

## Risk 1. Canonical state가 너무 빈약해서 future model 요구를 못 담음

완화:

- canonical state는 현재 웹 표시용보다 조금 넓게 설계
- derived field 추가는 허용하되 제거는 신중하게 관리

## Risk 2. Adapter가 과도하게 복잡해져 모델마다 작은 서빙 코드베이스가 생김

완화:

- adapter base class 제공
- 공통 helper library 제공
- adapter lint / validation suite 운영

## Risk 3. Semantic decode ambiguity

완화:

- canonical legal action catalog를 richer하게 설계
- deterministic tie-break 정책 문서화
- fallback usage를 전부 로그에 남김

## Risk 4. 번들 간 replay parity 비교가 어려워짐

완화:

- replay logger에 bundle/adapter/schema 정보를 모두 기록
- golden scenario 세트를 운영

## Risk 5. one-time refactor 범위가 생각보다 큼

완화:

- 단계적 cutover
- old path와 new path 병행 기간 운영
- first champion만 new bundle runtime 사용

## Risk 6. `PuCo_RL` 최신 feature 브랜치의 리팩터링 결과를 Castone이 임의로 되돌리게 되는 위험

배경:

- `PuCo_RL`의 최신 feature 브랜치는 연구 팀이 실제로 실험하고 검증한 env/obs/action 기준이다.
- 웹 시각화는 부가 기능이지만, 모델 입력 계약은 연구 결과의 핵심이다.
- 따라서 Castone이 편의를 위해 `PuCo_RL` 최신 semantics를 임의 변경하는 방향은 피해야 한다.

완화:

- source of truth는 `PuCo_RL` 최신 feature 브랜치와 거기서 생성된 bundle로 둔다.
- Castone은 모델 semantics를 바꾸지 않고 canonical runtime adapter로만 연결한다.
- 기존 PPO 모델을 살리고 future onboarding 무변경을 달성하기 위해서도 Option C를 유지한다.

## 20. Rollout Plan

## Phase 0. Design lock

- canonical state v1 정의
- canonical action v1 정의
- bundle manifest v2 정의
- adapter interface 고정

## Phase 1. Backend runtime split

- current env-dependent flatten 경로를 isolate
- new adapter runtime 추가
- feature flag로 old/new path 공존

## Phase 2. First adapter

- 현재 최신 feature 브랜치 학습 모델용 adapter 구현
- provided PPO checkpoint를 첫 candidate bundle로 등록

## Phase 3. Validation

- smoke inference
- replay parity
- illegal action / fallback rate 확인
- selected bot match evaluation

## Phase 4. Promotion

- champion 전환
- rollback bundle 지정
- 운영 로그 모니터링

## Phase 5. Legacy cleanup

- old `210/211 patch` wrapper 제거
- backend env flatten 의존 제거
- obsolete fingerprint naming 정리

## 21. Open Questions

- canonical state v1에 어느 수준까지 derived field를 포함할지
- rule-based file bots도 장기적으로 canonical adapter 경로로 통일할지
- bundle 저장 위치를 기존 `PuCo_RL/models`로 유지할지, 별도 registry directory를 둘지
- BentoML을 실제 배포 경로에 넣을지, 내부 bundle spec만 먼저 도입할지

이번 문서 기준 권장 답:

- derived field는 "decode와 replay parity에 필요한 정도"까지만 포함
- rule-based file bots는 우선 예외로 두되 장기적으로 동일 runtime 계약으로 통합
- 저장소는 초기에는 로컬 directory 기반, 이후 필요 시 registry abstraction 추가
- BentoML은 2차 도입 검토, 1차는 자체 bundle spec 우선

## 22. Decision Log

### Decision 1. backend는 future model onboarding 때 수정되지 않는 구조를 목표로 한다

- 대안
  - env 변경 때마다 backend patch
- 선택 이유
  - 운영 비용과 회귀 위험을 줄이기 위해

### Decision 2. canonical state를 backend 정본 입력으로 둔다

- 대안
  - backend가 계속 runtime env flatten 수행
- 선택 이유
  - env schema drift를 backend에서 분리하기 위해

### Decision 3. 모델 배포 단위는 `checkpoint only`가 아니라 `model bundle`이다

- 대안
  - `.pth + ad-hoc json`
- 선택 이유
  - 입력/출력 계약과 운영 메타데이터를 함께 묶기 위해

### Decision 4. obs/action 변환 책임은 adapter가 가진다

- 대안
  - backend 중앙 로직에서 모든 모델별 예외 처리
- 선택 이유
  - 모델별 차이를 지역화하고 backend churn을 줄이기 위해

### Decision 5. pickle은 보조 자산으로만 사용한다

- 대안
  - pickle 전체를 정본 계약으로 사용
- 선택 이유
  - 보안, 가시성, 이식성 문제를 줄이기 위해

### Decision 6. BentoML은 optional packaging layer로만 본다

- 대안
  - BentoML을 즉시 정본 registry로 채택
- 선택 이유
  - 현재 코드베이스는 sidecar/local artifact 중심이라, 먼저 bundle 계약을 고정하는 편이 안전하기 때문이다

### Decision 7. `PuCo_RL` 원본 저장소가 bundle contract의 source of truth를 가진다

- 대안
  - Castone backend에서 모델별 계약을 재정의
- 선택 이유
  - 입력/출력 계약은 학습 시점에 가장 정확히 알 수 있고, future onboarding 무변경 목표와도 맞기 때문이다

## 23. Final Recommendation

추천 결론은 명확하다.

- 지금 구조 그대로는 `pr_env.py`가 바뀔 때 backend/app 수정 없이 계속 서빙하는 것이 어렵다.
- 하지만 한 번 `canonical state + model bundle adapter` 구조로 개편하면,
  이후부터는 새 모델마다
  - 새 체크포인트
  - 새 manifest/spec
  - 새 adapter
  만 등록해서 서빙하는 방향이 가능하다.

즉, "backend 무변경 서빙"은 지금 당장은 불가능하지만,
"한 번의 구조 개편 이후 future onboarding 무변경"은 충분히 가능한 목표다.


## 주의 사항

- test는 변경 사항 위주로 어떤 계약/환경이 깨지는지 
- 그 변경에 대해 어떤 엣지 케이스들이 발생하는지
   - 단순히 import 에거 같은게 아니라 비지니스 로직 상의 문제, 런타임 중 발생할 수 있는 문제 등을 체크해서 테스트를 진행

- 모든 테스트는 docker를 올려서 시행
