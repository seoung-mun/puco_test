# Random Bot Trader/Captain 이상 행동 점검 및 해결 설계 보고서

작성일: 2026-04-03  
범위: "Random 봇전인데 상인/선장 페이즈에서 판매/선적을 거의 하지 않는다"는 현상을 점검하고, 원인 분리와 해결 순서를 설계한다.  
전제: 코드 수정 없음. 본 문서는 설계와 조사 결과만 정리한다.

## 1. 문제 정의

관찰된 현상:

- Random 봇전으로 인식되는 게임에서
- Trader 페이즈에서 물건을 팔지 않거나
- Captain 페이즈에서 선적하지 않고
- 행동을 하지 않는 것처럼 보인다

사용자 가설:

- Random인데 행동을 거의 안 하는 것은 이상하다
- 액션 마스킹이 잘못되어 유효 액션이 열리지 않는 것일 수 있다

이 문제는 바로 "mask 버그"라고 단정하면 안 된다. 현재 코드 기준으로는 최소 4개의 원인 후보가 있다.

1. 실제로는 Random 봇이 아닐 수 있다
2. Random 봇이 맞지만 Trader는 pass가 항상 허용되므로 우연히 자주 pass할 수 있다
3. Captain mask가 잘못 열려 pass가 허용될 수 있다
4. 봇은 정상 행동했지만 상태 전파 또는 UI 표시가 어긋날 수 있다

이 문서는 위 후보를 우선순위로 정리하고, 어떤 순서로 검증/수정해야 하는지 설계한다.

## 2. 핵심 조사 결과

## 2.1 Trader/Captain 액션 마스크 자체는 이미 테스트가 있다

`PuCo_RL` 테스트에는 Trader/Captain mask에 대한 명시적인 검증이 이미 들어 있다.

관련 파일:

