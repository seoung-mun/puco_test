# Mayor Docker Runtime TDD Report

작성일: 2026-04-06

## 목적

Mayor 계약 이슈를 Docker 실행 환경 기준으로 다시 검증하고, 무엇이 실사용 blocker인지와 무엇이 테스트 drift인지 분리한다.

## Docker 기준 결론

Docker 기준으로 다시 보면 "Mayor 전체가 다 깨져 있다"기보다는 두 종류의 문제가 섞여 있었다.

1. 실사용 blocker
- modern channel Mayor 경로에서 island `slot_id` naming이 serializer와 orchestrator 사이에서 달랐다.
- 프론트는 `island:corn:0`을 보내는데, orchestrator는 `island:corn_plantation:0`을 기대했다.
- 이 문제는 실제 human turn의 Mayor 토글 확정 요청을 실패시킬 수 있는 production bug였다.

2. 테스트 drift
- legacy `TestMayorDistributeErrorFormat`은 `[1] * 24`가 항상 invalid일 것이라고 가정했다.
- 하지만 현재 엔진/fixture에서는 그 입력이 더 이상 자동으로 invalid가 아니다.
- 따라서 실패 원인은 "legacy adapter가 무조건 잘못됐다"라기보다 "테스트가 숨은 보드 상태를 가정했다"는 쪽이 더 정확했다.

3. flaky fixture
- `mayor_can_skip` 테스트는 `game.current_player_idx`만 직접 바꾸고 PettingZoo AEC cursor(`agent_selection`)를 deterministic하게 맞추지 않아 runtime과 다른 상태를 만들 수 있었다.
- 이 문제는 production bug보다 test fixture 품질 문제에 가깝다.

## Brainstorming 관점 정리

Mayor 계약은 아래 세 층이 동시에 맞아야 한다.

1. Frontend payload contract
- 프론트는 serializer가 내려준 `slot_id`를 그대로 modern Mayor API에 보낸다.

2. Backend validation contract
- orchestrator는 그 `slot_id`를 현재 플레이어의 slot catalog와 비교해 검증한다.

3. Engine turn/mask contract
- Mayor skip 가능 여부와 각 배치 수용량은 현재 player cursor와 AEC agent cursor가 일치한 상태에서 해석돼야 한다.

즉, 문제를 "legacy냐 아니냐"로만 보면 놓친다.
실제 중요한 것은:

- serializer가 준 식별자가 validator에서 그대로 통과하는가
- 현재 Mayor turn의 action mask가 runtime cursor와 일치하는가
- legacy 테스트가 보드 상태를 암묵적으로 가정하지 않는가

## TDD로 반영한 수정

### 1. modern 실사용 계약 테스트 추가

추가한 테스트:
- `test_mayor_serializer_island_slot_ids_are_accepted_by_orchestrator`

의미:
- 프론트가 받은 island `slot_id`를 서버가 그대로 받아야 한다는 실제 human flow를 고정한다.

### 2. legacy 테스트를 real-world invalid case로 교체

변경 내용:
- `[1] * 24` 같은 암묵적 invalid 입력 대신,
- 현재 state를 보고 실제 존재하는 슬롯의 `capacity + 1`을 보내는 helper로 바꿨다.

의미:
- legacy 진단 테스트가 "숨은 초기 보드 가정"이 아니라 "명시적인 over-capacity 오류"를 검증하게 됐다.

### 3. Mayor fixture를 deterministic하게 정리

변경 내용:
- `governor_idx=0`으로 고정
- Mayor 테스트 준비 후 `agent_selection`도 현재 player와 일치시킴

의미:
- action mask 관련 테스트가 우연한 초기 governor 상태에 흔들리지 않게 됐다.

## 코드 수정 설계

### 반영한 production 수정

- `backend/app/services/mayor_orchestrator.py`
  - island slot catalog 생성 시 short tile name(`corn`, `indigo` 등)을 사용하도록 정렬

- `backend/app/services/state_serializer.py`
  - island `slot_id` 생성 시 orchestrator와 같은 helper를 사용하도록 정렬

### 설계 원칙

- `slot_id` string format은 한 곳에서 정의하고, serializer와 validator가 공유해야 한다.
- runtime contract를 tests가 따라가야지, tests 때문에 hidden adapter behavior를 유지하면 안 된다.

## 검증 결과

Docker에서 실행:

```bash
docker compose exec backend pytest -q tests/test_legacy_features.py tests/test_todo_priority1_task1_mayor_contract.py tests/test_channel_mayor_distribute.py
```

결과:
- `36 passed, 1 skipped`

## 남은 권고

1. Mayor `slot_id` helper를 contract-level shared utility로 더 명시화
2. PettingZoo AEC cursor를 직접 만지는 테스트 helper에는 항상 cursor sync를 포함
3. legacy tests는 "현재 실사용 경로 보장"이 아니라 "diagnostic adapter 품질 보장"으로 역할을 좁혀 유지
