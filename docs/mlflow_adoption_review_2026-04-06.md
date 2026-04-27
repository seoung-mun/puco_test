# MLflow 도입 검토 메모

작성일: 2026-04-06  
관점: MLOps Engineer / 운영 관점  
대상: Castone 유지보수자, 모델 학습 담당자, 백엔드/서빙 담당자

## 한 줄 결론

현재 프로젝트 기준으로 **MLflow는 바로 전면 도입하기보다, 학습/평가 추적 계층에만 제한적으로 1차 도입하는 것이 적절**합니다.  
반대로 **MLflow를 현재 런타임 정본 저장소처럼 쓰는 방향은 비권장**입니다.

이유는 간단합니다.

- 이 프로젝트는 이미 `PostgreSQL + Redis + per-game JSONL + replay JSON + sidecar metadata + vis 보고서` 체계가 존재합니다.
- 여기에 MLflow를 정본처럼 추가하면 계보와 책임 경계가 더 분산될 가능성이 큽니다.
- 특히 현재 백엔드 서빙 계약은 `filename + sidecar + env var` 중심이라, MLflow Registry를 곧바로 읽는 구조와 잘 맞지 않습니다.

## 1. 현재 MLOps/운영 구조 인벤토리

현재 코드베이스는 이미 여러 개의 저장/추적 축을 동시에 사용합니다.

| 층 | 현재 사용 중인 체계 | 실제 위치 / 근거 | 역할 |
| --- | --- | --- | --- |
| 학습 실험 추적 | TensorBoard `SummaryWriter` | `PuCo_RL/train/train_ppo_selfplay_server.py`, `PuCo_RL/train_phase_ppo_selfplay_server.py`, `PuCo_RL/train_hppo_selfplay_server.py` | 학습 중 metric 기록 |
| 체크포인트 저장 | `.pth` 파일 | `PuCo_RL/models/`, 일부는 `PuCo_RL/models/ppo_checkpoints/` | 모델 가중치 저장 |
| 모델 메타데이터 | sidecar JSON + bootstrap 파생 | `backend/app/services/model_registry.py` | `obs_dim`, `action_dim`, `architecture`, `family` 등 서빙 계약 |
| 실게임 lineage | DB + per-game JSONL + replay JSON | `games.model_versions`, `game_logs`, `data/logs/games/*.jsonl`, `data/logs/replay/*.json` | 운영 추적, 재학습, replay |
| 사람이 읽는 감사 리포트 | `vis/` 도구 | `vis/README.md` 및 리포트 스크립트 | lineage/storage/behavior 감사 |
| 실시간 상태 전달 | Redis | `game:<id>:meta`, `game:<id>:players`, pub/sub | 실시간 브로드캐스트 및 접속 메타 |

현재 구조에서 중요한 점은 **MLflow가 아직 비어 있는 퍼즐 한 조각이 아니라, 이미 존재하는 여러 저장소 위에 추가로 얹히게 된다는 것**입니다.

### 확인된 구조적 사실

1. **Docker 구성에 MLflow 서버가 없습니다.**
   - 현재 `docker-compose.yml`에는 `db`, `redis`, `backend`, `frontend`, `adminer`만 있습니다.
   - MLflow backend store / artifact store / credentials / backup 정책이 아직 없습니다.

2. **백엔드 서빙은 MLflow Registry를 기준으로 동작하지 않습니다.**
   - 현재는 `.env`의 `PPO_MODEL_FILENAME`, `HPPO_MODEL_FILENAME`와 실제 로컬 파일 경로를 사용합니다.
   - `backend/app/services/agent_registry.py`, `backend/app/services/model_registry.py`가 이 계약을 해석합니다.

3. **모델 메타데이터는 sidecar JSON이 핵심 계약입니다.**
   - `model_registry.py`는 sidecar JSON을 우선 사용하고,
   - 제한적으로 `PPO_PR_Server_*.pth` 이름만 bootstrap 합니다.
   - 즉, MLflow artifact URI만으로는 현재 서빙이 자동 연결되지 않습니다.

4. **실게임 lineage는 이미 별도 체계로 잘게 쪼개져 있습니다.**
   - `games.model_versions`
   - `game_logs`
   - `data/logs/games/<game_id>.jsonl`
   - `data/logs/replay/<game_id>.json`

