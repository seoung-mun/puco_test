# PRD: 푸에르토리코 AI 배틀 플랫폼 (Puerto Rico AI Battle Platform)

## 1. 프로젝트 개요

본 프로젝트는 보드게임 '푸에르토리코(Puerto Rico)'를 웹 환경에서 다수의 플레이어와 AI 에이전트가 함께 즐길 수 있는 플랫폼을 구축하는 것을 목표로 한다. 특히, 게임 중 발생하는 모든 데이터를 수집하여 강화학습(RL) 재학습을 위한 고품질 데이터셋을 구축하는 데 중점을 둔다.

## 2. 사용자 기능 요구사항 (User Features)

### 2.1 인증 및 유저 관리

- **구글 OAuth 2.0 로그인:** 구글 계정을 통한 간편 로그인 지원.
- **고유 ID 관리:** JWT(JSON Web Token)를 사용하여 유저 세션을 관리하고, DB 내 고유 식별자를 통해 전적 및 로그를 매칭함.
- **표준 보안:** 토큰 기반 인증을 통해 API 접근 권한을 제어함.

### 2.2 게임 방 생성 및 매칭 (Room & Matching)

- **사용자 생성 방(User-created Rooms):** 유저가 직접 방을 생성하고 설정을 제어함.
- **에이전트 설정:** 방 생성 시 포함할 에이전트의 수와 난이도를 선택 가능함.
- **매칭 시나리오:**
  - 타입 A: 사람(1) vs 사람(1) vs 에이전트(1)
  - 타입 B: 사람(1) vs 에이전트(1) vs 에이전트(1)
- **실시간 동기화:** 보드게임 아레나(BGA)와 유사하게 모든 플레이어의 상태가 실시간으로 동기화되어야 함.

## 2. 주요 구성 요소 및 특징

### 📦 Backend (FastAPI)
- **Engine Wrapper**: `PuCo_RL`의 `PuertoRicoEnv`를 래핑하여 강화학습에 필요한 `state_before`, `action`, `mask`, `state_after`를 자동으로 캡처하는 인터페이스 구현.
- **Data Models**: 유저 정보, 게임 세션, RL 로그 저장을 위한 SQLAlchemy 모델 정의.
- **Game & Room API**: 방 생성, 목록 조회, 게임 시작 및 액션 처리를 위한 REST API 엔드포인트 구현.
- **WebSocket & Redis**: Redis Pub/Sub을 활용하여 게임 상태 변화를 실시간으로 브로드캐스트하는 커스텀 `ConnectionManager` 구현.

### 🍱 Infrastructure (Docker Compose)
- **PostgreSQL 16**: 게임 상태 및 RL 로그 데이터베이스.
- **Redis 7**: 실시간 통신 및 세션 상태 관리.
- **Volume Mount**: 유연한 개발을 위해 `PuCo_RL` 폴더를 백엔드 컨테이너에 마운트하여 직접 참조.

### 🌐 Frontend (Next.js)
- **Premium Design**: 다크 모드, 그라데이션, 글래스모피즘이 적용된 현대적인 UI (`/`, `/lobby`, `/room/[id]`).
- **Real-time Sync**: `useGameWebSocket` 커스텀 훅을 통해 서버의 상태 변화를 실시간으로 UI에 반영.
- **Interaction**: Gymnasium Action Space(Discrete 200)에 대응하는 액션 전송 기능 구현.

## 3. RL 로깅 메커니즘 확인
모든 게임 액션 발생 시, 백엔드는 다음 데이터를 `game_logs` 테이블에 기록합니다:
- `state_before`: 액션 전 전체 보드 상태
- `available_options`: 당시 선택 가능했던 액션 마스크 (RL 학습 필수 데이터)
- `action_data`: 선택된 액션 인덱스
- `state_after`: 액션 적용 후 전체 보드 상태

---
모든 질문과 계획 사항은 한국어로 작성되었으며, 요청하신 대로 기존 `PuCo_RL` 폴더를 훼손하지 않고 외부 모듈로 참조하도록 설계하였습니다.

## 3. 기술적 요구사항 (Technical Requirements)

### 3.1 게임 엔진 및 AI 에이전트 통합

- **엔진 형태:** 기존 Python 라이브러리 형태의 게임 엔진을 백엔드(FastAPI 권장)에 이식함.
- **에이전트 인터페이스:** 백엔드 서버가 엔진 라이브러리를 호출하여 에이전트의 액션을 결정하고 게임 상태를 업데이트함.
- **통신 프로토콜:** 실시간 턴제 인터랙션을 위해 **WebSocket** 사용을 권장함.

### 3.2 데이터 로깅 및 강화학습 파이프라인

- **데이터 포맷:** 모든 로그는 JSON 형태로 생성 및 저장함.
- **수집 데이터 범위:**
  - **Full State Snapshot:** 매 턴(Turn) 및 페이즈(Phase) 전환 시점의 보드 전체 상태 스냅샷.
  - **Action Details:** 누가, 어떤 라운드에, 어떤 역할을 골랐는지, 그리고 세부 액션(일꾼 배치, 건물 구매 등)의 구체적 파라미터.
  - **Reward & Result:** 승점 변화 및 최종 승패 결과.
- **목적:** 수집된 데이터는 추후 강화학습 에이전트의 행동 복제(Behavior Cloning) 및 재학습 데이터로 활용됨.

### 3.3 인프라 및 배포

- **컨테이너화:** Docker를 사용하여 프론트엔드, 백엔드, DB 환경을 가상화함.
- **클라우드:** AWS(EC2, RDS, ElastiCache 등) 환경에 배포하며, 로컬 환경과 배포 환경의 일관성을 유지함.

## 4. 데이터 스키마 정의 (Data Schema Concept)

```json
{
  "game_id": "uuid",
  "round": 5,
  "phase": "MAYOR",
  "active_player": "user_id_or_agent_id",
  "action": {
    "type": "ROLE_SELECTION",
    "value": "BUILDER"
  },
  "state_snapshot": {
    "players": [...],
    "supply": {...},
    "board": {...}
  },
  "timestamp": "ISO-8601"
}
```

## 5. 제약 사항 및 보안 (Security & Constraints)

- **Server-side Logic:** 모든 게임 규칙 판정 및 상태 변화는 서버에서만 발생해야 하며, 클라이언트는 뷰어(Viewer) 역할만 수행함.
- **Data Integrity:** DB 트랜잭션을 통해 게임 상태와 로그 저장의 원자성(Atomicity)을 보장함.
- **JWT Security:** Access Token의 만료 시간을 설정하고 Refresh Token 전략을 검토함.

---

### 💡 AI 에이전트에게 전달할 다음 지침

이 PRD 문서를 작성한 후, AI에게 다음과 같이 첫 명령을 내리세요.

> "위의 `docs/PRD.md`를 읽고, **FastAPI(백엔드)와 Next.js(프론트엔드)**를 사용하여 프로젝트의 기본 구조를 잡아줘. 특히 **Python 라이브러리 형태의 게임 엔진**을 백엔드에서 import 해서 사용할 수 있도록 폴더 구조를 설계하고, **구글 로그인(JWT)** 기능의 뼈대부터 만들어줘."

이후 과정에서 **기술 설계서(ARCH.md)**와 **API 명세서(API.md)**를 순차적으로 구체화해 나가면 됩니다. PRD 내용 중 수정하거나 더 추가하고 싶은 세부 규칙이 있나요?
