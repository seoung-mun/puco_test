# Fullstack Architecture Analysis (AS-IS)

본 문서는 `@[senior-fullstack]` 관점에서 현재 나뉘어져 있는 두 개의 주요 프로젝트(`puertorico`, `castone`)와 핵심 엔진(`PuCo_RL`) 간의 아키텍처 구조, 관계, 데이터베이스 및 도커 컨테이너 연결 생태계를 심층 분석한 명세서입니다.

---

## 1. 생태계 개요 (Ecosystem Overview)

현재 시스템은 **코어 게임 엔진(`PuCo_RL`)**을 중심으로, 이를 활용하는 두 가지 서로 다른 컨텍스트의 프로젝트로 나뉘어져 있습니다.

1. **`castone/PuCo_RL` (Core Engine & ML)**: 게임의 룰(Domain Logic)과 강화학습(RL) 파이프라인이 정의된 핵심 코어.
2. **`puertorico/` (Local / Bot Testing Mode)**: 가벼운 상태 저장(JSON)과 폴링(Polling) 기반의 로컬 봇 테스트 및 시각화를 위한 프로젝트.
3. **`castone/` (Multiplayer Production Mode)**: Redis, PostgreSQL, WebSockets를 활용한 실시간 다중 접속 멀티플레이어 환경 프로젝트.

---

## 2. 모듈별 상세 아키텍처 및 관계

### 2.1. `castone/PuCo_RL` (코어 엔진 및 MLOps)
- **역할**: 게임의 본질적인 룰(`PuertoRicoGame`), 보드 컴포넌트(`components.py`), 그리고 강화학습 환경(`PuertoRicoEnv` - PettingZoo 래퍼)을 정의합니다.
- **관계**: 독립적인 Python 패키지로 동작하며, `puertorico`와 `castone`의 **백엔드 도커 컨테이너에서 각각 Read-Only(`:ro`) 볼륨으로 마운트**되어 코어 로직으로 임포트(`PYTHONPATH=/PuCo_RL`)됩니다.
- **포함 요소**: `PPO/HPPO` 강화학습 스크립트(`train_ppo_selfplay.py` 등), ML 모델 모음(`models/`), 봇 구조체(`agents/`).

### 2.2. `puertorico/` (단일 세션 로컬 아키텍처)
로컬에서의 봇 행동 분석 및 빠른 UI 테스트를 목적으로 구성되었습니다.

- **Frontend**: Vite + React (`port 5173`). 백엔드를 짧은 주기로 지속적 폴링(Polling)하여 UI를 갱신합니다.
- **Backend (`backend_py`)**: FastAPI (`port 3001`). `manager` 싱글톤 객체를 사용해 한 번에 단 하나의 게임 세션만 구동 가능합니다.
- **Database**: **없음 (No DB)**. 모든 게임 상태(`game_state.json`)와 로비 상태(`lobby_state.json`)는 파일 시스템(`state_dir`)에 직접 IO 기록됩니다.
- **Docker 연결**: `docker-compose.yml`을 통해 UI와 API를 올려두고, `../castone/PuCo_RL` 폴더를 주입받아 엔진을 돌립니다.

### 2.3. `castone/` (멀티플레이어 실시간 아키텍처)
분산된 유저들이 방(Room)에 모여 실시간으로 통신하며 플레이하기 위한 거대한 프로덕션용 인프라입니다.