5. **감사/시각화는 이미 `vis/`가 맡고 있습니다.**
   - `vis/`는 DB/JSONL/replay를 읽어서 Markdown/Mermaid 리포트를 생성합니다.
   - 즉, MLflow를 붙인다고 기존 운영 감사 체계가 자동 대체되지는 않습니다.

### 추가로 보이는 현재 불균일성

- PPO 계열과 Phase/HPPO 계열의 체크포인트 저장 경로가 일관되지 않습니다.
  - `PuCo_RL/train/train_ppo_selfplay_server.py`: `models/ppo_checkpoints/`
  - `PuCo_RL/train_phase_ppo_selfplay_server.py`: `models/`
  - `PuCo_RL/train_hppo_selfplay_server.py`: `models/`
- `PuCo_RL/models/MODEL_ONBOARDING.md`는 `PuCo_RL/train/generate_model_metadata.py` 존재를 가정하지만, 현재 저장소에서는 해당 파일이 보이지 않습니다.
  - 즉, “체크포인트 -> sidecar 자동 생성” 경로가 문서와 실제 코드 사이에서 완전히 정렬되어 있지 않을 수 있습니다.

이 불균일성은 MLflow를 붙였을 때 run/artifact naming과 metadata consistency를 망가뜨릴 수 있는 지점입니다.

## 2. 현재 저장 방식별 역할 정리

현재 프로젝트를 저장소 관점으로 보면 아래처럼 이해하는 것이 가장 정확합니다.

| 저장 방식 | 현재 역할 | 정본 여부 | 비고 |
| --- | --- | --- | --- |
| PostgreSQL | `users`, `games`, `game_logs` 저장 | 운영 정본 | 유저/방/게임 메타와 액션 감사 로그 |
| Redis | 최신 상태, 접속 상태, pub/sub 브로드캐스트 | 비정본 | 실시간 캐시/전달 레이어 |
| `data/logs/games/*.jsonl` | per-game raw transition 저장 | 학습/lineage용 원본 | `state_before`, `action`, `reward`, `state_after`, `model_info` |
| `data/logs/replay/*.json` | 사람이 읽는 replay 로그 | 디버깅/검수용 | 행동 흐름과 commentary 확인 |
| `PuCo_RL/models/*.pth` | 실제 모델 가중치 저장 | 모델 아티팩트 정본 | 서빙 대상 checkpoint |
| sidecar `.json` | 모델 메타데이터 저장 | 모델 메타 정본 | `architecture`, `obs_dim`, `action_dim`, `num_players` 등 |
| TensorBoard `runs/` | 훈련 metric 곡선 저장 | 실험 관찰용 | 학습 추이 확인 |

### PostgreSQL은 현재 “학습 데이터 저장소”보다 “운영 메타 저장소”에 가깝다

질문하신 방향처럼, 나중에 원격 저장소나 원격 서버로 학습 데이터를 보내는 구조를 만들 때 PostgreSQL을 중간 메타 저장소로 활용하는 것은 가능합니다.  
다만 현재 구조에서 PostgreSQL은 아래 역할이 더 핵심입니다.

- 유저/방/게임 상태 관리
- 액션 감사 로그 보관
- 운영 관점의 조회와 디버깅

즉, 대용량 학습 원본을 오래 쌓는 primary data lake로 쓰기보다는, **운영 메타와 인덱스 역할**에 더 적합합니다.

### sidecar는 정확히 무엇인가

sidecar는 `.pth` 체크포인트 옆에 붙는 모델 메타데이터 JSON입니다.  
쉽게 말하면 **모델 신분증**입니다.

현재 backend는 이 sidecar를 보고 아래를 판단합니다.

- 이 모델이 PPO인지, PhasePPO인지
- `obs_dim`, `action_dim`이 현재 환경과 맞는지
- `architecture`가 wrapper와 호환되는지
- `num_players`, `potential_mode` 같은 기본 계약이 맞는지

즉, sidecar는 단순 설명문이 아니라 **서빙 안전장치**에 가깝습니다.

### Redis는 “실시간 게임 로그 저장소”라기보다 “실시간 상태/전달 레이어”다

표현을 조금 더 정확히 하면, Redis는 장기 로그 저장소보다는 아래 역할에 가깝습니다.

- 최신 상태 캐시
- 접속 상태 관리
- pub/sub 기반 브로드캐스트

현재 Redis에 들어가는 값은 장기 감사 용도가 아니라, **진행 중 게임을 빠르게 전달하고 연결 상태를 추적하기 위한 임시성 데이터**라고 보는 편이 맞습니다.

