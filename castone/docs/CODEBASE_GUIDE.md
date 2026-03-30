# Castone — 코드베이스 이해 가이드

> 작성일: 2026-03-30
> 목적: 프로젝트 전체 구조를 이해하기 위한 지도 + 핵심 질문 모음

---

## 1. 한 줄 요약

**Puerto Rico 보드게임을 멀티플레이어로 플레이하면서, 사람과 AI의 모든 행동을 PostgreSQL에 기록해 RL 학습 데이터를 수집하는 플랫폼.**

---

## 2. 전체 디렉토리 지도

```
castone/
├── frontend/                  ← React 19 + Vite (브라우저 뷰어)
│   └── src/
│       ├── App.tsx            ← 라우팅 + 세션 상태 최상위 관리
│       ├── components/        ← 게임 UI 컴포넌트들
│       ├── hooks/
│       │   ├── useGameWebSocket.ts  ← WS 상태 수신 (v1 API 전용)
│       │   └── useGameSSE.ts        ← SSE 상태 수신 (레거시 API 전용)
│       ├── types/
│       │   └── gameState.ts   ← 프론트-백 공유 타입 계약
│       └── locales/           ← ko.json, en.json, it.json
│
├── backend/                   ← FastAPI (게임 로직의 유일한 권한자)
│   └── app/
│       ├── main.py            ← FastAPI 앱, 미들웨어, 라우터 등록
│       ├── api/
│       │   ├── v1/            ← 정식 API (OAuth + 게임 + WS)
│       │   │   ├── auth.py    ← Google OAuth → JWT 발급
│       │   │   ├── room.py    ← 방 생성/목록
│       │   │   ├── game.py    ← 게임 시작/액션 제출
│       │   │   └── ws.py      ← WebSocket 연결 관리
│       │   └── legacy/        ← 테스트용 심플 API (인증 없음)
│       │       ├── lobby.py   ← 멀티플레이어 로비 (init/join/start)
│       │       ├── actions.py ← 게임 액션 (역할선택/정착/건설 등)
│       │       ├── game.py    ← 상태 조회 (server-info, game-state)
│       │       └── events.py  ← SSE 스트림 (GET /events/stream)
│       ├── services/
│       │   ├── game_service.py      ← 핵심 게임 로직 오케스트레이터
│       │   ├── session_manager.py   ← 레거시 인메모리 세션 싱글턴
│       │   ├── bot_service.py       ← PPO/HPPO 추론 + 봇 턴 실행
│       │   ├── event_bus.py         ← asyncio.Queue Pub/Sub (SSE용)
│       │   ├── ws_manager.py        ← WebSocket 브로드캐스트 + 연결 추적
│       │   ├── state_serializer.py  ← 엔진 상태 → JSON 변환
│       │   ├── action_translator.py ← 프론트 payload → 액션 정수 변환
│       │   ├── ml_logger.py         ← 비동기 JSONL 로깅
│       │   └── agent_registry.py    ← 사용 가능한 봇 타입 목록
│       ├── engine_wrapper/
│       │   └── wrapper.py     ← PuCo_RL PettingZoo AEC 인터페이스 래핑
│       ├── db/
│       │   └── models.py      ← User, GameSession, GameLog SQLAlchemy 모델
│       ├── core/
│       │   ├── security.py    ← JWT 생성/검증
│       │   └── redis.py       ← sync/async Redis 클라이언트
│       └── dependencies.py    ← DB 세션, 현재 유저 FastAPI 의존성
│
├── PuCo_RL/                   ← 게임 엔진 (Pure Python, 백엔드가 import)
│   ├── env/
│   │   ├── engine.py          ← PuertoRicoGame 상태 머신 (핵심 규칙)
│   │   └── pr_env.py          ← Gymnasium/PettingZoo AEC 래퍼
│   ├── agents/
│   │   ├── ppo_agent.py       ← 표준 PPO 에이전트
│   │   └── ppo_agent_phase.py ← 페이즈 인식 HPPO 에이전트
│   ├── models/                ← 학습된 .pth 가중치 파일들
│   └── configs/
│       └── constants.py       ← Phase, Role, Good, BuildingType 열거형
│
├── data/
│   └── logs/                  ← transitions_YYYY-MM-DD.jsonl (RL 학습 데이터)
│
├── docs/                      ← 설계 문서들
│   ├── POLLING_TO_SSE_DESIGN.md
│   └── CODEBASE_GUIDE.md      ← 이 파일
│
├── docker-compose.yml         ← 개발 환경 (db + redis + backend + frontend + adminer)
├── docker-compose.prod.yml    ← 프로덕션 환경
├── ARCHITECTURE.md            ← 공식 아키텍처 문서
└── CLAUDE.md                  ← Claude Code 작업 지침
```

