# Trader / Captain Rule Audit

작성일: 2026-04-03

대상 TODO:
- `1-C. Captain 강제 적재 규칙 검증`
- `1-D. Trader 규칙 및 pass 정책 검증`

대상 코드:
- [TODO.md](/Users/seoungmun/Documents/agent_dev/castest/castone/TODO.md)
- [engine.py](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/engine.py)
- [pr_env.py](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/pr_env.py)
- [bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)

## 범위

이번 작업에서는 코드를 수정하지 않았다. 아래 두 축만 검증했다.

1. 엔진 규칙이 코드상 어떻게 정의되어 있는지
2. Docker로 실제 `puco_backend` 컨테이너를 띄운 뒤, 그 안에서 엔진 시나리오를 직접 실행했을 때 규칙이 그대로 재현되는지

## Docker 상태

실행 명령:

```bash
docker compose up -d db redis backend
docker compose ps
```

확인 결과:

```text
puco_backend   Up (healthy)   127.0.0.1:8000->8000/tcp
puco_db        Up (healthy)   127.0.0.1:5432->5432/tcp
puco_redis     Up (healthy)   127.0.0.1:6379->6379/tcp
```

백엔드 로그에서는 `/health` 200 응답만 확인되었고, 이번 검증은 API 경유 플레이스루가 아니라 컨테이너 내부 엔진 직접 실행 방식으로 진행했다.

## 코드 판독 결과

### Trader

