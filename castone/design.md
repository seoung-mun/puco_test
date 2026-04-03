# Castone 봇 장애 해결 설계도

**날짜:** 2026-04-02
**원칙:** PuCo_RL은 블랙박스. 모든 수정은 `backend/` 래퍼 계층에서 흡수한다.

---

## Phase 1~3 완료 요약

| Phase | 대상 파일 | 해결 내용 | 상태 |
|-------|----------|----------|------|
| 1 | `wrappers.py` | Mayor 페이즈 Empty Mask 폴백을 69(place 0)로 수정 | **완료** |
| 2 | `bot_service.py` | callback 실패 시 fallback 재시도 + `_extract_phase_id` 강화 | **완료** |
| 3 | `game_service.py` | `_bot_tasks` set으로 asyncio 태스크 참조 보존 | **완료** |

**단위 테스트 전부 통과. 그러나 Docker 통합 테스트에서 봇이 여전히 미작동.**

---

## Phase 4 -- 잔여 버그 해결 설계

### 현재 증상

1. **모든 봇**(random, ppo, hppo)이 **첫 역할 선택**에서 액션 미수행
2. 방장이 첫 주지사를 잡지 못함
3. `401 Unauthorized` on `/api/puco/auth/me` (프론트엔드 인증 -- 봇 무관)

### 핵심 추론

**Random 봇마저 작동하지 않는다** = 모델/obs_dim/Mayor 폴백 문제가 **아님**.
스케줄링 자체가 발동하지 않거나, `run_bot_turn` 초입에서 침묵 실패 중.

---

## 결함 분석

### 결함 A: `run_bot_turn` 최상위 try-except 누락 (P0)

`run_bot_turn`이 `asyncio.create_task()`로 실행되므로,
코루틴 내부에서 catch되지 않는 예외 발생 시 **태스크가 로그 없이 소멸**.

현재 보호되지 않은 영역:

```python
# bot_service.py:104~116 -- try-except 바깥
mask = engine.get_action_mask()         # 예외 시 -> 코루틴 즉사
is_role_selection = any(mask[0:8])
delay = 3.0 if is_role_selection else 2.0
await asyncio.sleep(delay)
current_phase = _extract_phase_id(engine.last_obs)  # 예외 시 -> 코루틴 즉사
game_context = { ... }
```

`get_action()`과 `process_action_callback()`은 각각 try-except 안이지만,
**그 바깥 코드는 무방비**. 여기서 어떤 예외라도 발생하면 로그 0줄, 게임 고착.

### 결함 B: 진단 로그 부족 (P0)

현재 `_schedule_next_bot_turn_if_needed`에 로그가 전혀 없음.
스케줄링이 호출되었는지, 어떤 플레이어에게 트리거되었는지 추적 불가.

`run_bot_turn` 시작 시 로그도 `logger.debug` (기본 레벨 INFO에서 안 보임).

### 결함 C: 주지사 배정 불일치 (P1)

`engine.py:65`에서 `governor_idx = random.randint(0, num_players - 1)`.
방장이 항상 `room.players[0]`이지만, 엔진 주지사는 랜덤.
UI에서 "방장 = 주지사"를 기대하면 불일치.

---

## 수정 대상 파일

| # | 파일 | 변경 내용 |
|---|------|----------|
| 1 | `backend/app/services/bot_service.py` | `run_bot_turn` 전체를 try-except로 감싸기 + INFO 로그 강화 |
| 2 | `backend/app/services/game_service.py` | `_schedule_next_bot_turn_if_needed`에 INFO 로그 추가 |
| 3 | `backend/app/engine_wrapper/wrapper.py` | 주지사를 player_0으로 고정 (reset 반복 방식) |

---

## 4-A. `bot_service.py` -- `run_bot_turn` 전면 수정

**목표:** 어떤 예외에서도 로그를 남기고, 코루틴이 조용히 죽지 않게 한다.