- [`PuCo_RL/tests/test_phase_edge_cases.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/tests/test_phase_edge_cases.py)

중요한 검증:

- Trader에서는 pass가 항상 가능
- 재고가 없으면 판매 액션이 닫힘
- Office 없으면 중복 상품 판매 막힘
- Captain에서는 적재 가능할 때 pass가 막힘
- 선적 불가일 때만 pass가 열림
- Wharf 사용 가능/불가도 mask로 제어됨

특히 다음 테스트가 중요하다.

- `test_pass_always_valid` for Trader
- `test_pass_blocked_when_can_load` for Captain

즉, 현재 소스만 놓고 보면 "액션 마스크가 전혀 없다"는 해석은 맞지 않는다.

## 2.2 Trader는 원래 Random이 pass를 자주 뽑을 수 있다

[`valid_action_mask()`](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/pr_env.py#L495) 에서 Trader는 다음처럼 설계돼 있다.

- `mask[15] = True`
- 조건이 맞는 상품만 `39~43` 판매 액션 활성화

즉, Trader에서는 pass와 sell이 동시에 열릴 수 있다.  
진짜 Random이라면 판매 가능한 순간에도 pass를 꽤 자주 뽑을 수 있다.

따라서 "Trader에서 안 팔았다"만으로는 버그 증거가 아니다.

반대로 Captain은 다르다.

- 선적 가능하면 pass는 닫혀야 한다
- 선적 불가능할 때만 pass가 열려야 한다

그래서 Captain에서 반복적으로 아무것도 안 한다면, Trader보다 더 강한 이상 신호다.

## 2.3 가장 큰 구조적 문제: 채널 봇 서비스가 `bot_type`을 실제로 사용하지 않는다

이 부분이 현재 가장 중요한 설계 포인트다.

방 상태에는 `BOT_random`, `BOT_ppo`, `BOT_hppo` 같은 값이 저장된다.

관련 파일:

- [`backend/app/api/channel/room.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/room.py#L124)
- [`backend/app/api/channel/game.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/game.py#L74)
- [`backend/app/services/game_service.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py#L39)

하지만 실제 채널 봇 추론은 [`backend/app/services/bot_service.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py#L47) 가 담당하는데, 여기서는 전역 wrapper 하나만 쓴다.

현재 구조:

- `BotService._agent_wrapper` 싱글턴 하나
- `BotService.get_agent_wrapper()`는 환경변수 기반 모델 하나만 로드
- `BotService.get_action(game_context)`는 `bot_type` 인자를 받지 않음
- `run_bot_turn(game_id, engine, actor_id, ...)`도 `actor_id`를 받아도 그 안에서 `BOT_random`인지 `BOT_ppo`인지 해석하지 않음

즉, 현재 채널 모드에서 "화면에 Random Bot이라고 보이는 것"과 "실제로 RandomWrapper가 사용되는 것"은 별개일 수 있다.

이건 액션 마스크보다 우선해서 해결해야 할 구조 문제다.

## 2.4 레거시 경로와 채널 경로가 서로 다른 계약을 기대한다

레거시 경로에는 `bot_type`을 인자로 넘기려는 흔적이 남아 있다.

관련 파일:

- [`backend/app/api/legacy/deps.py`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/legacy/deps.py#L180)

여기서는 다음처럼 기대한다.

```python
action = BotService.get_action(bot_type, game_context)
```

하지만 실제 `BotService.get_action` 시그니처는 현재 다음이다.

```python
def get_action(game_context: Dict[str, Any]) -> int:
```

즉:

- 레거시는 `bot_type` 기반 라우팅을 기대
- 채널 BotService는 전역 wrapper 하나만 사용

이 드리프트는 "Random이라고 만들었는데 PPO처럼 행동하는" 현상을 충분히 만들 수 있다.

## 3. 현재 증상에 대한 우선순위 해석

현재 코드 상태에서 우선순위는 다음처럼 보는 것이 맞다.

### 1순위: 실제로 Random이 아닐 가능성

가장 먼저 확인해야 할 것은 "BOT_random 라벨이 붙어 있어도 실제 추론은 RandomWrapper로 가는가"다.

현재 구조상 채널 모드에서는 그 보장이 없다.

따라서 다음 현상은 모두 설명 가능하다.

- Random 봇전이라고 생각했는데 학습된 PPO wrapper가 행동
- Trader에서 pass 성향이 높은 정책이 반복
- Captain에서 특정 정책 편향으로 행동이 적게 보임

### 2순위: 상태는 진행됐지만 UI/WS가 놓쳤을 가능성

기존 조사 문서에서도 봇 stall/상태 전파 문제 가능성이 이미 제기되어 있다.

관련 문서:

- [`backend_bot_repro_report_2026-04-02.md`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend_bot_repro_report_2026-04-02.md)

즉 사용자는 "행동을 안 한다"고 느끼지만 실제로는

- backend action은 적용
- Redis/WS 전파 실패
- 프론트가 stale state 유지

일 수도 있다.

### 3순위: Captain mask 버그 또는 phase-specific mask/obs 불일치

이건 완전히 배제할 수는 없다.  
특히 실게임 상태에서는 다음이 얽힌다.

- cargo ships 상태
- other ship already has same good 규칙
- wharf 예외
- pass 허용 조건

테스트가 있다고 해서 실서비스 경로까지 완전 보장되는 것은 아니다.

다만 현재 소스만 보면 1순위 원인보다 우선되지는 않는다.

### 4순위: Trader에서의 "아무것도 안 함"은 정상 랜덤 변동일 수 있음

Trader는 pass가 항상 열려 있으므로, Random이면 판매 기회가 있어도 pass할 수 있다.

따라서 Trader는 "정말 이상한지"를 정량 기준으로 봐야 한다.

예:

- 판매 가능한 상황 100회 중 95회 이상 pass

이 정도가 되어야 비정상으로 볼 수 있다.

## 4. 관련 코드 구조

## 4.1 마스크 생성 지점

마스크의 단일 진실 소스는 [`PuertoRicoEnv.valid_action_mask()`](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/pr_env.py#L495) 이다.

여기서:

- Trader: `39~43`, `15`
- Captain: `44~58`, `59~63`, `15`
- Mayor: `69~72`
- Captain Store: `64~68`, `106~110`, `15`

가 열린다.

## 4.2 백엔드가 마스크를 소비하는 경로

채널 모드:

- [`GameService._schedule_next_bot_turn_if_needed()`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py#L235)
- [`BotService.run_bot_turn()`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py#L104)
- [`EngineWrapper.get_action_mask()`](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py#L51)

현재 흐름:

1. 현재 턴이 `BOT_*` 인지 확인
2. `engine.get_action_mask()` 획득
3. `BotService.get_action(game_context)` 호출
4. 선택 액션을 `process_action()`에 전달

이때 문제는 3번에서 `bot_type`이 사라진다는 점이다.

## 4.3 `random` 표시와 실제 wrapper 선택의 단절

표시용 `bot_type`은 room/session/serializer 쪽에 존재한다.

- room DB `players=["BOT_random", ...]`
- serializer `bot_players`
- 프론트 UI label

하지만 추론용 wrapper 선택에는 연결되지 않는다.

이 단절이 두 번째 이슈의 핵심 설계 포인트다.

## 5. 해결 목표

이 문제의 해결 목표는 둘로 나뉜다.

### 목표 A. "Random"이 실제 Random이어야 한다

- `BOT_random` actor는 반드시 `RandomWrapper`를 사용
- `BOT_ppo` actor는 반드시 PPO wrapper를 사용
- actor label과 실제 추론 정책이 일치해야 한다

### 목표 B. Trader/Captain 이상 행동을 재현 가능하게 진단해야 한다

- phase
- valid action count
- action_mask summary
- selected action
- applied action
- state propagation

이 남아야 "mask 문제인지, policy 문제인지, WS 문제인지"를 분리할 수 있다.

## 6. 권장 설계안

## 6.1 1단계: 봇 타입 라우팅을 단일 경로로 복구

가장 먼저 해야 할 일은 `bot_type`을 실제 추론에 연결하는 것이다.

권장 방향:

- `BotService.get_action(bot_type, game_context)` 형태로 계약을 명시적으로 복구
- 내부에서 `AgentRegistry.get_wrapper(bot_type, obs_dim)` 또는 이에 준하는 라우팅 사용
- channel/legacy 모두 같은 호출 형태를 쓰게 통일

즉 다음 구조가 되어야 한다.

```python
bot_type = resolve_bot_type(actor_id or room.players[current_idx])
wrapper = get_wrapper_for(bot_type)
action = wrapper.act(obs, mask, phase_id)
```

핵심 원칙:

- actor label
- wrapper selection
- logging

세 가지가 같은 `bot_type`을 공유해야 한다.

## 6.2 2단계: action mask 진단 로그 강화

현재도 일부 `[BOT_TRACE]` 로그는 있으나, Trader/Captain 분석에는 부족하다.

추가로 반드시 남겨야 할 항목:

- `bot_type`
- `phase_name`
- `valid_action_count`
- `pass_allowed`
- `valid_trader_actions`
- `valid_captain_ship_actions`
- `valid_captain_wharf_actions`
- `selected_action`
- `selected_action_is_pass`

권장 로그 예시:

```text
[BOT_MASK] game=... actor=BOT_random bot_type=random phase=CAPTAIN
valid_count=3 pass_allowed=0 ship_actions=[44,47] wharf_actions=[]
selected_action=47
```

이 정도가 있어야 "Captain인데 왜 pass했는지"를 바로 판별할 수 있다.

## 6.3 3단계: phase별 검증 테스트를 서비스 경로에 추가

현재 `PuCo_RL` 단위 테스트는 있지만, channel 백엔드 경로 테스트는 따로 보강해야 한다.

필수 테스트:

1. `BOT_random`가 실제 RandomWrapper를 사용한다
2. `BOT_ppo`와 `BOT_random`가 같은 마스크에서 다른 wrapper를 탄다
3. Captain에서 적재 가능하면 pass가 선택되지 않는다
4. Trader에서 valid sell + pass가 동시에 열리는 상태가 정확히 생성된다
5. bot action 후 `process_action()`와 WS broadcast까지 이어진다

즉, 엔진 테스트와 서비스 테스트를 분리해야 한다.

## 6.4 4단계: "진짜 랜덤"과 "실용 랜덤"을 구분

여기서 제품 결정을 하나 해야 한다.

### 옵션 A. 순수 Random 유지

- Trader에서 pass도 무작위 후보
- Captain에서는 mask상 허용된 것만 무작위
- 단순하고 정직하다

장점:

- 구현 단순
- "random" 의미와 일치

단점:

- Trader에서 체감상 멍청해 보일 수 있다

### 옵션 B. 제약된 Random

- Trader에서 sell 가능한데도 pass는 제외
- Captain에서 ship action이 있으면 그중 무작위
- 사람이 기대하는 "뭔가 해보는 랜덤"에 더 가깝다

장점:

- 관전 UX가 좋아진다
- "아무것도 안 한다"는 불만이 줄어든다

단점:

- 더 이상 순수 random은 아니다

권장:

- 문서상 `random`은 순수 random으로 유지
- 별도 `active_random` 또는 `no_pass_random` 같은 봇 타입을 추가하는 것이 더 정직하다

즉, 현 이슈 해결의 1차 목표는 "random이 진짜 random이게 만들기"이지, random 성격을 몰래 바꾸는 것이 아니다.

## 7. 세부 설계

## 7.1 bot_type 해석 함수 도입

권장 신규 개념:

- `resolve_bot_type(actor_id: str, room_players: list[str], current_idx: int) -> str`

해석 규칙:

1. `actor_id`가 `BOT_random` 형태면 바로 파싱
2. 아니면 `room.players[current_idx]`에서 파싱
3. 실패 시 `"random"` 폴백
4. 폴백 발생은 warning 로그 남김

이 함수를 도입하면 channel/legacy 모두 같은 규칙을 공유할 수 있다.

## 7.2 wrapper cache 전략

현재는 BotService 전역 wrapper 하나만 쓰는 구조다.

변경 후 권장:

- `bot_type -> wrapper` 캐시
- obs_dim은 공통, wrapper만 타입별 분기

예:

```python
_wrappers: dict[str, AgentWrapper]
```

이 구조는 actor가 늘어나도 안전하고, all-bot self-play도 자연스럽게 지원한다.

## 7.3 진단용 mask summary 함수 도입

권장:

- `summarize_mask(mask, phase)` 유틸

출력 예:

- Trader: `pass`, `sell_goods`
- Captain: `pass`, `ship_loads`, `wharf_loads`
- Mayor: `allowed_amounts`

이 요약이 없으면 200차원 마스크 로그는 사람이 읽을 수 없다.

## 7.4 재현 리포트 자동화

운영 측에서 반복 확인하려면, 전투 한 판 기준으로 다음이 자동 축적되면 좋다.

- phase
- valid action summary
- selected action
- action result
- final state

이미 `GameLog`와 ML logging 경로가 있으므로, 최소한 bot debug 모드에서는 위 정보를 JSONL로 남기는 설계를 권장한다.

## 8. 테스트 전략

## 8.1 엔진 수준 테스트

기존 `PuCo_RL` 테스트는 유지하되, 다음을 보강하면 좋다.

1. Trader에서 sell과 pass 동시 허용 상태의 빈도 검증
2. Captain에서 can_load_anything일 때 pass 미허용 검증
3. Wharf만 가능한 경우 pass 허용 정책 검증

## 8.2 서비스 수준 테스트

필수 테스트:

1. `BOT_random` 라벨 actor가 RandomWrapper를 사용
2. `BOT_ppo` 라벨 actor가 PPOWrapper를 사용
3. game_service -> bot_service -> process_action 전체 경로에서 bot_type 유지
4. all-bot room에서 각 actor별 bot_type이 섞여도 안전

## 8.3 통합 테스트

필수 시나리오:

1. `random/random/random` 봇전
2. `ppo/random/hppo` 혼합 봇전
3. Trader phase 진입 후 판매 가능한 상태
4. Captain phase 진입 후 적재 가능한 상태

검증 포인트:

- mask summary
- selected action
- pass 사용 빈도
- state transition
- WS update 수신

## 8.4 정량 검증 지표

Random bot이 "정상적으로 움직인다"를 다음처럼 정의하는 것이 좋다.

### Trader

- 판매 가능 상태 N회 중
- pass 비율이 100%이면 이상
- 다만 pass가 항상 허용되므로 일정 수준 pass는 정상

### Captain

- 선적 가능 상태 N회 중
- pass가 선택되면 즉시 이상
- 이유: mask 상 pass가 닫혀 있어야 하기 때문

즉, Captain은 binary하게 검증 가능하고, Trader는 통계적으로 봐야 한다.

## 9. 권장 실행 순서

실행 순서는 반드시 다음이어야 한다.

1. bot_type 라우팅부터 바로잡는다
2. mask summary 로그를 추가한다
3. Captain 이상 행동부터 확인한다
4. Trader는 통계적으로 관찰한다
5. 필요하면 별도 `active_random` 봇 타입을 도입한다

이 순서를 뒤집으면 안 된다.

특히 "random이 멍청하니 Trader pass를 막자"를 먼저 하면, 실제 원인이 bot_type 라우팅 불일치였을 때 문제를 덮어버리게 된다.

## 10. 최종 결론

현재 코드베이스 기준으로, 두 번째 이슈의 1순위 원인은 액션 마스크 자체보다 "Random bot_type이 실제 추론 wrapper 선택으로 이어지지 않는 구조"다.

정리하면:

- Trader/Captain mask 로직은 엔진과 테스트 상 존재한다
- Trader는 원래 pass가 열려 있으므로 pass 자체는 이상이 아닐 수 있다
- Captain에서 반복 무행동이면 더 강한 이상 신호다
- 그러나 그 전에 "정말 RandomWrapper가 쓰이고 있는지"부터 검증해야 한다

따라서 해결 설계의 핵심은 다음 두 가지다.

1. `bot_type` 기반 wrapper 라우팅을 channel 경로에 복구
2. phase별 mask summary와 selected action logging을 넣어 원인을 분리

이 두 가지가 먼저 해결되어야, 그 다음에야 "진짜 mask 버그"인지 "정상 random 분포"인지 판별할 수 있다.
