System Architecture: Puerto Rico AI Battle Platform

1. High-Level Architecture
   본 시스템은 Client-Server 모델을 따르며, 모든 게임 로직은 서버에서 집중 처리하는 Authoritative Server 구조를 채택한다.

1.1 Tech Stack
Frontend: Next.js (App Router), Tailwind CSS, Lucide React (Icons).

Backend: FastAPI (Python), SQLAlchemy (ORM).

Database: PostgreSQL (with JSONB & Partitioning).

Real-time: WebSocket (Broadcasting), Socket.io (Optional).

Infrastructure: Docker, AWS (EC2, RDS).

2. Component Breakdown
   2.1 Frontend (Next.js)
   View Layer: 게임판(Board), 자원 상황, 유저 인터페이스(UI) 렌더링.

State Management: 서버로부터 받은 WebSocket 데이터를 기반으로 로컬 상태 업데이트.

Auth: NextAuth.js를 이용한 Google OAuth 처리 및 JWT 토큰 관리.

2.2 Backend (FastAPI)
API Server: 유저 인증, 방 생성, 게임 액션 수신.

Game Engine Wrapper: 기존 Python 게임 엔진 라이브러리를 Import 하여 게임 상태 관리.

Agent Runner: 에이전트의 차례가 되면 백엔드 스케줄러가 에이전트 로직을 실행하고 결과를 엔진에 반영.

Logging Middleware: 모든 유효한 액션 발생 시 state_before, action, state_after를 추출하여 DB에 비동기로 저장.

2.3 Database (PostgreSQL)
Users Table: 유저 프로필 및 전적 데이터.

Games Table: 현재 활성화된 게임 세션 메타데이터.

Game Logs Table: 라운드별 파티셔닝된 RL 학습용 스냅샷 (JSONB).

3. Data Flow & Interaction
   3.1 Game Action Flow (유저 액션 발생 시)
   Client: /api/v1/game/action 엔드포인트로 JSON 데이터 전송.

Server: - JWT 검증 및 현재 턴 확인.

게임 엔진의 is_valid_action() 호출.

(Valid 시) 엔진의 apply_action() 호출.

[Logging] 액션 전후 상태와 선택지 리스트를 로그 테이블에 저장.

Broadcaster: WebSocket을 통해 방 안의 모든 클라이언트에게 최신 state 전송.

3.2 Agent Interaction Flow (에이전트 턴인 경우)
서버 엔진이 상태 변화 후 다음 턴이 '에이전트'임을 감지.

Agent Module: 현재 상태(State)와 액션 마스크(Mask)를 입력받아 최적의 액션 결정.

결정된 액션을 서버 내부에서 apply_action()에 투입 (유저 액션과 동일한 로깅 절차 수행).

4. Database Partitioning Strategy
   대상: game_logs 테이블.

방식: round 컬럼을 기준으로 Declarative Partitioning 적용.

이유: 강화학습 학습 시 특정 라운드 구간의 데이터만 빠르게 조회하기 위함이며, 대규모 로그 데이터의 인덱스 크기를 관리 가능한 수준으로 유지하기 위함.

5. Security & Reliability
   Single Source of Truth: 모든 게임 상태는 서버의 Python 엔진이 유일한 기준이며, 클라이언트 데이터는 참조하지 않는다.

Atomic Logging: 로그 저장 실패 시 게임 상태 진행을 롤백하거나 에러를 기록하여 데이터 오염을 방지한다.

CORS & Rate Limiting: 악의적인 API 호출 및 도스 공격 방지.