```python
@staticmethod
async def run_bot_turn(game_id, engine, actor_id, process_action_callback):
    """Background task to execute a bot's turn with UX delay."""
    logger.info("[BOT] turn start game=%s actor=%s", game_id, actor_id)
    try:
        mask = engine.get_action_mask()
        valid_count = sum(1 for v in mask if v)
        logger.info("[BOT] game=%s valid_actions=%d", game_id, valid_count)

        is_role_selection = any(mask[0:8])
        delay = 3.0 if is_role_selection else 2.0
        await asyncio.sleep(delay)

        current_phase = _extract_phase_id(engine.last_obs)
        game_context = {
            "vector_obs": engine.last_obs,
            "action_mask": mask,
            "phase_id": current_phase,
        }

        # 1. Model Inference
        try:
            action_int = BotService.get_action(game_context)
            logger.info("[BOT] game=%s action=%d phase=%d", game_id, action_int, current_phase)
        except Exception as e:
            logger.exception("[BOT] inference failed game=%s", game_id)
            valid_indices = [i for i, v in enumerate(mask) if v > 0.5]
            action_int = int(np.random.choice(valid_indices)) if valid_indices else 15

        # 2. Action Application with Retry
        try:
            if asyncio.iscoroutinefunction(process_action_callback):
                await process_action_callback(game_id, actor_id, action_int)
            else:
                process_action_callback(game_id, actor_id, action_int)
            logger.info("[BOT] game=%s action=%d applied OK", game_id, action_int)
        except Exception as e:
            logger.error("[BOT] action %d REJECTED game=%s: %s", action_int, game_id, e)
            try:
                retry_mask = engine.get_action_mask()
                valid = [i for i, v in enumerate(retry_mask) if v > 0.5 and i != action_int]
                if valid:
                    fallback = int(np.random.choice(valid))
                    logger.warning("[BOT] retry game=%s fallback=%d", game_id, fallback)
                    if asyncio.iscoroutinefunction(process_action_callback):
                        await process_action_callback(game_id, actor_id, fallback)
                    else:
                        process_action_callback(game_id, actor_id, fallback)
                else:
                    logger.critical("[BOT] no valid fallback game=%s", game_id)
            except Exception as retry_err:
                logger.critical("[BOT] fallback FAILED game=%s: %s", game_id, retry_err)

    except Exception as e:
        logger.critical(
            "[BOT] UNHANDLED ERROR game=%s actor=%s: %s",
            game_id, actor_id, e, exc_info=True
        )
```

**변경 포인트:**

- 전체 로직을 최상위 `try-except`로 감쌈
- `logger.debug` -> `logger.info`로 승격 (Docker에서 보이도록)
- `[BOT]` 태그로 통일하여 `grep` 추적 용이

---

## 4-B. `game_service.py` -- 스케줄링 로그 추가

```python
def _schedule_next_bot_turn_if_needed(self, game_id, room, engine):
    next_idx = engine.env.game.current_player_idx
    players = room.players or []
    logger.info("[SCHEDULE] game=%s next_idx=%d players=%s", game_id, next_idx, players)

    if not players or next_idx >= len(players):
        logger.warning("[SCHEDULE] game=%s abort: idx %d out of range (len=%d)",
                        game_id, next_idx, len(players))
        return

    next_actor = players[next_idx]
    if str(next_actor).startswith("BOT_"):
        logger.info("[SCHEDULE] game=%s -> bot turn for %s (idx=%d)",
                     game_id, next_actor, next_idx)
        from app.services.bot_service import BotService
        from app.dependencies import SessionLocal

        def sync_callback(bg_game_id, bg_actor_id, bg_action):
            with SessionLocal() as bg_db:
                bg_service = GameService(bg_db)
                bg_service.process_action(bg_game_id, bg_actor_id, bg_action)

        task = asyncio.create_task(
            BotService.run_bot_turn(
                game_id=game_id,
                engine=engine,
                actor_id=next_actor,
                process_action_callback=sync_callback
            )
        )
        GameService._bot_tasks.add(task)
        task.add_done_callback(GameService._bot_tasks.discard)
    else:
        logger.info("[SCHEDULE] game=%s -> human turn for %s (idx=%d)",
                     game_id, next_actor, next_idx)
```

**변경 포인트:**

- 스케줄링 호출 시 `next_idx`, `players` 목록, 대상 actor 전부 INFO 로그
- 인덱스 범위 초과 시 WARNING 로그
- 사람 차례일 때도 로그 남겨서 흐름 추적

---

## 4-C. `engine_wrapper/wrapper.py` -- 주지사 player_0 고정