- [engine.py:533](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/engine.py#L533) 의 `action_trader()`는 `sell_good is None`이면 별도 검증 없이 바로 `self._advance_phase_turn()`을 호출한다.
- 즉 `Trader pass`는 현재 구현상 "규칙 위반"이 아니라 "항상 허용되는 정책"이다.
- [pr_env.py:547](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/pr_env.py#L547) 가 아니라 Trader 분기 상단에서 `mask[15] = True`가 항상 열리는 구조이므로, sell action과 pass가 동시에 열리는 것이 의도된 현재 contract다.

핵심 해석:
- TODO의 "Trader에서 pass가 항상 허용되는 현재 정책은 의도된 설계인가"에 대해, 현재 코드는 명백히 `항상 허용` 쪽으로 구현되어 있다.
- 따라서 Random 봇이 Trader에서 물건을 안 팔고 pass하는 현상은, 최소한 엔진/mask 기준으로는 "버그"가 아니라 "허용된 행동"이다.

### Captain

- [engine.py:685](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/engine.py#L685) 의 `action_captain_load()`는 적재 가능한 배 중 가장 많이 실을 수 있는 선택이 아니면 예외를 발생시킨다.
- [engine.py:773](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/engine.py#L773) 의 `action_captain_pass()`는 일반 화물선 기준으로라도 실을 수 있는 경우 `Rule Violation` 예외를 발생시킨다.
- 같은 함수 내부 주석대로 Wharf는 `100% voluntary`로 처리되므로, 일반 화물선 적재가 불가능하고 Wharf만 가능한 경우에는 pass가 허용된다.
- [pr_env.py:547](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/pr_env.py#L547) 의 Captain mask도 같은 철학을 따른다.
  - 일반 선적 가능 액션이 있으면 `mask[15]`를 열지 않음
  - Wharf 액션은 별도로 열지만, 그것만으로 pass를 막지는 않음

핵심 해석:
- TODO의 "선장 페이즈에서 적재 가능하면 반드시 적재해야 한다는 규칙이 실제로 강제되는가"에 대해, 현재 구현은 `일반 화물선 기준으로는 강제한다`.
- 다만 `Wharf만 가능한 상태`는 예외적으로 pass를 허용하는 설계다.

## 컨테이너 내부 직접 검증

실행 방식:

```bash
docker exec -i puco_backend python - <<'PY'
# 컨테이너 내부에서 PuertoRicoGame / PuertoRicoEnv를 직접 생성해 시나리오 실행
PY
```

### 시나리오 1. Trader: sell 가능한데도 pass 가능한가

조건:
- 3인 게임
- 현재 플레이어 goods 에 `CORN=2`
- Trader phase 강제 세팅

관찰:

```json
{
  "pass_in_mask": true,
  "sell_corn_in_mask": true,
  "engine_pass_result": "allowed",
  "next_player_idx": 1,
  "phase_after": 4
}
```

판정:
- `pass`와 `sell`이 동시에 mask에 열림
- 엔진도 `pass`를 정상 허용

결론:
- Trader 무행동은 현재 규칙상 허용된 행동이다.

### 시나리오 2. Captain: 일반 화물선 적재 가능 시 pass 가능한가

조건:
- 3인 게임
- 현재 플레이어 goods 에 `CORN=2`
- 모든 화물선이 비어 있음

관찰:

```json
{
  "pass_in_mask": false,
  "load_actions": [46, 51, 56],
  "engine_pass_result": "error:Rule Violation: Player MUST load if they have valid goods and ship capacity."
}
```

판정:
- mask에서 pass가 닫힘
- 엔진도 pass를 거부

결론:
- Captain 일반 선적 강제는 실제로 작동한다.

### 시나리오 3. Captain: Wharf만 가능하면 pass 가능한가

조건:
- 3인 게임
- 현재 플레이어 goods 에 `CORN=3`
- Wharf 보유 및 점유
- 일반 화물선은 모두 불가능한 상태로 세팅

관찰:

```json
{
  "pass_in_mask": true,
  "wharf_corn_in_mask": true,
  "engine_pass_result": "allowed",
  "next_player_idx": 1
}
```

판정:
- mask에서 Wharf action과 pass가 동시에 열림
- 엔진도 pass를 허용

결론:
- 현재 구현은 `Wharf는 선택사항`이라는 설계를 일관되게 따르고 있다.

### 시나리오 4. Captain: 더 많이 실을 수 있는 배가 있으면 작은 배 선택이 막히는가

조건:
- 2인 게임의 기본 화물선 용량 `4 / 6`
- 현재 플레이어 goods 에 `COFFEE=5`
- 둘 다 빈 배

관찰:

```json
{
  "ship0_coffee_action": false,
  "ship1_coffee_action": true,
  "pass_in_mask": false,
  "engine_small_ship_result": "error:Rule Violation: Must load on a ship that maximizes the stored amount. (Can load 5, tried to load 4)",
  "engine_large_ship_result": "allowed",
  "ship1_load_after": 5,
  "remaining_coffee": 0
}
```

판정:
- action mask가 작은 배 선택을 미리 닫음
- 엔진도 작은 배 선택을 거부
- 큰 배 선택은 정상 허용

결론:
- Captain 최대 적재 규칙은 mask와 엔진 양쪽에서 일관되게 강제된다.

## TODO 기준 결론

### 1-C Captain 강제 적재 규칙

결론: `정상 작동`

- 일반 화물선에 적재 가능한 경우 pass는 허용되지 않는다.
- 최대 적재가 아닌 load 선택도 허용되지 않는다.
- mask와 engine의 정책이 일치한다.

단, 다음은 명확히 문서화해야 한다.

- `Wharf만 가능한 경우 pass 허용`은 현재 구현의 명시적 설계다.
- 따라서 "선장은 무조건 선적해야 한다"를 제품 규칙으로 해석할 때 Wharf까지 강제할지 여부는 별도 정책 결정이 필요하다.

### 1-D Trader pass 정책

결론: `현재는 항상 허용되는 정책`

- sell 가능한 상태에서도 pass가 열려 있다.
- 엔진도 이를 그대로 허용한다.
- 따라서 Random 봇이 Trader에서 pass하는 현상은 `Captain처럼 규칙 위반`이 아니라 `행동 정책/모델 선택 결과`일 가능성이 높다.

## 봇 경로 해석

- [bot_service.py:80](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py#L80) 이후 로직은 action mask를 받아 모델이 액션을 고르게 한다.
- [bot_service.py:95](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py#L95) 에서 `selected_action`, `phase_id`, `valid` 로그를 남긴다.
- [bot_service.py:172](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py#L172) 이후에는 엔진 거부 시 fallback 재시도를 한다.

해석:
- Captain에서 `action=15`가 실제로 선택된다면, 우선 mask가 정말 열렸는지부터 로그로 확인해야 한다.
- 현재 엔진/마스크 정의만 보면 `일반 화물선 적재가 가능한 Captain 턴`에 `15`가 정상 선택되는 구조는 아니다.
- 반면 Trader에서 `15`가 찍히는 것은 구조상 정상이다.

## 최종 판단

1. `Captain 강제 적재 로직`은 엔진과 action mask 양쪽에서 명확히 작동한다.
2. `Captain 최대 적재 로직`도 엔진과 action mask 양쪽에서 명확히 작동한다.
3. `Wharf만 가능한 경우 pass 허용`은 버그가 아니라 현재 명시적 설계다.
4. `Trader pass`는 sell 가능 여부와 무관하게 현재 항상 허용된다.
5. 따라서 TODO에서 의심한 "상인/선장에서 아무 행동도 하지 않는 현상"은 둘을 분리해서 봐야 한다.
   - Trader: 규칙 버그가 아니라 정책/모델 문제일 가능성이 큼
   - Captain: 일반 선적 가능 상태에서 pass가 나오면 추가 로그 추적 대상

## 후속 권장 검증

코드 수정 없이 다음 확인을 추가하면 TODO의 남은 의문을 더 줄일 수 있다.

1. Random 봇전 로그에서 `phase_id=5`인 Captain 턴에 실제 `action=15`가 찍히는지 수집
2. 찍힌다면 같은 시점 action mask에서 `mask[15]`가 열려 있었는지 대조
3. `Wharf만 가능했던 턴`인지, `일반 화물선 적재 가능 턴`인지 분리 집계
4. Trader는 `pass 비율`을 규칙 위반이 아니라 행동 품질 지표로 따로 분석
