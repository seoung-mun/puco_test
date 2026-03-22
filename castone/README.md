# Puerto Rico AI Battle Platform

본 프로젝트는 보드게임 '푸에르토리코(Puerto Rico)'를 웹 환경에서 다수의 플레이어와 AI 에이전트가 함께 즐길 수 있는 플랫폼입니다.
특히 강화학습(RL) 재학습을 위한 고품질 데이터 세트 구축을 목표로 합니다.

## 프로젝트 구조

```text
castone/
├── backend/          # FastAPI (Python 3.12+)
├── frontend/         # Next.js (App Router, TypeScript)
├── PuCo_RL/          # Pure Python Game Engine (Gymnasium)
├── docs/             # PRD, ARCH, API 설계 문서
├── docker-compose.yml # 컨테이너 오케스트레이션
└── .env              # 환경 변수 설정
```

## 빠른 시작 (Docker Compose)

1. **환경 변수 설정**
   `.env` 파일을 생성하고 필요한 값을 설정합니다 (예: Google OAuth ID 등).

2. **Docker 컨테이너 구동**
   ```bash
   docker-compose up --build
   ```

3. **접속 정보**
   - Frontend: `http://localhost:3000`
   - Backend API: `http://localhost:8000`
   - API Docs (Swagger): `http://localhost:8000/docs`

## 주요 기능 및 특징

- ** Authoritative Game Server**: 모든 게임 로직은 서버(FastAPI)에서 관리하며 클라이언트는 뷰어 역할을 수행합니다.
- **RL Logging Wrapper**: `PuCo_RL` 엔진의 상태 변화를 래핑하여 `state_before`, `action`, `action_mask`, `state_after` 로그를 PostgreSQL(JSONB)에 자동 기록합니다.
- **Real-time Sync**: Redis와 WebSocket을 활용하여 플레이어 간의 게임 상태를 실시간으로 동기화합니다.
- **Agent Integration**: MCTS, PPO 등 다양한 AI 에이전트를 백엔드에서 직접 호출하여 게임에 참여시킬 수 있습니다.