`engine.py:65`에서 `governor_idx = random.randint(...)` -> `_setup_players()`가 이 값 기준으로 초기 plantation 배분.
`reset()` 후 단순히 `governor_idx = 0`으로 바꾸면 plantation 배분과 불일치.

**안전한 방법: `reset()`을 governor가 0이 될 때까지 반복 호출.**

```python
class EngineWrapper:
    def __init__(self, num_players=3, max_game_steps=1200):
        if PuertoRicoEnv is None:
            raise RuntimeError("PuertoRicoEnv could not be imported.")
        self.env = PuertoRicoEnv(num_players=num_players, max_game_steps=max_game_steps)

        # 주지사가 player_0(방장)이 될 때까지 reset 반복
        # engine.py에서 governor_idx = random.randint(0, n-1)이므로 평균 n번 시도
        for _ in range(100):
            self.env.reset()
            if self.env.game.governor_idx == 0:
                break
        else:
            # 100번 안에 못 맞추면(확률적으로 불가능) 강제 설정
            self.env.game.governor_idx = 0
            self.env.game.current_player_idx = 0

        obs_dict = self.env.observe(self.env.agent_selection)
        self.last_obs = obs_dict["observation"]
        self.last_info = self.env.infos[self.env.agent_selection]
        self.last_action_mask = obs_dict["action_mask"]
        self._step_count = 0
        self._round_count = 0
        self._last_governor = self.env.game.governor_idx
```

**장점:** `reset()`이 `start_game()` -> `_setup_players()` -> plantation 배분을 포함하므로,
`governor_idx=0`일 때의 reset 결과는 **완전히 정합적**. 엔진 내부 수정 없음.

**비용:** 평균 `num_players`(=3)회 reset. 게임 시작 시 1회만 발생하므로 무시 가능.

---

## TDD 테스트

### 테스트 1: `run_bot_turn` 최상위 예외 방어

**파일:** `backend/tests/test_bot_service_safety.py` (기존 파일에 추가)

```python
class TestRunBotTurnTopLevelSafety:
    """run_bot_turn 최상위에서 예외가 발생해도 crash하지 않아야 한다."""

    @pytest.mark.asyncio
    async def test_engine_get_action_mask_error_caught(self):
        """engine.get_action_mask() 실패해도 코루틴이 예외 없이 종료."""
        engine = MagicMock()
        engine.get_action_mask.side_effect = RuntimeError("Engine corrupt")
        callback = MagicMock()

        # 예외가 전파되지 않아야 한다
        await BotService.run_bot_turn(
            game_id="test-game",
            engine=engine,
            actor_id="BOT_random",
            process_action_callback=callback,
        )
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_engine_last_obs_none_caught(self):
        """engine.last_obs가 None이어도 코루틴이 예외 없이 종료."""
        engine = MagicMock()
        engine.get_action_mask.return_value = [0]*200
        engine.last_obs = None
        callback = MagicMock()

        await BotService.run_bot_turn(
            game_id="test-game",
            engine=engine,
            actor_id="BOT_ppo",
            process_action_callback=callback,
        )
        # crash만 안 하면 됨
```

### 테스트 2: 주지사 player_0 고정

**파일:** `backend/tests/test_governor_assignment.py` (신규)

```python
import pytest
from app.engine_wrapper.wrapper import EngineWrapper


def test_governor_is_always_player_0():
    """EngineWrapper 생성 시 주지사가 항상 player_0이어야 한다."""
    for _ in range(10):
        engine = EngineWrapper(num_players=3)
        assert engine.env.game.governor_idx == 0
        assert engine.env.game.current_player_idx == 0


def test_initial_plantation_consistent_with_governor_0():
    """governor가 0일 때 player_0이 인디고를 받아야 한다."""
    engine = EngineWrapper(num_players=3)
    game = engine.env.game
    p0 = game.players[0]

    from configs.constants import TileType
    has_indigo = any(t.tile_type == TileType.INDIGO_PLANTATION for t in p0.island_board)
    assert has_indigo
```

---

## 구현 순서