---

## 3. 두 개의 API 레이어 — 왜 있는가?

이 프로젝트에는 **API가 두 벌** 존재한다.

```
/api/puco/*   (v1)      ← 정식 API. Google OAuth 필요. PostgreSQL 기록.
/api/*        (legacy)  ← 테스트용 심플 API. 인증 없음. 인메모리 세션.
```

| 항목 | v1 API | Legacy API |
|---|---|---|
| 경로 | `/api/puco/rooms`, `/api/puco/game`, `/api/puco/ws` | `/api/lobby/*`, `/api/action/*`, `/api/events/stream` |
| 인증 | Google OAuth + JWT | 없음 (INTERNAL_API_KEY 선택적) |
| 세션 저장 | PostgreSQL + Redis | 인메모리 `SessionManager` |
| RL 로깅 | PostgreSQL `game_logs` + JSONL | 없음 |
| 실시간 | WebSocket (`ws_manager.py`) | SSE (`event_bus.py`) |
| 현재 프론트 연결 | 미연결 (코드 있으나 미사용) | **연결됨 (App.tsx에서 사용)** |

> **핵심 모순:** 현재 프론트엔드는 인증 없는 Legacy API에 연결되어 있다.
> v1 API (RL 로깅 포함)는 코드는 완성되어 있으나 프론트에서 사용하지 않는다.

---

## 4. 데이터 흐름 전체 지도

### 4-1. 사람 플레이어 액션 흐름

```
사용자 클릭 (브라우저)
    │
    ▼
POST /api/action/{action_type}    [legacy API]
    │
    ▼
deps._step(action)
    ├─ session.game.get_action_mask() 검증
    └─ session.game.step(action)  ←── EngineWrapper
                                           │
                                           ▼
                                    PuertoRicoEnv.step(action)
                                    PuertoRicoEnv.observe()
    │
    ▼
session.add_history(action_name, params)
    │
    ▼
_run_pending_bots()
    ├─ _publish_state_update()   →  Redis Pub/Sub  →  WebSocket 브로드캐스트
    └─ [봇 턴들 실행]
        └─ BotService.get_action()  →  PPO/HPPO 추론
    │
    ▼
event_bus.publish(key, "state_update", gs_json)  →  SSE 클라이언트들
    │
    ▼
serialize_game_state(session) 반환
    │
    ▼
프론트 setState(gs)  →  리렌더링
```

### 4-2. SSE 상태 동기화 흐름

```
프론트 (useGameSSE)              백엔드 (/api/events/stream)
    │                                      │
    ├──── GET /events/stream ─────────────►│
    │                                      ├─ event_bus.subscribe(key)
    │◄─── event: ping ─────────────────────│  (연결 확인 즉시 ping)
    │                                      │
    │  [다른 플레이어가 액션 실행]            │
    │                                      ├─ lobby_start() 또는 action()
    │                                      ├─ event_bus.publish("state_update", gs)
    │◄─── event: state_update ─────────────│
    │     data: {meta, players, ...}        │
    │                                      │
    ├─ onStateUpdate(gs) 콜백              │
    └─ setState → 리렌더링                 │
```

### 4-3. RL 데이터 수집 흐름 (v1 API 한정)

