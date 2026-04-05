# Priority 2 Design Report

작성일: 2026-04-04

대상 범위:
- `TODO.md > Priority 2. 봇전 / 봇 추론 / WS / 봇 타입 라우팅`
- `2-A. 봇전 생성 구조와 봇 타입 고정값 제거 설계`
- `2-B. bot_type 라우팅 복구`
- `2-C. Random 봇 역할 선택/상인/선장 편향 분석`
- `2-D. 봇 입력 데이터 검증 로직 및 테스트 계획`
- `2-E. 봇전 WS 리스크 및 통신 오류 대응 분석`

관련 파일:
- [backend/app/api/channel/room.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/room.py)
- [backend/app/api/channel/game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/game.py)
- [backend/app/api/channel/ws.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/ws.py)
- [backend/app/api/legacy/deps.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/legacy/deps.py)
- [backend/app/services/game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- [backend/app/services/bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)
- [backend/app/services/agent_registry.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/agent_registry.py)
- [backend/app/services/ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)
- [backend/app/engine_wrapper/wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py)
- [backend/app/services/state_serializer.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py)
- [frontend/src/hooks/useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)
- [PuCo_RL/agents/wrappers.py](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/agents/wrappers.py)

## 요약

Priority 2의 직접 원인은 하나가 아니다. 현재 코드를 기준으로 보면 아래 네 문제가 서로 얽혀 있다.

1. `channel` 경로는 bot_type을 저장하지만 실제 추론 시 wrapper 선택에는 쓰지 않는다.
2. `legacy` 경로는 여전히 `BotService.get_action(bot_type, game_context)` 계약을 기대하지만, 실제 `BotService`는 `get_action(game_context)`만 제공한다.
3. 봇 추론 입력은 `engine.last_obs`와 `engine.get_action_mask()`를 조합해 만들고 있는데, serializer가 보여주는 상태와 같은 step 기준인지 명시적 검증층이 없다.
4. WS는 `direct broadcast`와 `redis listener broadcast`가 동시에 살아 있어 같은 `STATE_UPDATE`가 중복 전파될 수 있고, 종료 시점 이벤트 contract도 아직 단일화되어 있지 않다.

따라서 Priority 2는 기능 추가보다 먼저 `계약 통합`이 핵심이다.

## 현재 상태 진단

### 1. bot_type 저장은 되지만 실제 wrapper 선택에는 연결되지 않음

[game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py) 는 room의 `BOT_random`, `BOT_ppo` 같은 문자열을 읽어 `bot_players[idx] = bot_type`으로 저장한다.

```python
if pid.startswith("BOT_"):
    bot_type = pid.split("_", 1)[1].lower() if "_" in pid else "random"
    player_names.append(f"Bot ({bot_type})")
    bot_players[i] = bot_type
```

하지만 [bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py) 는 `MODEL_TYPE` 환경변수로 단일 wrapper만 로드한다.

```python
model_type = os.getenv("MODEL_TYPE", "legacy_ppo").lower()
...
cls._agent_wrapper = AgentFactory.get_agent(model_path)
```

즉 현재 channel 경로에서는:
- DB/room/player label 상으로는 `BOT_random`, `BOT_ppo`를 구분함
- 실제 inference wrapper는 전역 singleton 하나만 씀
- 결과적으로 `BOT_random`이 정말 `RandomWrapper`인지 보장되지 않음

### 2. legacy와 channel이 서로 다른 BotService 계약을 가정함

[legacy/deps.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/legacy/deps.py) 는 아래처럼 호출한다.

```python
action = BotService.get_action(bot_type, game_context)
```

반면 실제 [bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py) 는 아래 시그니처다.

```python
@staticmethod
def get_action(game_context: Dict[str, Any]) -> int:
```

이건 단순 구현 누락이 아니라, 이미 `legacy/channel contract drift`가 코드 레벨에서 발생한 상태다.

### 3. 봇 입력 데이터의 step 동기성이 테스트로 고정되어 있지 않음

[bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py) 는 아래 조합으로 추론 입력을 만든다.

```python
mask = engine.get_action_mask()
current_phase = _extract_phase_id(engine.last_obs)
game_context = {
    "vector_obs": engine.last_obs,
    "action_mask": mask,
    "phase_id": current_phase,
}
```

[engine_wrapper/wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py) 는 `step()` 후 `_refresh_cached_view()`로 `last_obs`, `last_info`, `last_action_mask`를 갱신한다. 구조상 맞아 보이지만, 현재는 아래가 characterization test로 고정되어 있지 않다.

- `engine.last_obs`의 phase
- `engine.get_action_mask()`의 유효 action
- `serialize_game_state_from_engine()`이 노출하는 `meta.phase`, `action_mask`

이 셋이 항상 같은 step 기준인지 명시적으로 검증하는 테스트가 없다.

### 4. WS는 direct + redis 경로가 동시에 존재함

[game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py) 의 `_sync_to_redis()` 경로와 [ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py) 의 `broadcast_to_game()` fallback 때문에, 동일 상태가 아래 두 경로로 전송될 수 있다.

- Redis publish -> redis listener -> manager broadcast
- direct broadcast -> manager broadcast

프론트는 [useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts) 에서 JSON stringify dedupe를 하고 있지만, 이것은 증상 완화이지 backend contract 정리는 아니다.

## 설계 원칙

Priority 2는 아래 원칙으로 정리하는 것이 안전하다.

1. `bot_type resolution`의 단일 책임은 `AgentRegistry`로 몰아준다.
2. `BotService`는 전역 singleton wrapper가 아니라 `bot_type` 기반 wrapper resolver를 호출해야 한다.
3. `legacy`와 `channel`은 같은 bot contract를 공유해야 한다.
4. 통계 분석과 규칙 검증은 분리한다.
5. WS는 "전송 경로를 줄이는 것"과 "중복 수신을 견디는 것"을 같이 설계해야 한다.

---

## Task 2-A. 봇전 생성 구조와 봇 타입 고정값 제거 설계

### 목표

현재 `create_bot_game()`이 무조건 `BOT_random` 3개를 넣는 구조를 일반화한다. 단, UI를 바로 바꾸기 전에 backend contract부터 정리해야 한다.

현재 코드:

```python
room = GameSession(
    ...
    players=["BOT_random", "BOT_random", "BOT_random"],
    host_id=str(current_user.id),
)
```

### 제안 설계

`bot-game` 생성 API는 아래 두 레이어로 분리한다.

1. 입력 스키마
2. 봇 슬롯 생성기

예시:

```python
class BotGameCreateRequest(BaseModel):
    bot_types: list[str] = Field(default_factory=lambda: ["random", "random", "random"])


def _normalize_bot_types(bot_types: list[str], max_players: int = 3) -> list[str]:
    normalized = [(bt or "random").lower() for bt in bot_types[:max_players]]
    while len(normalized) < max_players:
        normalized.append("random")
    return normalized
```

적용 위치:
- [backend/app/api/channel/room.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/room.py)
- 필요 시 schema는 [backend/app/schemas/game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/schemas/game.py)

### 영향 범위

직접 영향:
- 즉시 시작 봇전 생성 API
- 봇전 생성 응답 payload
- UI의 bot-game 생성 버튼 / body shape

간접 영향:
- `BOT_random`만 가정한 테스트
- 향후 `all-ppo`, `mixed bots`, `debug bot roster` 시나리오

### 리스크

- UI가 아직 `POST /bot-game` body를 안 보내면 default 처리 필요
- 잘못된 bot_type 문자열이 들어오면 방 생성 시점에 막을지, fallback할지 정책이 필요

권장:
- 생성 시점에는 validation fail-fast
- 실행 시점에는 unknown type fallback을 두지 말고 400을 반환

### 테스트 설계

우선 red test:

```python
def test_create_bot_game_accepts_explicit_bot_types(...)
def test_create_bot_game_rejects_unknown_bot_type(...)
def test_create_bot_game_defaults_to_three_random_bots(...)
```

### 롤백 방법

최소 롤백:
- 새 request schema 제거
- `players=["BOT_random", "BOT_random", "BOT_random"]`로 복귀

부분 롤백 영향:
- 생성 API만 되돌아가고, 하위 bot routing이 이미 바뀐 상태면 mixed bot contract 문서와 어긋날 수 있음

---

## Task 2-B. bot_type 라우팅 복구

### 목표

`BOT_random -> RandomWrapper`, `BOT_ppo -> PPOWrapper`가 실제로 보장되도록 한다.

### 현재 문제

[agent_registry.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/agent_registry.py) 는 이미 올바른 registry를 갖고 있다.

```python
AGENT_REGISTRY = {
    "ppo": {"wrapper_cls": PPOWrapper, ...},
    "hppo": {"wrapper_cls": HPPOWrapper, ...},
    "random": {"wrapper_cls": RandomWrapper, ...},
}
```

문제는 [bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py) 가 이 registry를 전혀 사용하지 않는다는 점이다.

### 제안 설계

`BotService`를 아래 형태로 바꾼다.

```python
from app.services.agent_registry import get_wrapper


class BotService:
    _obs_space = None
    _obs_dim = None

    @classmethod
    def _ensure_obs_space(cls):
        if cls._obs_space is None:
            cls._obs_space, cls._obs_dim = _build_obs_space()

    @classmethod
    def get_agent_wrapper(cls, bot_type: str) -> AgentWrapper:
        cls._ensure_obs_space()
        return get_wrapper(bot_type, cls._obs_dim)

    @staticmethod
    def get_action(bot_type: str, game_context: Dict[str, Any]) -> int:
        wrapper = BotService.get_agent_wrapper(bot_type)
        ...
```

그리고 channel 경로도 `actor_id -> bot_type` resolution을 명시적으로 사용한다.

예시:

```python
bot_type = str(actor_id).split("_", 1)[1].lower() if str(actor_id).startswith("BOT_") else "random"
action_int = BotService.get_action(bot_type, game_context)
```

### 영향 범위

직접 영향:
- [backend/app/services/bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)
- [backend/app/services/game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- [backend/app/api/legacy/deps.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/legacy/deps.py)

간접 영향:
- 기존 `MODEL_TYPE` 환경변수 기반 단일 봇 운영 방식
- 테스트들이 `BotService.get_action(game_context)` 계약을 직접 모킹하고 있다면 수정 필요
- mixed bot table game 지원 시 추론 path 안정성

### 호환성 정책

권장 방향:
- `MODEL_TYPE` 경로는 deprecated
- `AgentRegistry`만 공식 경로
- legacy/channel 모두 `bot_type + game_context` 계약 공유

과도기 fallback 예시:

```python
def get_action(*args, **kwargs):
    if len(args) == 1:
        bot_type = "ppo"
        game_context = args[0]
    else:
        bot_type, game_context = args
```

하지만 이건 장기적으로 권장하지 않는다. 이번 Priority 2에서는 contract를 깨끗하게 정리하는 편이 낫다.

### 테스트 설계

필수 red test:

```python
def test_channel_bot_random_uses_random_wrapper(...)
def test_channel_bot_ppo_uses_ppo_wrapper(...)
def test_legacy_and_channel_share_same_bot_type_contract(...)
```

구체 전략:
- `get_wrapper`를 monkeypatch/mock 처리
- `BOT_random` 입력 시 `RandomWrapper.act()`가 호출됐는지 검증
- `BOT_ppo` 입력 시 `PPOWrapper.act()`가 호출됐는지 검증

### 롤백 방법

최소 롤백:
- `BotService.get_action(bot_type, ...)` 변경을 되돌리고 기존 singleton 방식으로 복귀

부작용:
- rollback 즉시 channel의 bot label과 실제 wrapper 선택이 다시 어긋남
- mixed bot game은 다시 "표시만 다른 단일 모델" 상태로 돌아감

---

## Task 2-C. Random 봇 역할 선택/상인/선장 편향 분석

### 목표

"Random인데 왜 시장을 많이 고르지?"와 "상인/선장에서 아무것도 안 한다"를 구분 가능한 지표로 정리한다.

### 현재 해석

현재 프로젝트에서는 `Random` 의심 이슈가 세 갈래다.

1. 정말 `RandomWrapper`가 아닌 다른 wrapper가 쓰이고 있을 수 있음
2. mask 자체가 특정 액션만 열고 있을 수 있음
3. 규칙상 pass가 열려 있어 random이 pass를 자주 뽑을 수 있음

특히 Trader는 현재 규칙상 pass가 열려 있으므로, "아무것도 안 한다"는 관찰만으로 버그라고 결론내릴 수 없다.

### 제안 설계

분석 레이어를 둘로 나눈다.

1. deterministic correctness
2. statistical behavior

deterministic correctness는 테스트로 고정한다.

```python
def test_random_wrapper_only_selects_valid_mask_actions(...)
def test_bot_random_resolves_to_random_wrapper(...)
```

statistical behavior는 리포트/스크립트로 분리한다.

예시 로그 집계 구조:

```python
{
    "phase_id": 4,
    "bot_type": "random",
    "valid_count": 3,
    "selected_action": 15,
    "valid_actions": [15, 41, 43],
}
```

추천 산출 지표:
- role selection 빈도
- Trader phase에서 `pass / sell` 비율
- Captain phase에서 `pass` 발생 수
- Captain에서 `action=15`가 열린 상태와 닫힌 상태 비율

### 영향 범위

직접 영향:
- [backend/app/services/bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py) trace log
- replay / DB log / 분석 스크립트

간접 영향:
- 운영자 해석 방식
- "random"의 제품 의미

### 설계 결정 포인트

`random`을 두 개로 나눌지 검토할 수 있다.

1. `legal_random`
2. `uniform_debug_random`

예시:

```python
AGENT_REGISTRY["debug_random"] = {
    "name": "Debug Random Bot",
    "wrapper_cls": RandomWrapper,
    "model_env_key": None,
    "model_default": None,
}
```

단, 이번 Priority 2에서는 먼저 `BOT_random`이 진짜 `RandomWrapper`인지 복구하는 것이 우선이다. 새 bot type 추가는 2차 작업으로 미루는 것이 안전하다.

### 테스트 / 리포트 경계

테스트로 검증할 것:
- 유효 action만 선택하는지
- wrapper routing이 맞는지

테스트로 검증하지 않을 것:
- 100판 돌렸을 때 role 분포가 균등한지

이건 스크립트/리포트가 맞다.

### 롤백 방법

통계 집계 코드만 추가했다면 제거가 쉽다.
- trace log 필드 제거
- report script 삭제

핵심 bot routing 변경과 분리해서 커밋/적용해야 rollback 비용이 낮다.

---

## Task 2-D. 봇 입력 데이터 검증 로직 및 테스트 계획

### 목표

봇이 보고 있는 `obs/mask/phase`와 UI/serializer가 노출하는 상태가 같은 step를 가리키는지 검증 가능하게 만든다.

### 현재 문제

현재 구조:

```python
mask = engine.get_action_mask()
phase_id = _extract_phase_id(engine.last_obs)
game_context = {
    "vector_obs": engine.last_obs,
    "action_mask": mask,
    "phase_id": phase_id,
}
```

serializer는 별도로:

```python
state = serialize_game_state_from_engine(engine=engine, ...)
```

이 구조는 직관상 맞지만, 아래 drift를 방지하는 guard가 없다.

- stale `last_obs`
- mask-before / state-after 혼동
- serializer phase와 bot phase 불일치

### 제안 설계

`bot input snapshot` 개념을 도입한다.

예시:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class BotInputSnapshot:
    obs: dict
    action_mask: list[int]
    phase_id: int
    current_player_idx: int
    step_count: int
```

`EngineWrapper` 또는 `BotService`에서 snapshot을 한 번에 만든다.

```python
def build_bot_input_snapshot(engine: EngineWrapper) -> BotInputSnapshot:
    obs = engine.last_obs
    mask = engine.get_action_mask()
    phase_id = _extract_phase_id(obs)
    return BotInputSnapshot(
        obs=obs,
        action_mask=mask,
        phase_id=phase_id,
        current_player_idx=engine.env.game.current_player_idx,
        step_count=engine._step_count,
    )
```

그리고 serializer contract 검사:

```python
state = serialize_game_state_from_engine(...)
assert state["meta"]["active_player"] == f"player_{snapshot.current_player_idx}"
assert state["action_mask"] == snapshot.action_mask
```

### 영향 범위

직접 영향:
- [backend/app/services/bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)
- [backend/app/engine_wrapper/wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py)
- [backend/app/services/state_serializer.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py)

간접 영향:
- bot trace log 포맷
- regression test fixture

### 테스트 계획

우선 characterization test:

```python
def test_engine_last_obs_phase_matches_serializer_meta_phase(...)
def test_engine_action_mask_matches_serializer_action_mask(...)
def test_bot_input_snapshot_uses_same_current_player_as_engine(...)
```

phase drift 재현 시 regression test:

```python
def test_bot_phase_id_does_not_lag_after_engine_step(...)
```

### 롤백 방법

snapshot abstraction은 삭제가 쉽지만, trace/log/test가 그것에 의존하기 시작하면 연쇄 수정이 필요하다. 따라서:

- 1차: helper function만 추가
- 2차: 기존 코드가 helper를 사용하도록 전환

순서로 가는 것이 rollback-friendly 하다.

---

## Task 2-E. 봇전 WS 리스크 및 통신 오류 대응 분석

### 목표

봇전에서 상태는 바뀌었는데 프론트가 늦게 보거나 중복 수신하거나 종료 화면 전환이 흔들리는 문제를 예방한다.

### 현재 문제

[ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py) 에는 두 경로가 있다.

1. Redis listener path

```python
await pubsub.subscribe(f"game:{game_id}:events")
...
await self._broadcast(game_id, data)
```

2. Direct broadcast path

```python
async def broadcast_to_game(self, game_id: str, message: dict):
    await self._broadcast(game_id, json.dumps(message))
```

프론트는 dedupe를 하고 있다.

```ts
const stateKey = JSON.stringify({ data: richState, mask: actionMask })
if (stateKey === lastStateKeyRef.current) return
```

이건 안전장치로는 유효하지만, backend에서 동일 이벤트를 두 번 보내는 구조를 공식 contract로 두면 안 된다.

### 제안 설계

#### 방향 1. 단일 broadcast source 정리

권장:
- backend process 내부에서도 Redis publish만 표준 경로로 사용
- direct broadcast는 fallback 또는 test 전용으로 축소

예시:

```python
def publish_state_update(...):
    redis_client.publish(channel, payload)


async def broadcast_to_game(...):
    # deprecated fallback only
```

#### 방향 2. event envelope 도입

WS 메시지에 sequence id를 넣어 프론트가 더 안전하게 정렬/중복 제거할 수 있게 한다.

```json
{
  "type": "STATE_UPDATE",
  "game_id": "...",
  "seq": 128,
  "data": {...},
  "action_mask": [...]
}
```

이 `seq`는 DB `GameLog.step`나 engine `_step_count`를 재사용할 수 있다.

#### 방향 3. 종료 contract 정리

현재는 종료 시에도 사실상 `STATE_UPDATE` 중심이고, 별도 `GAME_ENDED`는 disconnect timeout 쪽에만 강하다.

권장:
- 정상 종료: `STATE_UPDATE(finished=true)` + 선택적으로 `GAME_ENDED`
- 비정상 종료: `GAME_ENDED(reason=...)`

프론트는 아래 우선순위로 처리한다.

1. `GAME_ENDED`
2. `STATE_UPDATE.meta.end_game_triggered`

### 영향 범위

직접 영향:
- [backend/app/services/game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- [backend/app/services/ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)
- [backend/app/api/channel/ws.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/ws.py)
- [frontend/src/hooks/useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)

간접 영향:
- reconnect 로직
- 종료 UX
- 중복 렌더링 / stale state 디버깅 방식

### 테스트 계획

integration sequence test 중심:

```python
def test_state_update_published_once_per_action(...)
def test_ws_listener_dispatches_single_effective_state(...)
def test_game_end_emits_terminal_state_before_disconnect(...)
```

프론트 acceptance test:

```ts
it('dedupes duplicated state updates with same seq')
it('transitions to ended state on GAME_ENDED or terminal STATE_UPDATE')
```

### 롤백 방법

가장 위험한 변경은 broadcast source 제거다. 그래서 rollout은 두 단계가 맞다.

1. `seq` 추가 + 로깅 강화
2. direct broadcast 제거

이렇게 가면 롤백 시에도 direct path만 다시 켜면 된다.

---

## 권장 구현 순서

Priority 2는 아래 순서가 가장 안전하다.

1. `2-B` bot_type routing 복구
2. `2-A` bot-game 생성 contract 일반화
3. `2-D` bot input snapshot / characterization test
4. `2-C` random behavior report script/logging
5. `2-E` WS sequence / broadcast 정리

이 순서를 권장하는 이유:
- 2-B가 틀리면 2-C 분석 결과가 무의미해진다.
- 2-D를 먼저 고정해야 2-C 통계가 해석 가능하다.
- WS는 가장 넓게 영향이 가므로 마지막에 다루는 것이 rollback 비용이 낮다.

## TDD First List

반드시 red부터 들어갈 테스트:

1. `test_channel_bot_random_uses_random_wrapper`
2. `test_channel_bot_ppo_uses_ppo_wrapper`
3. `test_legacy_and_channel_share_same_bot_type_contract`
4. `test_create_bot_game_accepts_explicit_bot_types`
5. `test_engine_action_mask_matches_serializer_action_mask`
6. `test_engine_last_obs_phase_matches_serializer_meta_phase`
7. `test_random_wrapper_only_selects_valid_actions`
8. `test_ws_state_update_effectively_delivered_once_per_action`

## 파일별 변경 예상표

### [backend/app/services/bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)

변경 목적:
- singleton model path 제거
- `bot_type -> wrapper` 라우팅 복구
- bot input snapshot 진입점 마련

영향:
- 가장 큼
- legacy/channel/bot task 전부 영향

### [backend/app/services/agent_registry.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/agent_registry.py)

변경 목적:
- 단일 truth source 유지
- 새 bot type 추가 시 여기만 수정하는 구조 강화

영향:
- 중간
- wrapper factory / bot listing / validation 공유

### [backend/app/services/game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)

변경 목적:
- room player의 `BOT_xxx`와 실제 bot action path 연결
- WS publish contract 정리

영향:
- 큼
- 봇 턴 실행, DB log, redis sync, 종료 처리

### [backend/app/api/legacy/deps.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/legacy/deps.py)

변경 목적:
- legacy 경로를 channel과 같은 bot contract로 맞춤

영향:
- 중간
- 구형 테스트와 내부 개발용 route 영향

### [backend/app/api/channel/room.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/room.py)

변경 목적:
- 즉시 시작 봇전 bot roster 일반화

영향:
- 작음~중간
- bot-game 생성 flow

### [backend/app/services/ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)

변경 목적:
- WS broadcast source 정리
- sequence 기반 dedupe contract 도입

영향:
- 큼
- 실시간 상태 반영 전반

### [frontend/src/hooks/useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)

변경 목적:
- seq 기반 dedupe
- 종료 이벤트 처리 선명화

영향:
- 중간
- 게임 화면 렌더 안정성

## 롤백 전략

### 최소 롤백 단위

1. bot routing
2. bot-game create payload
3. bot input snapshot helper
4. WS seq field
5. WS direct broadcast 제거

이 다섯 단위를 분리해서 적용해야 한다.

### 권장 커밋 경계

1. `bot routing contract unification`
2. `bot-game roster API generalization`
3. `bot input snapshot tests`
4. `ws sequencing and dedupe contract`

### 롤백 우선순위

문제 발생 시 가장 먼저 되돌릴 부분:
- WS direct broadcast 제거

두 번째:
- bot-game 생성 body generalization

가장 마지막까지 유지해야 할 부분:
- bot_type routing 복구

이유:
- 이건 현재 drift를 바로잡는 본질 수정이라 되돌리면 다시 "표시와 실제 동작이 다른 봇" 상태로 복귀한다.

## 최종 제안

Priority 2는 아래 한 문장으로 정리할 수 있다.

`먼저 bot_type contract를 단일화하고, 그 다음에 random behavior를 분석하며, 마지막에 WS 전달 계약을 정리한다.`

즉 다음 실제 작업 순서는:

1. `2-B` 구현 및 TDD
2. `2-A` 구현 및 TDD
3. `2-D` characterization test 추가
4. `2-C` 분석 스크립트/로그 설계
5. `2-E` WS 계약 정리

이 순서가 아니면, 나중 단계에서 얻은 관찰값이 앞 단계 drift 때문에 오염될 가능성이 높다.