## 3. MLflow를 붙였을 때 무엇이 대체될 수 있는가

MLflow를 붙인다고 모든 저장소가 대체되는 것은 아닙니다.  
현재 구조 기준으로는 아래처럼 보는 것이 가장 안전합니다.

| 현재 저장 방식 | MLflow로 대체 가능? | 권장 여부 | 이유 |
| --- | --- | --- | --- |
| TensorBoard `runs/` | 가능 | 권장 | 실험 비교/검색/UI 측면에서 MLflow가 더 강함 |
| `.pth` 모델 파일 저장 | 부분 가능 | 조건부 | artifact catalog는 가능하지만 현재 backend 서빙 계약과 직접 연결되진 않음 |
| sidecar `.json` | 부분 가능 | 제한적 | 완전 대체보다 MLflow 메타에서 sidecar 생성이 더 안전 |
| PostgreSQL | 불가 | 비권장 | 운영 메타/감사/권한 저장소 역할은 MLflow가 대체 불가 |
| Redis | 불가 | 비권장 | 실시간 pub/sub, 캐시, 접속 상태는 MLflow 대상이 아님 |
| `data/logs/games/*.jsonl` | 이론상 가능 | 비권장 | per-game raw logs는 MLflow artifact로 넣기엔 너무 무겁고 책임도 다름 |
| `data/logs/replay/*.json` | 일부 가능 | 비권장 | 샘플 첨부는 가능하지만 replay 정본 저장소로는 부적합 |

### 실제로 대체를 검토해볼 만한 것

#### 1. TensorBoard `runs/`

이건 MLflow가 가장 자연스럽게 대체할 수 있는 계층입니다.

장점:

- run 비교가 쉬움
- 파라미터/메트릭/태그 검색 가능
- 팀 단위로 UI 공유가 쉬움
- checkpoint와 metric을 한 run으로 묶기 좋음

단점:

- 로컬에서 단순히 곡선만 보는 용도는 TensorBoard가 더 가벼울 수 있음
- MLflow 서버 운영이 추가됨

#### 2. 모델 아티팩트 관리 일부

MLflow artifact store를 이용하면 checkpoint 관리 체계는 좋아질 수 있습니다.

장점:

- 중앙에서 checkpoint 관리 가능
- candidate / champion 개념을 붙이기 쉬움
- 특정 실험 run과 checkpoint를 연결하기 좋음

단점:

- 현재 backend는 `PuCo_RL/models/*.pth` basename과 sidecar를 기준으로 서빙함
- 따라서 MLflow artifact만 있다고 backend가 바로 로딩 가능한 구조는 아님
- 실제 서빙에는 결국 로컬 동기화 또는 export 단계가 필요함

#### 3. sidecar 생성 파이프라인

sidecar를 MLflow가 완전히 대체하기보다는, MLflow에 기록된 메타데이터를 바탕으로 sidecar를 자동 생성하는 방향이 더 좋습니다.

장점:

- 메타데이터 중복 입력 감소
- 실험 run -> serving metadata 연결이 쉬워짐

단점:

- sidecar 스키마와 MLflow tag/param 스키마를 강하게 맞춰야 함
- 이 정렬이 안 되면 오히려 메타데이터 충돌이 늘어남

### 대체하면 안 되는 것

#### 1. PostgreSQL

MLflow는 아래를 대신할 수 없습니다.

- 유저 정보 저장
- 게임/방 메타 저장
- 감사 로그 조회
- 권한/인증 기반 API와의 연동

즉, PostgreSQL은 계속 운영 정본으로 유지되어야 합니다.

#### 2. Redis

MLflow는 실시간 상태 전달용 도구가 아닙니다.

- pub/sub
- 현재 연결 상태
- 임시 캐시

이 역할은 그대로 Redis가 맡아야 합니다.

#### 3. per-game JSONL

`data/logs/games/<game_id>.jsonl`는 실게임 raw transition입니다.  
이건 실험 metric보다 훨씬 저수준이고, 양도 많고, 게임 단위로 잘게 쪼개져 있습니다.

MLflow artifact로 전부 올리기 시작하면:

- 파일 수가 급증
- UI 탐색성이 나빠짐
- 저장 비용이 커짐
- runtime lineage와 training lineage가 섞임

그래서 이건 기존 구조를 유지하는 편이 낫습니다.