```
모든 액션 (사람/봇 불문)
    │
    ▼
GameService.process_action()
    │
    ├─►  PostgreSQL game_logs
    │    {
    │      game_id, round, step, actor_id,
    │      state_before, action, action_mask,
    │      state_after, reward, done, state_summary
    │    }
    │
    └─►  /data/logs/transitions_YYYY-MM-DD.jsonl
         (비동기 append, 오프라인 재학습용)
```

---

## 5. 레거시 API 액션 정수 매핑

프론트에서 보내는 "action_type"이 엔진의 정수로 변환되는 방식:

| 범위 | 액션 | 예시 |
|---|---|---|
| 0–7 | `select_role` | 0=settler, 1=mayor, 2=builder... |
| 8–13 | `settle_plantation` (face-up) | 8=인덱스0 타일 |
| 14 | `settle_quarry` | 고정값 |
| 15 | `pass` | 모든 페이즈 공통 |
| 16–38 | `build` | 16+BuildingType.value |
| 39–43 | `sell` | 39+Good.value |
| 44–58 | `load_ship` | 44+(ship_idx×5)+good |
| 59–63 | `load_wharf` | 59+good |
| 64–68 | `store_windrose` | 64+good |
| 69–80 | `mayor_toggle_island` | 69+slot_idx |
| 81–92 | `mayor_toggle_city` | 81+slot_idx |
| 93–97 | `craftsman_privilege` | 93+good |
| 105 | `use_hacienda` | 고정값 |
| 106–110 | `store_warehouse` | 106+good |

---

## 6. 게임 페이즈 상태 머신

```
role_selection
    │
    ├─► settler_action      → (정착/채석장 선택)
    ├─► mayor_distribution  → mayor_action (식민지 배치)
    ├─► builder_action      → (건물 건설)
    ├─► craftsman_action    → (생산)
    ├─► trader_action       → (교역소 판매)
    └─► captain_action      → captain_discard (화물선 적재 → 잉여 폐기)
         │
         ▼
    role_selection (다음 라운드)
```

---

## 7. 봇 타입별 차이

| 봇 타입 | 클래스 | 특징 |
|---|---|---|
| `random` | `RandomAgent` | 유효한 액션 중 무작위 선택 |
| `ppo` | `Agent` (standard PPO) | 단일 관측 벡터 입력 |
| `hppo` | `PhasePPOAgent` | 현재 페이즈 ID를 추가 입력으로 사용 |

**모델 파일:** `PuCo_RL/models/*.pth`
**환경변수로 선택:** `PPO_MODEL_FILENAME`, `HPPO_MODEL_FILENAME`

---

## 8. Docker 서비스 구성

```
docker-compose.yml
    │
    ├─ db (postgres:16-alpine :5432)
    │    └─ 볼륨: pgdata
    │
    ├─ redis (redis:7-alpine :6379)
    │    └─ 볼륨: redisdata
    │
    ├─ backend (Python 3.12 FastAPI :8000)
    │    ├─ 의존: db + redis (healthy)
    │    ├─ 볼륨: ./backend:/app (핫 리로드)
    │    └─ 볼륨: ./PuCo_RL:/PuCo_RL:ro
    │
    ├─ frontend (Nginx :3000)
    │    └─ /api → backend:8000 프록시
    │
    └─ adminer (:8080)  ← 개발 전용 DB 관리
```

---

## 9. 이 프로젝트를 이해하기 위한 핵심 질문들

### 9-1. 아키텍처 의도 관련

> **Q1.** v1 API(Google OAuth 포함, RL 로깅 포함)가 완성되어 있는데
> 현재 프론트는 Legacy API(인증 없음)에 연결되어 있다.
> **v1 API로의 전환은 언제 할 계획인가? 어떤 기능이 블로커인가?**

> 할 수 있는 한 바로 진행하고 싶은데, 각각의 기능들에 대해 v1으로 전부 전환해 버리는게 괜찮은 선택일지 잘 모르겠다
> 각각의 기능들에 어울리는 api 를 정의해줘라(web socker, rest api 이런식으로)
> 게임 내, 실시간으로 상태 업데이트 해야하는 부분과은 ws를 사용해야하지만, 그 외에 인증, 로비, 게임 액션 선택 같은 경우는 rest로 해줘



