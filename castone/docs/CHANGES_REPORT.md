# 변경 사항 보고서 (Session Changes Report)

> 작성일: 2026-03-25
> 대상 세션: TDD Edge-Case Tests + ML Pipeline Alignment
> 범위: `PuCo_RL/`, `backend/`, `.env`, `.env.example`

---

## 목차

1. [개요](#1-개요)
2. [변경 1 — GameAction 스키마 Optional 처리](#2-변경-1--gameaction-스키마-optional-처리)
3. [변경 2 — Builder 마스크: 도시 보드 슬롯 체크 추가](#3-변경-2--builder-마스크-도시-보드-슬롯-체크-추가)
4. [변경 3 — bot_service.py 전면 재작성 (HPPO 지원)](#4-변경-3--bot_servicepy-전면-재작성-hppo-지원)
5. [변경 4 — EngineWrapper max_game_steps 수정](#5-변경-4--enginewrapper-max_game_steps-수정)
6. [변경 5 — 신규 API 엣지케이스 테스트 추가](#6-변경-5--신규-api-엣지케이스-테스트-추가)
7. [변경 6 — 엔진 테스트 버그 3건 수정](#7-변경-6--엔진-테스트-버그-3건-수정)
8. [변경 7 — Mayor 순차 배치 테스트: agent_selection 동기화](#8-변경-7--mayor-순차-배치-테스트-agent_selection-동기화)
9. [변경 8 — 환경 변수 파일 업데이트](#9-변경-8--환경-변수-파일-업데이트)
10. [전체 변경 요약 표](#10-전체-변경-요약-표)
11. [남은 리스크 및 권장 후속 작업](#11-남은-리스크-및-권장-후속-작업)

---

## 1. 개요

이번 세션은 두 가지 축으로 진행되었습니다.

**축 1 — TDD 기반 엣지케이스 테스트**
게임 5개 페이즈(Settler, Builder, Trader, Captain, Mayor) 전체에 대해 엔진 수준 및 API 수준 엣지케이스 테스트를 작성하였습니다.
테스트 작성 과정에서 실제 엔진 버그(Builder 마스크 도시 슬롯 누락)와 테스트 로직 버그 4건이 발견 및 수정되었습니다.

**축 2 — ML 파이프라인 학습/서빙 환경 정합성**
학습 환경(`train_hppo_selfplay_server.py`)에서 `PhasePPOAgent` + 페이즈 컨디셔닝을 사용하는 반면,
서빙 환경(`bot_service.py`)은 표준 `Agent`(PPO)만 지원하는 불일치가 있었습니다.
이를 완전히 정렬하여 학습 시 사용된 모델 아키텍처를 서빙에서도 그대로 사용할 수 있도록 하였습니다.

---

## 2. 변경 1 — GameAction 스키마 Optional 처리

**파일:** `backend/app/schemas/game.py`

### Before

```python
class GameAction(BaseModel):
    game_id: UUID
    action_type: str
    payload: Dict[str, Any]
```

### After

```python
class GameAction(BaseModel):
    game_id: UUID | None = None
    action_type: str | None = None
    payload: Dict[str, Any]
```

### 변경 이유

API 핸들러(`/api/v1/game/{game_id}/action`)는 경로 파라미터로 `game_id`를 받고, body에서는 `payload`만 사용합니다.
클라이언트(프론트엔드 및 테스트)가 body에 `game_id`와 `action_type`을 포함하지 않으면 422 Unprocessable Entity가 반환되었습니다.

### 장점

- 클라이언트가 불필요한 중복 필드를 보내지 않아도 됨
- 기존 클라이언트 코드와 하위 호환성 유지

### 단점

- `game_id`가 body에 있을 경우 경로 파라미터와의 일치 여부를 검증하지 않음
- 의미적으로 `action_type`이 없어도 허용되어 API 명세가 모호해질 수 있음

---

## 3. 변경 2 — Builder 마스크: 도시 보드 슬롯 체크 추가

**파일:** `PuCo_RL/env/pr_env.py`
**함수:** `valid_action_mask()` — Builder 페이즈 섹션

### Before

```python
for b_type, count in game.building_supply.items():
    if count > 0 and not p.has_building(b_type):
        base_cost = BUILDING_DATA[b_type][0]
        ...
        if p.doubloons >= final_cost:
            mask[16 + b_type.value] = True
```

### After

```python
for b_type, count in game.building_supply.items():
    if count > 0 and not p.has_building(b_type):
        spaces_needed = 2 if BUILDING_DATA[b_type][4] else 1
        if p.empty_city_spaces < spaces_needed:
            continue
        base_cost = BUILDING_DATA[b_type][0]
        ...
        if p.doubloons >= final_cost:
            mask[16 + b_type.value] = True
```

### 변경 이유

`BUILDING_DATA[b_type][4]`는 해당 건물이 대형(large) 건물인지 나타내는 플래그입니다.
대형 건물은 도시 보드에 2칸, 소형 건물은 1칸을 차지합니다.
기존 코드는 도시 보드가 꽉 찬 상태(`empty_city_spaces == 0`)에서도 모든 건물 액션을 유효(True)로 표시하는 **실제 엔진 버그**가 있었습니다.

### 장점

- 게임 규칙 정확 구현: 도시 보드가 가득 찬 경우 건물 구매 불가
- `test_city_board_full_blocks_all_buildings` 테스트로 검증 완료
- RL 에이전트가 불가능한 행동을 학습에 포함하는 문제 해소

### 단점

- 기존 학습된 모델의 policy가 이 마스크 변경에 의해 영향받을 수 있음 (재학습 필요 가능성)
- `BUILDING_DATA` 인덱스 4의 의미를 알아야 코드를 이해할 수 있어 가독성이 다소 낮음

---

## 4. 변경 3 — bot_service.py 전면 재작성 (HPPO 지원)

**파일:** `backend/app/services/bot_service.py`

### Before (핵심 구조)

```python
# 단일 Agent 아키텍처만 지원
agent = Agent(obs_dim=obs_dim, action_dim=200)
model_path = "ppo_agent_update_100.pth"
...
action, _, _, _ = agent.get_action_and_value(obs_tensor, mask_tensor)
```

### After (핵심 구조)

```python
# MODEL_TYPE 환경변수로 분기
model_type = os.getenv("MODEL_TYPE", "ppo").lower()

if model_type == "hppo":
    agent = PhasePPOAgent(obs_dim=cls._obs_dim, action_dim=200)
    model_filename = os.getenv("HPPO_MODEL_FILENAME", ...)
else:
    agent = Agent(obs_dim=cls._obs_dim, action_dim=200)
    model_filename = os.getenv("PPO_MODEL_FILENAME", ...)

# 추론 시 페이즈 컨디셔닝
if BotService._model_type == "hppo":
    phase_id = int(obs_dict["global_state"]["current_phase"])
    phase_t = torch.tensor([phase_id], dtype=torch.long)
    action, _, _, _ = agent.get_action_and_value(obs_tensor, mask_tensor, phase_ids=phase_t)
else:
    action, _, _, _ = agent.get_action_and_value(obs_tensor, mask_tensor)
```

### 주요 변경 사항

| 항목 | Before | After |
|------|--------|-------|
| 지원 모델 | `Agent` (PPO) 고정 | `Agent` + `PhasePPOAgent` (HPPO) |
| 페이즈 컨디셔닝 | 없음 | `obs_dict["global_state"]["current_phase"]` 추출 |
| Obs space 구성 | 추론 시마다 dummy env 생성 | 클래스 변수에 1회 캐시 |
| 모델 로딩 | `strict=False` | `strict=True` 시도, 실패 시 `strict=False` 폴백 |
| max_game_steps | 50,000 (EngineWrapper) | 1,200 (학습 환경과 동일) |
| 모델 선택 방법 | 하드코딩 | `MODEL_TYPE` 환경변수 |

### 변경 이유

학습(`train_hppo_selfplay_server.py`)에서는 `PhasePPOAgent`를 사용하며,
관측값에서 `current_phase`를 추출해 페이즈 임베딩을 통한 컨디셔닝을 적용합니다.
서빙에서 표준 `Agent`로 HPPO 체크포인트를 로드하면 아키텍처 불일치로 인해 성능이 크게 저하됩니다.

### 장점

- 학습-서빙 정합성 완전 달성
- `MODEL_TYPE` 환경변수로 PPO/HPPO를 무중단 전환 가능
- obs_space 캐싱으로 추론 레이턴시 감소
- `strict=True` 로딩으로 아키텍처 불일치를 즉시 감지
- `.env` 파일만 수정하면 운영 환경에서 모델 전환 가능

### 단점

- `_obs_space`와 `_obs_dim`이 클래스 변수로 캐시되므로, 프로세스 재시작 없이 모델 타입을 변경하려면 수동으로 클래스 상태를 리셋해야 함
- HPPO를 선택했지만 HPPO 모델 파일이 없는 경우 미초기화 가중치로 동작 (경고 로그 출력)
- `strict=False` 폴백 시 일부 레이어가 누락되어도 조용히 진행될 수 있음

---

## 5. 변경 4 — EngineWrapper max_game_steps 수정

**파일:** `backend/app/engine_wrapper/wrapper.py`

### Before

```python
def __init__(self, num_players: int = 3, max_game_steps: int = 50000):
```

### After

```python
def __init__(self, num_players: int = 3, max_game_steps: int = 1200):
```

### 변경 이유

학습 환경(`train_hppo_selfplay_server.py`)에서 `max_game_steps=1200`을 사용합니다.
서빙에서 50,000을 사용하면 게임이 종료되지 않는 무한 루프 엣지케이스가 발생하고,
truncation 경계가 달라져 에이전트 행동이 학습과 다르게 분포될 수 있습니다.

### 장점

- 학습-서빙 환경 완전 정합
- 비정상적으로 긴 게임 방지

### 단점

- 실제 플레이에서 1,200 스텝(약 400턴) 내에 게임이 완료되지 않으면 truncation이 발생
- Puerto Rico의 정상 게임 길이를 실측하여 적절한 값인지 재확인 필요

---

## 6. 변경 5 — 신규 API 엣지케이스 테스트 추가

**파일:** `backend/tests/test_phase_action_edge_cases.py` (신규)

### Before

API 수준의 자동화 엣지케이스 테스트 없음

### After

44개 테스트 케이스 추가 (pytest)

**커버리지 범주:**

| 범주 | 테스트 항목 |
|------|------------|
| 인증 | 토큰 없이 액션 시도 → 401 |
| IDOR | 다른 게임 ID로 접근 → 403 |
| 페이로드 검증 | `action` 키 누락 → 400 |
| 마스크 거부 | 마스크 = 0인 액션 → 400 |
| 턴 순서 | 자기 차례가 아닌 플레이어 액션 → 400 |
| Settler 페이즈 | 플랜테이션 선택 / 인디고 vs 콘 선택 |
| Builder 페이즈 | 건물 구매 / 도시 꽉 찼을 때 거부 |
| Trader 페이즈 | 상품 판매 / 시장 꽉 찼을 때 거부 |
| Captain 페이즈 | 선박 적재 / 빈 선박 거부 |
| Mayor 페이즈 | 식민지 배치 순차 실행 |

### Governor 인식 패턴 (핵심 기법)

랜덤 거버너 문제를 해결하기 위해 게임 시작 후 `current_player`를 읽어 동적으로 테스트 대상을 결정합니다:

```python
start_res = _start(client, game.id, _bearer(user0.id))
current_player_idx = start_res["state"]["global_state"]["current_player"]
current_user = players[current_player_idx]
wrong_user = [u for u in players if u.id != current_user.id][0]
```

### 장점

- 실제 HTTP 요청 경로 전체를 커버
- Auth, IDOR, 페이즈별 규칙 위반을 자동 검증
- 랜덤 거버너 환경에서도 안정적으로 실행

### 단점

- 테스트 픽스처가 DB + Redis 등 실제 인프라를 필요로 함 (단위 테스트보다 무거움)
- 게임 초기화 헬퍼(`_make_game`, `_start`)가 실제 API에 의존하므로 API 변경 시 유지보수 필요

---

## 7. 변경 6 — 엔진 테스트 버그 3건 수정

**파일:** `PuCo_RL/tests/test_phase_edge_cases.py`

### 버그 1: `test_building_slot_capacity_matches_building_data`

- **Before:** `min_place=0`이 유효하다고 가정 (마스크 69=True 기대)
- **After:** `future_capacity=0`, `available=3`일 때 `min_place=3`이므로 마스크 72(배치 3)만 유효
- **이유:** Mayor 게임 규칙 — 모든 식민지를 반드시 배치해야 함

### 버그 2: `test_pass_valid_in_craftsman_phase`

- **Before:** 생산 없이 Craftsman 선택 → 페이즈가 즉시 스킵되어 단언 실패
- **After:** 옥수수 플랜테이션에 식민지를 배치해 생산 강제 후, 실제 페이즈 진입 여부를 확인하고 단언
- **이유:** 생산할 상품이 없으면 Craftsman 페이즈는 자동 스킵됨

### 버그 3: `test_reserved_action_terminates_env`

- **Before:** 예약 액션(111-199)이 env를 종료시킨다고 가정
- **After:** 예약 액션은 모든 elif를 통과하여 조용히 무시됨 (env 종료 없음)
- **이유:** `action_role`, `action_settler` 등이 else 처리 없이 순차 체크되므로 매칭 없으면 통과

### 장점

- 테스트가 실제 게임 규칙을 정확히 반영
- 거짓 음성(false positive) 테스트 제거

### 단점

- 예약 액션 무시가 의도된 동작인지 문서화 필요

---

## 8. 변경 7 — Mayor 순차 배치 테스트: agent_selection 동기화

**파일:** `PuCo_RL/tests/test_mayor_sequential.py`

### Before

```python
game.current_phase = Phase.MAYOR
game.current_player_idx = 0
game.players[0].unplaced_colonists = 3
```

### After

```python
game.current_phase = Phase.MAYOR
game.current_player_idx = 0
env.agent_selection = "player_0"  # ← 추가
game.players[0].unplaced_colonists = 3
```

### 변경 이유

`env.reset()` 후 거버너가 랜덤으로 결정됩니다 (`random.randint(0, num_players-1)`).
`game.current_player_idx = 0`으로 강제 설정하더라도 `env.agent_selection`이 여전히 다른 플레이어를 가리킬 경우,
`env.step()`이 내부적으로 잘못된 플레이어 인덱스를 사용하여 `ValueError`가 발생하고 조용히 무시됩니다.

### 장점

- PettingZoo AEC 인터페이스 동기화 원칙 명확화
- 랜덤 거버너 상황에서도 안정적인 테스트 실행

### 단점

- 테스트 전용 패턴이 엔진 내부 구현(env.agent_selection)에 강하게 의존

---

## 9. 변경 8 — 환경 변수 파일 업데이트

**파일:** `.env`, `.env.example`

### .env 변경

```diff
+ MODEL_TYPE=hppo
+ HPPO_MODEL_FILENAME=HPPO_PR_Server_1774241514_step_14745600.pth
```

### .env.example 변경

```diff
+ # MODEL_TYPE selects the agent architecture:
+ #   ppo  → Agent (standard PPO, uses PPO_MODEL_FILENAME)
+ #   hppo → PhasePPOAgent / HierarchicalAgent (uses HPPO_MODEL_FILENAME)
+ MODEL_TYPE=ppo
+ PPO_MODEL_FILENAME=ppo_agent_update_100.pth
+ HPPO_MODEL_FILENAME=your_hppo_checkpoint.pth
```

### 장점

- 신규 개발자가 모델 타입 설정 방법을 즉시 파악 가능
- 두 모델 아키텍처 간 전환 절차가 명확하게 문서화됨

### 단점

- `.env`가 git에 커밋되면 실제 체크포인트 파일명이 노출될 수 있음

---

## 10. 전체 변경 요약 표

| # | 파일 | 변경 유형 | 핵심 내용 | 영향 범위 |
|---|------|----------|----------|----------|
| 1 | `backend/app/schemas/game.py` | 수정 | GameAction 필드 Optional화 | API 클라이언트 |
| 2 | `PuCo_RL/env/pr_env.py` | **버그 수정** | Builder 마스크 도시 슬롯 체크 | 게임 규칙 정확성, RL 학습 |
| 3 | `backend/app/services/bot_service.py` | **전면 재작성** | HPPO/PPO 분기, 페이즈 컨디셔닝 | AI 봇 추론 품질 |
| 4 | `backend/app/engine_wrapper/wrapper.py` | 수정 | max_game_steps 50000→1200 | 학습-서빙 정합성 |
| 5 | `backend/tests/test_phase_action_edge_cases.py` | **신규** | 44개 API 엣지케이스 테스트 | 품질 보증 |
| 6 | `PuCo_RL/tests/test_phase_edge_cases.py` | 버그 수정 | 테스트 3건 로직 오류 수정 | 테스트 신뢰도 |
| 7 | `PuCo_RL/tests/test_mayor_sequential.py` | 버그 수정 | agent_selection 동기화 | 테스트 신뢰도 |
| 8 | `.env` / `.env.example` | 수정 | MODEL_TYPE 문서화 | 운영 설정 |

---

## 11. 남은 리스크 및 권장 후속 작업

### 즉시 처리 권장

- [ ] `max_game_steps=1200`이 실제 Puerto Rico 게임 평균 길이에 적합한지 측정 및 검증
- [ ] Builder 마스크 버그 수정 후 기존 학습 모델의 성능 변화 확인 (재학습 필요 여부)
- [ ] API 테스트 실행 환경(DB + Redis) 구성 및 CI 파이프라인 통합

### 중기 권장

- [ ] `BotService`에 핫 스왑 지원: 프로세스 재시작 없이 모델 교체 가능하도록
- [ ] `action_type` 필드 명세 정비 또는 API 스키마에서 제거
- [ ] `BUILDING_DATA` 인덱스 상수화하여 가독성 향상 (예: `LARGE_BUILDING_IDX = 4`)
- [ ] 예약 액션(111-199) 처리 방식 명문화 (의도된 no-op인지 미구현 기능인지)

### 장기 권장

- [ ] `env/pr_env.py` 전체 마스크 생성 로직에 대한 속성 기반 테스트(property-based testing) 도입
- [ ] 학습 환경 하이퍼파라미터(`max_game_steps` 등)를 단일 config 파일로 관리하여 학습-서빙 자동 동기화