#### 4. replay JSON

replay JSON은 사람이 경기 흐름을 눈으로 따라가며 보는 용도입니다.  
샘플 몇 개를 MLflow artifact에 첨부하는 것은 가능하지만, 정본 replay 저장소를 MLflow로 바꾸는 것은 이득이 크지 않습니다.

## 4. MLflow를 붙였을 때의 장점

현재 구조에서 MLflow가 실제로 도움이 되는 지점은 **학습 실험 관리와 모델 승격 근거 정리**입니다.

### 4.1 실험 비교가 쉬워진다

지금은 학습 metric이 TensorBoard 중심이고, 체크포인트는 파일 시스템에 남습니다.  
이 구조는 개인 실험에는 충분하지만, 아래 질문에 답하기는 어렵습니다.

- 어떤 하이퍼파라미터 조합이 가장 좋았는가?
- PPO와 PhasePPO를 같은 축에서 비교할 수 있는가?
- 특정 champion 모델이 왜 선택되었는가?

MLflow를 붙이면 아래가 쉬워집니다.

- run 단위 실험 관리
- 하이퍼파라미터/metric/태그 비교
- experiment UI 기반 검색
- 학습 시점별 artifact 연결

### 4.2 재현성이 좋아진다

현재도 sidecar JSON이 있으면 일부 재현성은 확보되지만, 실험 run 자체를 체계적으로 묶는 계층은 약합니다.  
MLflow는 다음을 한 run 아래 묶기에 적합합니다.

- 하이퍼파라미터
- 환경 설정
- git commit hash
- 사용한 체크포인트
- 출력 checkpoint path
- 평가 결과

즉, “이 모델이 왜 만들어졌는가”를 설명하는 데 강합니다.

### 4.3 모델 승격 프로세스를 만들기 쉬워진다

장기적으로 아래 흐름을 만들 수 있습니다.

1. 실험 run 생성
2. metric 기준 상위 run 선별
3. candidate artifact 지정
4. 평가 결과 연결
5. champion 판단 근거 기록

현재는 이 판단이 파일명과 개별 문서에 분산될 가능성이 큽니다.

### 4.4 sidecar JSON 관리 기준을 강화할 수 있다

MLflow 자체가 sidecar를 대체하는 것은 아니지만, 다음을 강제하는 계기로는 좋습니다.

- 모든 학습 결과에 metadata JSON 동반
- `architecture`, `obs_dim`, `action_dim`, `num_players` 필수화
- `git_commit`, `training_script`, `potential_mode`, `reward weights` 기록

즉, MLflow는 지금 프로젝트에서 **sidecar discipline을 강화하는 촉매**가 될 수 있습니다.

## 5. 현재 프로젝트 기준 단점과 구조적 충돌

이 섹션이 가장 중요합니다.  
문제는 “MLflow가 나쁘다”가 아니라, **현재 코드와 어디서 충돌하는가**입니다.

### 5.1 이미 저장소가 많다

현재도 정본 후보가 많습니다.

- PostgreSQL
- Redis
- per-game JSONL
- replay JSON
- sidecar JSON
- TensorBoard runs

여기에 MLflow까지 넣으면 최소 7번째 축이 생깁니다.  
이때 가장 위험한 질문은 아래입니다.

- 어떤 값이 최종 정본인가?
- 모델 provenance는 DB를 봐야 하나, sidecar를 봐야 하나, MLflow를 봐야 하나?
- 운영 장애 시 어느 저장소를 믿어야 하나?

MLflow를 잘못 붙이면 “가시성은 좋아지는데 정합성은 나빠지는” 상황이 생길 수 있습니다.

### 5.2 backend 서빙 구조와 바로 맞지 않는다

현재 backend의 모델 선택 구조는 아래입니다.

- `.env`의 파일명 선택
- 로컬 파일 경로 resolve
- sidecar JSON 또는 bootstrap metadata 해석
- `ModelArtifact`로 서빙 계약 검증

즉, 현재는 **로컬 파일 + 로컬 메타데이터**가 서빙 계약의 핵심입니다.

MLflow Registry를 곧바로 source of truth로 삼으려면 추가 작업이 필요합니다.

- registry stage -> 실제 파일 동기화
- artifact URI -> 로컬 경로 매핑
- sidecar 생성/동기화
- backend cache invalidation
- startup 시 artifact resolution 정책