> **Q2.** `SessionManager`가 인메모리 싱글턴이다.
> 서버가 재시작되면 진행 중인 게임이 사라진다.
> **이 싱글턴을 Redis나 PostgreSQL로 교체할 계획이 있는가?**
> 교체하지 않는다면, 이 플랫폼은 "재시작하면 게임 날아가도 되는" 개발/연구용으로만 쓰는 건가?

> 이 플랫폼은 연구용으로 사용된다

> **Q3.** `GameService.active_engines`도 인메모리다.
> 수평 확장(서버 인스턴스를 늘리면)이 불가능하다.
> **이 플랫폼의 최대 동시 게임 수를 어느 정도로 상정하고 있는가?**

> 최대 20 ~ 30 게임정도를 생각하고 있다

---

### 9-2. 데이터 & RL 파이프라인 관련

> **Q4.** `/data/logs/transitions_*.jsonl`에 쌓이는 데이터를
> 실제로 모델 재학습에 사용하고 있는가?
> **재학습 파이프라인이 구현되어 있는가, 아니면 데이터만 수집 중인가?**

> 아직 구현이 안되었고, 실제 쌓이는 로그들의 정확성을 의심하고 있다
> 게임이 끝났는데 상점과, 더블룬의 개수가 변화하지 않는다는건 뭔가 이상하다


[문제 진단]
원인 1: 엔진의 step() 이후 observe()를 호출할 때, 특정 페이즈(예: 상인 페이즈)의 변화가 StateSerializer에서 누락되었을 가능성.

원인 2: 비동기 로깅(ml_logger.py) 시점의 문제. 엔진 상태가 완전히 업데이트되기 전의 snapshot을 찍고 있을 수 있음.

[로깅 아키텍처 개선 설계안]
로깅 누락을 방지하고 정확성을 높이기 위한 설계입니다.

중앙 집중식 로깅 (Interceptor 패턴):

Legacy API와 v1 API가 모두 사용하는 GameService.step() 메서드 마지막에 로깅 로직을 강제합니다.

action → engine.step() → verify_state_change() (검증) → log_to_db_and_jsonl() 순서로 실행합니다.

상태 검증 로직 추가:

로깅 직전에 "이전 상태"와 "현재 상태"를 비교하여, 액션이 일어났음에도 자원 변화가 전혀 없다면 경고(Warning)를 남기거나 에러를 발생시켜 데이터 오염을 막습니다.

V1 통합:

Legacy API 엔드포인트를 호출하더라도 내부적으로는 v1의 GameService를 거치게 하여, 프론트엔드 코드를 수정하기 전이라도 데이터는 무조건 DB에 쌓이도록 강제합니다.
> 이런 방식의 설계를 한번 생각해보고 괜찮은지 판단


> **Q5.** PostgreSQL `game_logs` 테이블과 JSONL 파일 두 곳에 동시 기록한다.
> PostgreSQL은 indexed, JSONL은 streamable이다.
> **각각의 사용 목적이 다른가? 중복이 맞는가, 아니면 하나를 제거할 계획인가?**

> 나중에 배포할 예정이므로, 결과적으로 게임 로그들은 postgresql에 저장되거나, gcp의 cloud에 저장될 예정이다

> **Q6.** RL 로깅이 Legacy API에는 없고 v1 API에만 있다.
> 현재 프론트가 Legacy API를 쓰는 상황에서는 **게임 데이터가 전혀 기록되지 않고 있다.**
> 이걸 인지하고 있는가?

> 이제 인지했고 고치기 위한 설계 계획서를 써달라 /brainstorming

---

### 9-3. 실시간 통신 이중화 관련

> **Q7.** 현재 WebSocket(`ws_manager.py` + Redis Pub/Sub)과
> SSE(`event_bus.py` + asyncio.Queue) **두 개의 실시간 채널이 공존한다.**
> WS는 v1 API 전용, SSE는 Legacy API 전용이다.
> **최종적으로 하나로 통합할 계획인가? 어느 쪽을 살릴 건가?**

