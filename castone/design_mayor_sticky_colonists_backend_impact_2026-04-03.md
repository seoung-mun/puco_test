# Mayor Sticky Colonists 설계 보고서

작성일: 2026-04-03  
범위: `PuCo_RL/env/engine.py` 규칙 변경이 필요해질 경우, `backend/`와 `frontend/` 계약을 어떻게 바꿔야 하는지에 대한 상세 설계  
전제: 코드 수정 없음. 본 문서는 설계안만 제시한다.

## 1. 문제 정의

현재 Mayor 페이즈는 "기존에 배치된 일꾼을 전부 회수한 뒤, 이번 Mayor에서 다시 전부 재배치"하는 모델이다.

핵심 구현은 다음 두 지점이다.

- [`Player.recall_all_colonists()`](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/player.py#L87)
- [`PuertoRicoGame._init_mayor_placement()`](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/engine.py#L332)

현재 흐름은 다음과 같다.

1. Mayor 역할 선택
2. 선출자 특권 이주민 지급
3. 배 위의 이주민 분배
4. 각 플레이어 차례 진입 시 `recall_all_colonists()`
5. 모든 섬/도시 슬롯을 다시 순차 재배치

그런데 운영/기획 측에서 다음과 같은 변경 아이디어가 제기되었다.

- 건설막, 소형상가, 채석장처럼 "한번 놓이면 보통 다시 빼지 않는" 슬롯은 고정 상태로 유지
- 전체 회수/전체 재배치가 아니라 "일부만 재배치"하는 모델로 완화

즉, Mayor를 다음 둘 중 하나로 바꾸고 싶은 것이다.

- 완전 재배치 모델 유지
- 부분 고정 + 일부 재배치 모델로 전환

이 문서는 두 번째 방향, 즉 "Sticky Colonists" 모델을 도입할 때 필요한 설계를 다룬다.

## 2. 현재 구현이 전제하는 구조

현재 엔진과 백엔드는 모두 "Mayor = 전부 회수 후 전부 재배치"를 강하게 전제하고 있다.

### 엔진 측 전제

- [`engine.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/engine.py)의 Mayor mask 계산은 "현재 슬롯 이후의 미래 수용량"을 계산해 `min_place ~ max_place`를 만든다.
- 이 계산은 "이미 이전 슬롯에 있던 일꾼들이 모두 비워진 상태"라는 가정을 깔고 있다.
- [`valid_action_mask()`](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/pr_env.py#L495)는 현재 슬롯의 수용량과 남은 수용량을 기반으로 유효 행동을 만든다.

### 백엔드 측 전제

- [`state_serializer.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py#L266) 는 `city.colonists_unplaced`를 현재 Mayor 재배치 풀처럼 사용한다.
- [`state_serializer.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py#L409) 는 `mayor_slot_idx`, `mayor_can_skip`를 순차 슬롯 UI용 메타로 노출한다.
- [`frontend/src/App.tsx`](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx#L168) 는 사람 차례일 때 24칸 전체를 대상으로 `mayorPending`을 만들고, 이전 배치를 다시 불러와 클리핑한다.
- [`frontend/src/App.tsx`](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx#L760) 는 24칸 전체에 대해 섬 12칸, 도시 12칸을 순회하며 액션을 보낸다.

즉, 현재 UI/Serializer/Mask/Engine이 전부 같은 가정을 공유한다.

- "Mayor 때는 현재 배치가 모두 풀린다"
- "플레이어는 다시 전체 배치를 짠다"
- "남은 미배치 이주민 수는 전체 재배치 풀이다"

따라서 `engine.py`만 고치면 끝나는 문제가 아니다.

## 3. 변경 목표

Sticky Colonists 모델의 목표는 다음과 같다.

1. 모든 일꾼을 자동 회수하지 않는다.
2. 특정 슬롯은 Mayor 진입 시 자동 유지된다.
3. 필요한 경우에만 일부 슬롯의 일꾼만 이동 대상이 된다.
4. 백엔드/프론트는 "현재 고정된 일꾼"과 "이번 Mayor에서 이동 가능한 일꾼"을 구분해서 보여줘야 한다.
5. 봇과 사람 모두 같은 규칙을 따라야 한다.

이때 중요한 것은 규칙의 정확한 정의다. "웬만하면 안 뺀다"는 말만으로는 구현이 불가능하다.

반드시 결정해야 할 룰 질문:

1. 어떤 슬롯을 자동 고정할 것인가
- 채석장만 고정할지
- 건설막/소형상가처럼 비생산 보라 건물도 고정할지
- 생산 건물은 재배치 허용할지

2. 고정 슬롯도 플레이어가 원하면 해제할 수 있는가
- 자동 고정 + 해제 불가
- 자동 고정 + 수동 해제 가능
- 추천: 자동 고정이 아니라 "기본 유지"만 하고 명시적 해제 액션 허용

3. 섬 타일도 고정 대상인가
- 채석장만 고정
- 모든 이미 점유된 섬 타일 고정
- 추천: 섬과 도시를 분리해 규칙 정의

4. 빈 슬롯 충원 우선순위는 어떻게 할 것인가
- 현재와 같이 순차
- 플레이어가 자유롭게 대상 슬롯 선택

이 중 어느 하나라도 정해지지 않으면 엔진/프론트/봇 설계가 흔들린다.

## 4. 권장 규칙 모델

본 문서의 권장안은 다음이다.

### 권장안 A: "Lock + Movable Pool" 모델

Mayor 시작 시 각 플레이어의 슬롯을 두 그룹으로 나눈다.

- Locked colonists: 자동 유지되는 일꾼
- Movable colonists: 이번 Mayor에서 다시 배치 가능한 일꾼

권장 규칙:

- 채석장, 건설막, 소형상가, 창고류, 항만류, 시장류 같은 "보조/인프라" 성격 슬롯은 기본 고정
- 생산계 건물 및 생산 타일은 이동 가능
- 단, 운영 규칙을 단순화하려면 1차 버전에서는 "고정 목록 기반"으로만 시작

즉, Mayor 진입 시 더 이상 `recall_all_colonists()`를 호출하지 않고 다음을 수행한다.

1. 각 슬롯을 순회
2. 슬롯이 sticky 대상이면 현재 점유 유지
3. sticky 대상이 아니면 점유를 풀고 movable pool로 회수
4. Mayor 동안은 movable pool만 재배치

이 방식의 장점:

- 기존 규칙을 전부 뒤엎지 않음
- 플레이어가 체감하는 귀찮은 전체 재배치를 줄일 수 있음
- 백엔드에서 "현재 유지 중인 점유"와 "이번에 이동 가능한 풀"을 명확하게 분리 가능

이 방식의 단점:

- 룰이 원작과 달라질 수 있음
- RL 환경과 기존 학습 모델의 정책 가정이 깨질 가능성이 큼

## 5. 엔진 설계 변경안

## 5.1 새 개념 도입

`PuertoRicoGame`에 다음 상태를 추가하는 것을 권장한다.

- `mayor_mode`: `"full_recall"` | `"sticky_redeploy"`
- `mayor_locked_slots`: 플레이어별 슬롯 잠금 정보
- `mayor_movable_pool`: 플레이어별 Mayor 재배치 가능 이주민 수
- `mayor_target_slots`: 플레이어별 이번 Mayor에서 배치 가능한 슬롯 목록

권장 자료구조 예시:

```python
self.mayor_mode = "sticky_redeploy"
self._mayor_locked_slots = {
    player_idx: {
        "island": [False] * 12,
        "city": [False] * 12,
    }
}
self._mayor_movable_pool = {player_idx: 0}
self._mayor_target_slots = {player_idx: []}
```

여기서 핵심은 `unplaced_colonists`를 더 이상 "Mayor 재배치 풀" 하나로만 쓰지 않는 것이다.

현재는 `unplaced_colonists`가 곧 Mayor 전체 재배치 풀이다. Sticky 모델에서는 의미가 달라진다.

추천:

- 일반 게임 규칙상 `unplaced_colonists`는 실제 미배치 일꾼만 의미하게 유지
- Mayor 중 일시적으로 사용할 재배치 풀은 `_mayor_movable_pool`로 분리

이 분리가 없으면 직렬화와 UI가 기존 의미를 계속 오해하게 된다.

## 5.2 Mayor 시작 처리 변경

현재:

- [`_init_mayor_placement()`](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/engine.py#L332) 진입 시 `recall_all_colonists()`

변경 후 권장:

1. `_prepare_mayor_for_player(player_idx)` 신규 도입
2. 플레이어 보드 스캔
3. sticky 슬롯과 movable 슬롯 분리
4. movable pool 계산
5. target slot sequence 생성
6. Mayor placement cursor 초기화

즉, 현재 `_init_mayor_placement()`는 아래처럼 분해하는 것이 맞다.

- `_prepare_mayor_for_player()`
- `_build_mayor_slot_sequence()`
- `_advance_to_next_mayor_slot()`

이유:

- 현재 구현은 "회수 + 순차 배치"가 한 덩어리로 묶여 있다.
- Sticky 규칙은 준비 단계와 액션 단계가 분리되어야 디버깅과 테스트가 가능하다.

## 5.3 Mayor slot capacity 계산 변경

현재 `_mayor_slot_capacity()`는 단순히 슬롯 자체의 최대 수용량만 본다.

Sticky 모델에서는 다음 둘을 분리해야 한다.

- `slot_max_capacity`
- `slot_current_locked`

실제 이번 Mayor에서 추가 배치 가능한 수는:

`available_capacity = slot_max_capacity - locked_colonists - already_redeployed_here`

예를 들어 소형상가가 sticky 대상이라 이미 1명이 잠겨 있으면:

- 최대 수용량 1
- 추가 배치 가능 0

따라서 기존 `_mayor_slot_capacity()`의 반환값은 의미가 달라진다.  
함수 자체를 재정의하거나, 다음처럼 분리하는 것이 좋다.

- `_mayor_slot_total_capacity()`
- `_mayor_slot_locked_count()`
- `_mayor_slot_available_capacity()`

## 5.4 Mayor mask 계산 변경

현재 [`valid_action_mask()`](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/pr_env.py#L616) 는

- 현재 슬롯 수용량
- 이후 슬롯 전체 수용량
- 현재 미배치 수

로 `min_place`와 `max_place`를 만든다.

Sticky 모델에서는 미래 수용량 계산 대상이 바뀐다.

- 이미 locked인 슬롯은 future capacity에서 제외
- 현재 target sequence에 포함되지 않은 슬롯도 제외
- 이미 완료된 target slot도 제외
- movable pool 기준으로 계산

즉, 현 mask 로직은 알고리즘 자체를 재작성해야 한다.

단순 패치로는 위험하다. 권장 방식은 다음이다.

1. `MayorAllocationView` 같은 내부 계산 구조를 만든다.
2. 여기에서 현재 cursor, movable pool, target slots, locked slots를 모두 본다.
3. mask는 이 구조에서만 계산한다.

그렇지 않으면 현재 코드처럼 섬/도시를 따로 스캔하는 로직이 계속 누더기가 된다.

## 5.5 액션 의미 재정의

현재 Mayor 액션은 사실상 "현재 슬롯에 0~3명 배치"다.

- 69~72: `amount = 0..3`

이 의미는 Sticky 모델에서도 유지 가능하다.  
다만 중요한 차이가 생긴다.

- 기존: "전체 재배치 중 현재 슬롯"
- 변경: "이동 가능 대상 슬롯 중 현재 슬롯"

따라서 액션 인덱스는 유지해도, 슬롯 선택 집합과 `mayor_slot_idx` 의미는 바뀐다.

이 부분을 프론트에 명시하지 않으면 UI는 기존 24칸 전체를 대상으로 오해한다.

## 6. backend 영향 범위

## 6.1 EngineWrapper

[`backend/app/engine_wrapper/wrapper.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py)

EngineWrapper 자체는 상태를 래핑할 뿐이라 직접 수정 범위는 작다. 그러나 다음은 확인해야 한다.

- `observe()`에서 들어오는 `action_mask` 의미 변화 반영
- `last_obs` 구조가 바뀌면 flatten 경로 영향 확인
- `process_action()`에서 Mayor 관련 invalid action이 늘어나지 않도록 검증

핵심:

- Wrapper는 큰 변경이 필요 없을 수 있지만,
- `env.observe()`에서 추가 메타가 생기면 serializable path가 안전한지 확인해야 한다.

## 6.2 State Serializer

가장 큰 영향은 [`backend/app/services/state_serializer.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py)다.

현재 노출 구조:

- `city.colonists_unplaced`
- `city.buildings[].current_colonists`
- `meta.mayor_slot_idx`
- `meta.mayor_can_skip`

Sticky 모델에서는 이걸로 부족하다.

추가가 필요한 필드:

- `meta.mayor_mode`
- `meta.mayor_cursor_slot`
- `meta.mayor_target_slots`
- `players[player].city.mayor_locked_buildings`
- `players[player].island.mayor_locked_plantations`
- `players[player].city.mayor_movable_pool`

권장 직렬화 예시:

```json
{
  "meta": {
    "phase": "mayor_action",
    "mayor_mode": "sticky_redeploy",
    "mayor_slot_idx": 13,
    "mayor_can_skip": false
  },
  "players": {
    "player_0": {
      "city": {
        "colonists_unplaced": 1,
        "mayor_movable_pool": 2,
        "buildings": [
          {
            "name": "small_market",
            "current_colonists": 1,
            "mayor_locked": true,
            "mayor_redeployable_capacity": 0
          }
        ]
      }
    }
  }
}
```

중요한 점:

- `colonists_unplaced`는 일반 게임 개념
- `mayor_movable_pool`는 이번 Mayor 임시 개념

둘을 분리하지 않으면 프론트와 봇이 같은 필드를 다른 의미로 읽게 된다.

## 6.3 GameService / WebSocket

[`backend/app/services/game_service.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)

이 레이어는 엔진을 직접 구현하지 않지만, 상태 전파 기준점이므로 계약 변경 영향을 크게 받는다.

확인 항목:

- `_build_rich_state()`가 새 Mayor 메타를 빠짐없이 포함하는지
- bot 차례 스케줄링 중 Mayor에서 `bot_thinking` 표시가 너무 길어지지 않는지
- `process_action()` 후 WS 상태가 sticky 관련 필드까지 안정적으로 전파되는지

특히 Mayor는 액션 한 번당 상태 변화가 미세해서 WS 디버깅이 어려우므로, 다음 로그가 필요하다.

- game_id
- actor_id
- current mayor cursor
- movable pool
- locked slots count
- emitted action_mask summary

## 6.4 프론트엔드 영향

실제 백엔드 계약 변경의 최종 소비자는 프론트다.

현재 프론트는 `mayorPending` 기반의 24칸 전체 재배치 UI를 사용한다.

문제 지점:

- [`frontend/src/App.tsx:168`](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx#L168)
- [`frontend/src/App.tsx:744`](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx#L744)
- [`frontend/src/App.tsx:760`](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx#L760)
- [`frontend/src/App.tsx:1030`](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx#L1030)

현재 UI는 다음 가정을 한다.

- 24칸 전체가 잠재 재배치 대상
- `colonists_unplaced`는 전체 Mayor 재배치 풀
- 사용자는 전체 계획을 한 번에 세우고, 프론트가 이를 슬롯별 액션으로 풀어서 전송

Sticky 모델에서는 이 UI가 오동작할 가능성이 높다.

권장 UI 변경:

1. "Locked" 시각화 추가
- 잠긴 슬롯은 잠금 아이콘 표시
- 클릭/토글 비활성화

2. "Movable pool" 수치 추가
- 현재 남은 재배치 가능 일꾼 수를 별도 표시

3. 전체 계획형 UI 대신 cursor 기반 UI 유지 여부 결정
- 최소 변경: 현재 순차 UI 유지
- 추천: 사람 플레이어도 "현재 슬롯만 결정"하는 순차 UI로 통일

추천 방향은 "사람 UI도 엔진 커서 기반 단일 슬롯 입력"으로 단순화하는 것이다.

이유:

- sticky 규칙이 들어오면 24칸 전체 사전 계획 UI가 오히려 더 복잡해진다.
- 엔진이 실제로 현재 커서만 허용하는데, 프론트가 전체 계획을 들고 있는 구조는 mismatch가 커진다.

## 7. 봇 영향

Sticky Mayor는 RL 입력 의미를 바꾼다.

현재 학습 모델은 다음 전제를 사실상 학습했을 가능성이 높다.

- Mayor 때 전체 회수 후 재배치
- 특정 슬롯 비우기/채우기 가치
- 미래 수용량 계산 방식

Sticky 모델로 바꾸면 다음이 달라진다.

- 관측값 분포
- Mayor 마스크 분포
- Mayor에서 가능한 행동 집합
- 생산 인프라 활성 상태의 유지 방식

즉, 기존 PPO/HPPO 모델은 Mayor에서 정책 붕괴가 날 수 있다.

따라서 선택지는 둘이다.

1. 모델 재학습을 전제로 한다
2. Sticky Mayor는 사람 전용 규칙으로 두고, 봇전에서는 기존 Full Recall을 유지한다

운영 복잡도를 줄이려면 1차는 2번이 더 안전하다.

즉 권장 운영 전략:

- `mayor_mode = full_recall` for existing bots
- `mayor_mode = sticky_redeploy` only in experimental or human-first mode

## 8. 권장 마이그레이션 전략

한 번에 바꾸면 위험하다. 단계적으로 도입해야 한다.

### 단계 1. 엔진 내부 추상화 도입

목표:

- 현재 Full Recall을 유지하되 Mayor 준비 로직을 함수로 분해

필수 작업:

- `recall_all_colonists()` 직호출 제거
- `_prepare_mayor_for_player()` 도입
- `_mayor_slot_*` 계산 함수 분리

이 단계에서는 동작 변화가 없어야 한다.

### 단계 2. 직렬화 계약 확장

목표:

- 새 필드를 먼저 내보내되, 기존 UI는 그대로 동작 가능하게 유지

추가 필드:

- `meta.mayor_mode`
- `player.city.mayor_movable_pool`
- `building.mayor_locked`

이 단계도 기본 동작은 기존과 같아야 한다.

### 단계 3. Sticky 모드 feature flag 도입

목표:

- 룸 단위 또는 서버 설정 단위로 Mayor 모드 선택 가능

추천:

- env option
- room config
- server env var

### 단계 4. 프론트 sticky UI 전환

목표:

- lock 표시
- movable pool 표시
- 현재 슬롯 입력 방식 정리

### 단계 5. bot 전략 분기 또는 재학습

목표:

- 기존 모델과 규칙 mismatch 제거

## 9. 테스트 전략

## 9.1 엔진 테스트

필수 테스트:

1. Sticky 대상 슬롯은 Mayor 시작 후 점유 유지
2. non-sticky 슬롯은 movable pool로 회수
3. movable pool 합계가 회수된 일꾼 수와 일치
4. 현재 슬롯 available capacity 계산이 locked count를 반영
5. Mayor 종료 후 locked + redeployed 총합이 일관
6. 기존 full_recall 모드와 sticky 모드를 분리 검증

## 9.2 serializer 테스트

필수 테스트:

1. `mayor_mode` 노출
2. `mayor_movable_pool` 노출
3. building/island별 `mayor_locked` 정확성
4. 기존 필드와 공존 시 타입 안정성 유지

## 9.3 frontend 계약 테스트

필수 테스트:

1. locked 슬롯 클릭 차단
2. movable pool과 남은 용량 계산 일치
3. sticky Mayor에서 전체 배치 계획 UI가 잘못 초기화되지 않음

## 9.4 회귀 테스트

반드시 다시 확인할 페이즈:

- Settler: Hospice/Construction Hut/Quarry 활성 상태
- Craftsman: 생산 건물 활성 여부
- Builder: Quarry/Construction Hut 할인 및 판단
- Captain: Harbor/Wharf 등 점유 기반 능력
- 최종 점수: Fortress/Guild Hall/City Hall 등

이유:

- Sticky Mayor는 "어떤 슬롯이 점유 상태로 남는가"를 바꾸므로, 거의 모든 점유 기반 규칙에 회귀 위험이 있다.

## 10. 리스크

가장 큰 리스크는 세 가지다.

1. 규칙 의미의 이중화
- 일부 슬롯은 locked, 일부는 movable인데 UI가 이 차이를 숨기면 사용자 혼란이 커진다.

2. 기존 RL 모델 무력화
- Mayor 관련 관측과 행동공간 분포가 바뀌므로, 기존 정책이 비정상적으로 흔들릴 수 있다.

3. 프론트/엔진 계약 불일치
- 현재 프론트는 전체 재배치 계획을 가정한다.
- 엔진이 sticky cursor 모델로 바뀌면 가장 먼저 깨질 가능성이 큰 곳이 프론트 Mayor UI다.

## 11. 최종 권고

Sticky Colonists는 `engine.py`만 바꾸는 작은 수정으로 보면 안 된다.  
실제로는 다음 세 층을 같이 설계해야 한다.

- 엔진의 Mayor 상태 모델
- 백엔드 serializer/WS 계약
- 프론트 Mayor UI/입력 방식

추천 순서는 다음이다.

1. 엔진 내부 Mayor 준비/용량 계산 로직을 먼저 분해
2. serializer에 새 Mayor 메타를 추가
3. sticky 모드를 feature flag로 도입
4. 프론트를 cursor 기반 단순 UI로 정리
5. 봇은 별도 모드 유지 또는 재학습 계획 수립

가장 안전한 1차 방안은 이렇다.

- 기본값은 `full_recall`
- `sticky_redeploy`는 실험 플래그로 도입
- 기존 봇전은 full_recall 유지
- 사람 플레이 또는 특정 실험 룸에서만 sticky 사용

이 접근이 현재 코드베이스의 결합도를 고려할 때 가장 현실적이다.