이 작업 없이 MLflow를 붙이면 “MLflow에는 production, backend는 옛 `.env` 모델” 같은 이중 운영이 생깁니다.

### 5.3 `vis/` 체계를 대체하지 못한다

`vis/`는 현재 실제 운영 감사에 맞춰져 있습니다.

- DB `game_logs`
- `data/logs/games/*.jsonl`
- `data/logs/replay/*.json`

MLflow는 실험 추적에는 좋지만, **실게임 액션 단위 lineage audit**까지 그대로 대체하는 도구는 아닙니다.  
즉, MLflow를 도입해도 `vis/`는 계속 필요합니다.

### 5.4 per-game transition를 MLflow artifact로 올리는 것은 좋지 않다

`data/logs/games/<game_id>.jsonl`는 per-game raw transition입니다.  
이 파일들을 게임마다 MLflow artifact로 올리기 시작하면 문제가 생깁니다.

- artifact 수가 폭증
- UI 탐색성이 나빠짐
- 저장비가 올라감
- 업로드/다운로드 시간이 길어짐
- runtime logging과 experiment logging이 섞임

이 데이터는 MLflow보다 **기존 per-game storage + vis pipeline**이 더 적합합니다.

### 5.5 HPPO 명칭 불일치가 taxonomy를 오염시킬 수 있다

현재 확인된 큰 리스크 중 하나는 HPPO 경로입니다.

- `train_hppo_selfplay_server.py`
- `train_hppo_league_server.py`
- `tests/test_hppo_agent.py`

이 경로들은 `HierarchicalAgent`를 기대하지만, 실제 `agents/ppo_agent.py`에는 `Agent`, `PhasePPOAgent`가 정의되어 있습니다.

이 상태에서 MLflow experiment/model naming을 먼저 도입하면 다음이 생길 수 있습니다.

- `HPPO`
- `HierarchicalAgent`
- `PhasePPO`
- `hppo`

같은 계열을 서로 다른 이름으로 기록하는 taxonomy 오염이 발생합니다.

즉, **실험 이름 체계와 모델 family 체계를 정리하기 전에 MLflow를 붙이면 오히려 데이터 품질이 나빠질 수 있습니다.**

### 5.6 현재 운영은 로컬 디스크 중심이라 MLflow를 붙이면 운영 복잡도가 곧바로 늘어난다

지금은 비교적 단순합니다.

- DB는 PostgreSQL
- 캐시는 Redis
- 로그는 로컬 파일

MLflow를 붙이면 최소한 아래를 결정해야 합니다.

- backend store DB
- artifact store 위치
- 인증/비밀값
- backup
- retention
- local/dev/prod 환경 차이

이건 단순 라이브러리 추가가 아니라 **서비스 하나를 더 운영하는 수준**에 가깝습니다.

## 6. 오류가 날 수 있는 방향과 실패 시나리오

아래는 현재 코드 구조를 기준으로 “어떻게 망가질 수 있는가”를 분류한 목록입니다.

### 6.1 멀티프로세스 학습 로그 충돌

현재 학습 스크립트는 `torch.multiprocessing` 기반 persistent worker 구조를 사용합니다.  
이 상태에서 worker 프로세스가 잘못 MLflow logging을 호출하면 다음 문제가 날 수 있습니다.

- 동일 run에 child process가 중복 logging
- run 중복 생성
- metric 순서 꼬임
- backend store lock 경합

**특히 중요한 점**: MLflow logging은 반드시 main process에서만 하도록 명확히 제한해야 합니다.

### 6.2 SQLite 기반 MLflow 서버 사용 시 잠금/경합

로컬에서 쉽게 시작하려고 MLflow backend store를 SQLite로 잡을 가능성이 큽니다.  
그런데 현재 학습 스크립트는 metric logging이 비교적 자주 일어나고, snapshot 저장도 겹칩니다.

이때 다음 문제가 날 수 있습니다.

- DB is locked
- run write 지연
- artifact logging 타임아웃

즉, **개발 편의성 때문에 SQLite로 시작하는 것은 가능하지만, 공유 사용이나 빈번한 logging에는 취약**합니다.

### 6.3 artifact path 불일치

현재 backend는 실제 파일 basename과 sidecar를 기준으로 서빙합니다.  
그런데 MLflow artifact만 믿고 다음처럼 운영하면 문제가 생깁니다.