> 각각의 장단점을 알려주고, 현재 플랫폼에서의 장단점을 알려줘라


> **Q8.** `event_bus.py`의 `EventBus`는 단일 프로세스에서만 동작한다.
> uvicorn을 멀티 워커로 띄우면 SSE가 깨진다.
> **현재 프로덕션에서 워커는 몇 개인가?**

> 연구용으로 사용되므로, 워커는 1개로 충분할 거 같다



---

### 9-4. 게임 엔진 인터페이스 관련

> **Q9.** PettingZoo AEC의 핵심 특징은 `env.step()` 반환값이 `None`이고,
> 결과는 `env.observe(agent_selection)`으로 따로 읽어야 한다.
> **EngineWrapper가 이 패턴을 정확히 추상화하고 있는가?**
> 신규 기능을 추가할 때 이 패턴을 직접 이해해야 하는 상황이 발생하는가?

> 정확하게 추상화 되고 있는지 테스트해보고, 새로운 에이전트가 추가되거나, 게임의 규칙을 직접 바꿔서 게임의 밸런스를 검증해보는 일은 있겠지만, 
> 그렇게 신규 기능을 추가할 거 같지는 않아


> **Q10.** Mayor 페이즈에서 봇이 slot을 toggle하는 방식이 복잡하다.
> `mayor_toggle_island(slot_idx)` → 봇이 최대 30번 toggle 후 강제 pass.
> **이 30회 제한은 실험적으로 정한 값인가? 실제 게임 규칙과 맞는가?**

> 현재는 봇은 순차방식으로 되어있고, 플레이어는 토글 방식으로 되어있는걸로 알고있는데 이거 검증해줘

---

### 9-5. 보안 & 인증 관련

> **Q11.** Legacy API에는 `INTERNAL_API_KEY`가 있지만,
> 멀티플레이어 로비(`lobby/join`, `lobby/add-bot` 등)에는 이 키 검증이 없다.
> `/api/lobby/join`에 아무나 접속하면 방에 들어올 수 있다.
> **이건 의도된 설계인가 (비공개 세션 키로 접근 제어)?
> 아니면 미완성 인증 로직인가?**

> 처음에 로비에 접속할 때, 새로운 방을 만드는 것과, 기존에 다른 플레이어들이 만든 방을 볼 수 있게 만들어줘
> 방은 비밀방, 공개방이 있고, 비밀방은 오른쪽 위에 자물쇠 잠금 표시로 비밀방인걸 표시해줘
> 각 방은 현재 인원/최대 정원을 보이게 하고, 중앙 밑에 입장하기 버튼을 만들어줘(정원이 다 찬 방은 그 버튼을 비활성화 해줘)
> 왼쪽 위에는 그 방의 이름을 보이게 해줘
> 비밀방 접속할 때는 방을 만든 플레이어가 설정한 비밀번호를 맞추면 들어갈수 있게 해줘 
> 처음에 방을 만들 때 비밀방, 공개방을 설정할 수 있게하고, 비밀방은 비밀방 비밀번호를 플레이어가 설정할 수 있게 해줘(4자리 숫자로)
> 또한 처음에 방의 이름을 설정할 수 있게 하고, 그 방의 이름은 다른 방의 이름들과 겹치지 않게 해줘

> 세션키 관련되서는 위의 작업을 완수하고, 보안 관련 상황을 다시 확인해서 ㄱㄱ

> **Q12.** `INTERNAL_API_KEY`가 `.env`에 `dev-internal-key-change-me`로 설정되어 있다.
> **프로덕션 배포 시 이 키를 바꾸는 절차가 있는가?**

> python 로직을 활용해서 만들어줘

---

### 9-6. 프론트엔드 관련