```
4-A (즉시)              4-B (즉시)              4-C (즉시)
+------------------+   +------------------+   +------------------+
| bot_service.py   |   | game_service.py  |   | wrapper.py       |
| 최상위 try-      |   | [SCHEDULE] 로그  |   | governor=0 고정  |
| except + 로그    |   | 추가             |   | (reset 반복)     |
+------------------+   +------------------+   +------------------+
         |                      |                      |
         v                      v                      v
  test_bot_service_    test_bot_task_         test_governor_
  safety.py 추가       reference.py 추가     assignment.py 신규
```

**4-A + 4-B 먼저 배포 -> Docker 로그에서 정확한 실패 지점 확인 -> 4-C 적용**

---

## 검증 체크리스트

### 단위 테스트

- [ ] `test_engine_get_action_mask_error_caught` -- 최상위 예외 방어
- [ ] `test_engine_last_obs_none_caught` -- last_obs None 방어
- [ ] `test_governor_is_always_player_0` -- 주지사 고정
- [ ] `test_initial_plantation_consistent_with_governor_0` -- plantation 정합성
- [ ] 기존 Phase 1~3 테스트 전부 회귀 없음

### Docker 통합 테스트

- [ ] 로그에 `[SCHEDULE]` 태그 출력 확인
- [ ] 로그에 `[BOT] turn start` 태그 출력 확인
- [ ] 봇 3인전 시작 -> 첫 역할 선택 -> 봇이 액션 수행
- [ ] 방장(player_0)이 첫 주지사로 표시
- [ ] 게임 완주(종료까지 고착 없이 진행)



puco_backend   | INFO:     127.0.0.1:60172 - "GET /health HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:46808 - "GET /api/puco/auth/me HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:46814 - "GET /api/puco/auth/me HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:46818 - "GET /api/puco/rooms/ HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:46826 - "GET /api/puco/rooms/ HTTP/1.1" 200 OK
puco_backend   | INFO:     127.0.0.1:60178 - "GET /health HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:54094 - "POST /api/puco/rooms/ HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:54110 - "GET /api/bot-types HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:54122 - "GET /api/bot-types HTTP/1.1" 200 OK
puco_backend   | INFO:     127.0.0.1:43020 - "GET /health HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:54132 - "POST /api/puco/game/32f2597d-0202-4263-9135-3520288ea3c9/add-bot HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:54144 - "POST /api/puco/game/32f2597d-0202-4263-9135-3520288ea3c9/add-bot HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:54160 - "POST /api/puco/game/32f2597d-0202-4263-9135-3520288ea3c9/start HTTP/1.1" 200 OK
puco_backend   | INFO:     127.0.0.1:43030 - "GET /health HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:53902 - "POST /api/puco/game/32f2597d-0202-4263-9135-3520288ea3c9/action HTTP/1.1" 200 OK
puco_backend   | INFO:     172.18.0.3:53918 - "POST /api/puco/game/32f2597d-0202-4263-9135-3520288ea3c9/action HTTP/1.1" 200 OK
테스트 결과 아직도 봇이 행동을 안하고, 이번엔 주지사가 방장에게 고정되고 있어 주지사는 3명의 플레이어(봇 포함) 중 랜덤으로 배정되게 해줘  
예전에 봇의 행동을 2~3초 정도 늦추는 로직을 작성한적이 있는데 그것 때문인지도 봐줘 

기존에 너가 수정하기 전에는 방장 플레이어는 첫 주지사를 받을 수 없는 버그가 있었고 너가 수정한 후(지금)은 방장만 첫 주지사를 받는 버그가 발생해
내가 원하는 점은 첫 주지사는 플레이어 3명 중 랜덤으로 배정되는거야

수정 전 옛날 로직의 버그 : 첫 주지사가 방장을 제외한 다른 2명의 플레이어에게만 배정되었다
현재 버그 : 첫 주지사가 오직 방장에게만 배정된다
**내가 원하는 방향 : 첫 주지사가 방장을 포함한 플레이어 중 랜덤으로 배정되는것** 


또한 첫 봇 턴에서 스케줄 한다고 하는데 애초에 봇이 처음 턴이든 아니면 나중 턴이든 행동 자체를 안하고 있어 백엔들 로그 상은 저 위의 로그만 나오고, 프론트 부분에서는 Bot 님의 차롈르 기다리는 중... 이러면서 아무런 행동도 하지 않아 