- MLflow에는 artifact URI만 존재
- 로컬 `PuCo_RL/models/*.pth`에는 동일 basename이 없음
- sidecar JSON도 없음

이 경우 backend의 `model_registry.py`는 모델을 해석하지 못하거나, bootstrap allowlist 바깥에서 실패합니다.

즉, **MLflow artifact가 있다고 해서 backend가 바로 그 모델을 쓸 수 있는 것은 아닙니다.**

### 6.4 sidecar / registry 불일치

현재 backend는 `obs_dim`, `action_dim`, `architecture`를 꽤 중요하게 봅니다.  
만약 MLflow params와 sidecar JSON이 다르면 다음이 생깁니다.

- MLflow에는 `phase_ppo`로 기록
- sidecar에는 `ppo_residual`
- backend wrapper 검증에서 incompatibility 발생

즉, MLflow는 보조 기록일 뿐이고, **현재 서빙 계약은 여전히 sidecar가 더 중요**합니다.

### 6.5 runtime lineage 분리 심화

현재도 이미 아래가 따로 움직입니다.

- DB commit
- `MLLogger` JSONL
- `ReplayLogger`

여기에 MLflow logging까지 비동기/별도 타이밍으로 추가되면 다음 현상이 생길 수 있습니다.

- DB에는 반영됐는데 MLflow에는 없음
- MLflow run에는 기록됐는데 실제 배포 모델 sidecar에는 없음
- 게임 runtime provenance와 학습 provenance가 서로 다른 이름 체계를 가짐

즉, **MLflow가 들어오면 lineage가 더 좋아질 수도 있지만, 연결 규칙 없이 붙이면 더 나빠질 수도 있습니다.**

### 6.6 대용량 artifact 남용

다음 데이터를 MLflow artifact로 습관적으로 밀어 넣기 시작하면 곧바로 무거워집니다.

- per-game JSONL
- replay JSON
- 장기간 평가 replay 묶음
- checkpoint snapshot 다수

이 프로젝트는 이미 로그 산출물이 많기 때문에, MLflow에는 아래만 올리는 것이 적절합니다.

- 학습 run 산출 checkpoint
- sidecar JSON
- 요약 리포트
- convergence plot

반대로 per-game raw logs는 기존 체계에 두는 편이 낫습니다.

### 6.7 secret/config 운영 오류

MLflow를 Docker에 추가하면 다음이 늘어납니다.

- tracking URI
- backend store URI
- artifact root
- 인증값
- volume

현재 프로젝트는 `.env`에 이미 DB/Redis/OAuth/모델 파일명이 들어 있습니다.  
여기에 MLflow 관련 설정까지 들어가면 로컬/운영 환경 차이로 인한 misconfiguration 가능성이 커집니다.

### 6.8 모델 승격 혼선

가장 흔한 운영 사고는 “MLflow stage와 실제 서빙 모델이 다르다”는 문제입니다.

예:

- MLflow Registry: `Production`
- `.env`: 예전 `PPO_MODEL_FILENAME`
- backend 실제 로딩 모델: 로컬 디스크의 이전 파일

이 상태가 되면 운영자가 UI상으로 보는 champion과 실제 게임 서버가 쓰는 champion이 달라질 수 있습니다.

### 6.9 HPPO naming drift 확산

현재 HPPO 관련 이름이 이미 흔들리고 있으므로, MLflow experiment/model naming을 도입하면 그 흔들림이 데이터에 영구 반영될 수 있습니다.

예:

- 어떤 run은 `HPPO`
- 어떤 run은 `PhasePPO`
- 어떤 run은 `HierarchicalAgent`

이렇게 쌓이면 나중에 비교나 통계가 매우 어려워집니다.

## 7. 권장 결론과 단계별 도입안

### 최종 권고

### 권장

**MLflow는 학습/평가 계층에만 1차 도입**합니다.

- 학습 실험 기록
- 평가 리포트 연결
- checkpoint/sidecar provenance
- champion 선정 근거 정리

### 비권장

아래는 지금 하지 않는 것이 맞습니다.

- backend request path에서 MLflow 서버를 직접 조회하는 구조
- per-game runtime JSONL/replay를 MLflow 정본으로 대체하는 구조
- MLflow Registry를 sidecar 없이 곧바로 serving source로 삼는 구조

즉, MLflow는 **runtime source of truth가 아니라 experiment ledger**로 써야 합니다.

### 단계별 도입안