> **Q13.** `App.tsx`가 1,600줄이 넘는다. 화면 라우팅, API 호출, 게임 상태, 폴링,
> 마이어 배치 UI까지 모두 한 파일에 있다.
> **언제 컴포넌트 분리를 할 계획인가? 아니면 이 규모면 괜찮다고 판단하는가?**

> 이건 나중에

> **Q14.** `useGameWebSocket`과 `useGameSSE` 두 훅이 있다.
> 현재 `useGameWebSocket`은 `gameId: null`로 호출되어 사실상 비활성화된 상태다.
> **이 훅은 향후 v1 API 전환 시 사용할 예비 코드인가, 아니면 제거 대상인가?**

> 예비 코드이다

---

### 9-7. 운영 & 배포 관련

> **Q15.** Alembic 마이그레이션 파일이 3개 있다.
> 현재 DB 스키마와 최신 마이그레이션이 일치하는가?
> **`alembic upgrade head`를 실행하면 최신 상태가 되는가?**

> 테스트 해보고 알려줘라

> **Q16.** `data/logs/transitions_*.jsonl` 파일이 무한히 쌓인다.
> **로그 로테이션 정책이 있는가? 디스크 관리 계획은?**

> 에이전트 학습용 데이터로 활용될 예정이고, 나중에 mlops로 관리할 예정이다 아마 다른 클라우드 저장소에 저장할 거같다

---

## 10. 구조 이해를 위한 핵심 코드 읽기 순서

처음 이 코드베이스를 이해하려면 이 순서로 읽는 것을 추천한다:

```
1. PuCo_RL/configs/constants.py
   → Phase, Role, Good, BuildingType 열거형 이해
   → 이걸 모르면 액션 매핑이 이해 안 됨

2. backend/app/engine_wrapper/wrapper.py
   → EngineWrapper.step() 반환 구조 파악
   → state_before / state_after / action_mask 구조

3. backend/app/services/state_serializer.py
   → 엔진 raw 상태 → 프론트 JSON 변환 로직

4. backend/app/api/legacy/actions.py
   → 실제 게임 액션 엔드포인트들
   → mayor-distribute가 왜 복잡한지 이해

5. backend/app/services/session_manager.py
   → 인메모리 싱글턴 구조와 그 한계

6. frontend/src/types/gameState.ts
   → 프론트-백 공유 타입 계약

7. frontend/src/App.tsx (800번째 줄 이후)
   → 게임 화면 렌더링 로직
```

---

## 11. 현재 알려진 기술 부채

| 항목 | 위치 | 위험도 | 설명 |
|---|---|---|---|
| 프론트-백 API 불일치 | App.tsx + v1 API | 🔴 높음 | 프론트가 RL 로깅 없는 Legacy API 사용 중 |
| 인메모리 세션 | SessionManager | 🟡 중간 | 재시작 시 세션 소실 |
| 인메모리 엔진 | GameService.active_engines | 🟡 중간 | 단일 인스턴스 제약 |
| App.tsx 1600줄 | frontend/src/App.tsx | 🟡 중간 | 분리 필요 |
| SSE 단일 프로세스 | event_bus.py | 🟡 중간 | 멀티워커 시 깨짐 |
| 로비 인증 없음 | legacy/lobby.py | 🟠 낮음 | 세션 키로만 보호됨 |
| 로그 무한 누적 | /data/logs/ | 🟠 낮음 | 로테이션 정책 없음 |

---

## 12. 핵심 설계 결정 요약

| 결정 | 이유 |
|---|---|
| 서버 권한 모델 | 프론트는 pure viewer. 모든 게임 로직은 백엔드. 치팅 불가. |
| PettingZoo AEC 사용 | RL 학습 환경과 동일한 인터페이스 유지 → 훈련/서빙 일관성 |
| 액션 정수 공간 (0-199) | 학습 모델의 출력 공간과 1:1 대응 |
| JSONL + PostgreSQL 이중 기록 | JSONL: 스트리밍 재학습용 / PostgreSQL: 쿼리/분석용 |
| Legacy API 유지 | v1 전환 전 빠른 기능 개발 + 봇만으로 테스트 가능 |