- **Frontend**: Next.js (`port 3000`). 서버사이드 렌더링(SSR)과 함께 WebSocket 연결을 맺어 폴링 없이 즉각적으로 화면을 갱신합니다.
- **Backend`: FastAPI (`port 8000`). 여러 개의 `game_id`를 관리합니다.
- **Databases**:
  1. **PostgreSQL 16** (`port 5432`): 영구적인 데이터(유저 정보, 게임 전적, 랭킹 등)를 보관하는 RDBMS. (`puco_db`)
  2. **Redis 7** (`port 6379`): 세션 관리 및 Pub/Sub을 활용하여 방(Room)에 속한 여러 유저들의 웹소켓에 이벤트를 동시 브로드캐스팅하는 In-Memory Message Broker. (`puco_redis`)
- **Docker 연결**: DB 컨테이너(`db`, `redis`)의 상태(Healthcheck) 통과 후 백엔드(`puco_backend`)가 켜지고, 프론트(`puco_frontend`)가 구동되는 체인 구조입니다. 역시 `PuCo_RL` 폴더를 호스트에서 볼륨 마운트하여 사용합니다.

---

## 3. Senior Full-Stack 아키텍처 평가 및 인사이트

1. **의존성 주입의 분리 (Excellent)**:
   핵심 도메인 로직인 `PuCo_RL`을 두 백엔드 모두 호스트의 폴더를 읽기 전용 볼륨으로 마운트하여 공유하고 있는 점은 매우 훌륭합니다. 게임 규칙 코드 하나를 고치면 로컬 테스트(`puertorico`)와 멀티 서버(`castone`) 양쪽에 즉시 반영되는 마이크로서비스 지향적 모노레포 구조를 띄고 있습니다.

2. **상태 관리의 이원화 (Areas for Improvement)**:
   `puertorico` 백엔드는 JSON을, `castone` 백엔드는 Redis/Postgres를 사용하고 있습니다. 궁극적으로 `puertorico` 프로젝트를 발전시키기 보다, **현재 실험된 파이썬 상태 역직렬화 및 자동패스 검증 로직들을 `castone/backend`의 Room 관리자(WebSocket) 쪽으로 병합시키는 컨버전스 작업**이 필수적입니다.

3. **향후 ML 추론 파이프라인 (Future Architecture)**:
   현재 `puertorico/backend_py`의 `bot_runner.py`에서 봇이 직접 행동을 결정하는데, 이 추론 엔진을 `castone/backend`로 어떻게 우아하게 이식할지가 다음 아키텍처 스케일링 핵심입니다. **로컬 CPU 인퍼런스(ONNX)** 방식을 통해 Redis 훅에 결합한다면, 봇의 턴이 돌아오자마자 Redis Pub/Sub을 통해 유저들에게 WebSocket으로 즉시 행동 결과가 브로드캐스트 될 수 있습니다.

---

## 4. 확장성을 위한 인터페이스 설계 제언

자동화된 에이전트 교체 및 확장성을 최적화하기 위해, 백엔드와 AI 에이전트 간의 통신 규격을 다음과 같이 **통합 에이전트 인터페이스(Universal Agent Interface)**로 정의할 것을 강력히 권장합니다.

### 4.1. 인터페이스 정의 (To-Be)
기존의 단순 관측값 전달 방식을 넘어, 모든 에이전트 유형을 포괄할 수 있는 `game_context` 객체 기반의 인터페이스로 수정합니다.

- **수정 전**: `get_action(observation, action_mask)`
- **수정 후**: `get_action(game_context)`

### 4.2. `game_context` 데이터 구조
`game_context` 내부에는 각기 다른 요구사항을 가진 에이전트들이 필요한 데이터만 선택적으로 추출할 수 있도록 다음 정보들을 포함합니다.

| 필드명 | 용도 | 대상 에이전트 |
| :--- | :--- | :--- |
| `vector_obs` | 210차원 벡터 데이터 (신경망 입력용) | **PPO Agent** |
| `engine_instance` | `PuertoRicoGame` 엔진 객체 (시뮬레이션용) | **MCTS Agent** |
| `action_mask` | 200차원 합법 액션 이진 마스크 | 공통 |
| `phase_id` | 현재 게임 페이즈 ID (0~8) | **Hierarchical Agent** |

이와 같은 **Context-Injection** 패턴을 채택하면, 추후 새로운 종류의 에이전트(예: 휴리스틱 기반, 다른 형태의 RL)를 도입하더라도 백엔드의 로직 수정 없이 유연하게 에이전트를 교체 및 확장할 수 있는 아키텍처적 토대가 마련됩니다.