### Phase 1. 학습 run 추적만 붙이기

대상:

- PPO 학습 스크립트
- PhasePPO 학습 스크립트

기록 대상:

- params
- metrics
- checkpoint path
- sidecar JSON 경로
- git commit
- env summary

규칙:

- MLflow logging은 main process만 수행
- checkpoint 저장 후 run artifact에 요약 정보만 기록
- 서빙 계약은 계속 sidecar 기준 유지

### Phase 2. 평가 계층 연결

대상:

- tournament 결과
- convergence 결과
- 주요 평가 리포트

목표:

- champion 선정 근거를 run/tag 수준에서 정리
- 학습 run과 평가 run을 연결

### Phase 3. sidecar schema 확장 검토

이 단계에서만 선택적으로 아래 필드를 sidecar에 추가 검토합니다.

- `mlflow_run_id`
- `mlflow_experiment`
- `mlflow_artifact_uri`
- `git_commit`
- `training_data_snapshot`

또한 `games.model_versions` snapshot에 이 필드를 read-only로 포함할 수 있습니다.  
단, **backend 로딩은 계속 `filename + sidecar` 기준 유지**가 안전합니다.

### Phase 4. Registry 연동 검토

이 단계는 나중 문제입니다.

선행 조건:

- HPPO naming 정리
- sidecar 자동 생성 정리
- artifact storage 정책 정리
- champion promotion workflow 정리

이전 단계가 안정화되기 전까지는 **MLflow Registry를 운영 정본으로 쓰지 않는 것**이 좋습니다.

## 8. Public Interfaces / 후보 스키마 변화

문서 시점에서는 런타임 API를 바꾸지 않습니다.  
다만 향후 바뀔 수 있는 인터페이스 후보는 아래 정도입니다.

### sidecar metadata 후보 필드

```json
{
  "mlflow_run_id": "optional",
  "mlflow_experiment": "optional",
  "mlflow_artifact_uri": "optional",
  "git_commit": "optional",
  "training_data_snapshot": "optional"
}
```

### `games.model_versions` snapshot 확장 후보

현재 snapshot은 대체로 다음 정보를 담습니다.

- `artifact_name`
- `checkpoint_filename`
- `architecture`
- `metadata_source`

향후에는 아래 정도를 read-only로 포함할 수 있습니다.

- `mlflow_run_id`
- `mlflow_artifact_uri`
- `git_commit`

하지만 이 필드는 운영 lineage를 보강하는 용도일 뿐, **runtime loading contract의 핵심은 계속 sidecar/filename이어야 합니다.**

## 9. 도입 전 선행 조건

MLflow를 붙이기 전에 아래 정리가 먼저 필요합니다.

1. **HPPO naming 정리**
   - `HierarchicalAgent` vs `PhasePPOAgent`
   - experiment/model family 명명 기준 통일

2. **체크포인트 저장 규칙 통일**
   - `models/` vs `models/ppo_checkpoints/` 정리
   - basename 규칙 확정

3. **sidecar 생성 경로 복구 또는 명문화**
   - 문서와 실제 코드가 일치하도록 정리

4. **run naming 규칙 통일**
   - `PPO`
   - `PhasePPO`
   - `HPPO`
   - family / architecture / stage 명칭 규칙 고정

이 선행 작업 없이 MLflow부터 붙이면, 기록은 쌓이지만 신뢰도는 낮을 가능성이 큽니다.

## 10. 최종 판단

### 지금 바로 해도 되는 것

- 학습/평가용 MLflow 도입 검토
- run/metric/artifact 비교 UI 확보
- sidecar discipline 강화

### 지금 하면 안 되는 것

- MLflow를 runtime authoritative store처럼 쓰는 것
- backend 서빙 경로를 MLflow 중심으로 즉시 재설계하는 것
- per-game JSONL/replay를 MLflow artifact로 대량 이관하는 것

### 최종 판단 문장

**현재 Castone은 MLflow가 “필요 없는 프로젝트”는 아니지만, “전면 도입하면 곧바로 좋아지는 프로젝트”도 아닙니다.**  
가장 안전한 방향은 **학습/평가 추적에만 제한적으로 붙이고, runtime 정본과 serving 계약은 기존 DB/sidecar 중심 구조를 유지하는 것**입니다.

그 후에 HPPO naming, sidecar 자동화, artifact naming이 안정되면 Model Registry 연동을 검토하는 순서가 맞습니다.
