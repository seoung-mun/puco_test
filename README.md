# Castone — Puerto Rico RL Web Platform

Puerto Rico 보드게임을 **웹 환경**에서 멀티플레이어 + **PPO 강화학습 AI**와 함께 플레이하고,
운영 로그와 RL 재학습용 데이터를 동시에 수집하는 플랫폼입니다.

---

## ✨ 주요 기능

- **실시간 멀티플레이어** — WebSocket 기반 최대 5인 대전
- **PPO AI 에이전트** — PBRS + Curriculum Learning으로 학습된 강화학습 봇
- **다양한 휴리스틱 봇** — Factory Rush, Shipping Rush, Trade Building, Action-Value 등
- **관전 & 리플레이** — 배속 조절, 일시정지, 종료 게임 리플레이 조회
- **ML 파이프라인** — 게임 transition 자동 기록, 오프라인 재학습 지원
- **다국어 UI** — 한국어(ko), 영어(en), 이탈리아어(it)

---

## 🛠️ 기술 스택

| 계층 | 기술 |
|------|------|
| **Frontend** | React 18 · TypeScript · Vite · i18next |
| **Backend** | FastAPI · SQLAlchemy · Alembic · WebSocket |
| **RL Engine** | PyTorch · Gymnasium · PPO · PBRS |
| **Database** | PostgreSQL · Redis |
| **Infra** | Docker Compose · Caddy (HTTPS) · Nginx |

---

## 📁 디렉토리 구조

```text
castone/
├── frontend/                  # React + Vite UI
│   ├── src/
│   │   ├── components/        # 게임 화면, 로비, 리플레이 등 UI 컴포넌트
│   │   ├── hooks/             # WebSocket, 리플레이, 인증 커스텀 훅
│   │   ├── locales/           # i18n 번역 파일 (ko, en, it)
│   │   └── types/             # TypeScript 타입 정의
│   └── public/
├── backend/                   # FastAPI 서버
│   ├── app/
│   │   ├── api/channel/       # Modern REST API + WebSocket 라우터
│   │   ├── api/legacy/        # 기존 호환 API
│   │   ├── db/                # SQLAlchemy 모델
│   │   ├── engine_wrapper/    # FastAPI ↔ PuCo_RL 엔진 브릿지
│   │   ├── services/          # 게임 진행, 로그, 봇 관리 등 비즈니스 로직
│   │   └── schemas/           # Pydantic 요청/응답 스키마
│   ├── alembic/               # DB 마이그레이션
│   ├── scripts/               # 운영/분석 스크립트
│   └── tests/                 # 백엔드 테스트
├── PuCo_RL/                   # Puerto Rico 게임 엔진 + RL
│   ├── env/                   # Gymnasium 환경 (엔진, 플레이어, 컴포넌트)
│   ├── agents/                # PPO, 휴리스틱 에이전트
│   ├── train/                 # PPO 학습 스크립트
│   ├── evaluate/              # 리그전, 벤치마크 평가
│   ├── common/                # 상태 어댑터 (observation encoding)
│   ├── models/                # 학습된 모델 체크포인트
│   └── web/                   # 경량 로컬 테스트 UI
├── data/
│   └── logs/                  # 게임 로그 (JSONL + replay JSON)
├── vis/                       # 로그 시각화 & 감사 리포트
├── design/                    # 설계 문서, 아키텍처 다이어그램
├── docker-compose.yml         # 개발 환경
├── docker-compose.prod.yml    # 프로덕션 환경
├── Caddyfile                  # HTTPS 리버스 프록시 설정
├── .env.example               # 환경 변수 템플릿
└── requirements.txt           # Python 의존성
```

---

## 🚀 시작하기

### 사전 준비

- Docker & Docker Compose
- Git

### 1. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 필요한 값을 설정하세요
```

### 2. 서비스 기동

```bash
docker compose up -d --build
docker compose ps
```

### 3. 접속 확인

| 서비스 | 주소 |
|--------|------|
| Frontend | `http://localhost:3000` |
| Backend API | `http://localhost:8000` |
| Swagger (DEBUG=true) | `http://localhost:8000/docs` |
| Adminer (DB 관리) | `http://localhost:8080` |

### 4. 헬스 체크

```bash
curl http://localhost:8000/health
```

---

## 📡 API 엔드포인트 요약

> Swagger UI는 `DEBUG=true`일 때 `http://localhost:8000/docs`에서 확인할 수 있습니다.

### 인증 (Auth)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/puco/auth/google` | Google 로그인 (JWT 발급) |
| `PATCH` | `/api/puco/auth/me/nickname` | 닉네임 변경 |
| `GET` | `/api/puco/auth/me` | 내 정보 조회 |

### 방 (Room)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/puco/rooms/` | 방 생성 |
| `GET` | `/api/puco/rooms/` | 대기 방 목록 |
| `POST` | `/api/puco/rooms/{room_id}/join` | 방 입장 |
| `POST` | `/api/puco/rooms/bot-game` | 봇전 즉시 시작 |

### 게임 (Game)

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/puco/game/{game_id}/start` | 게임 시작 |
| `POST` | `/api/puco/game/{game_id}/action` | 액션 수행 |
| `POST` | `/api/puco/game/{game_id}/add-bot` | 봇 추가 |
| `GET` | `/api/puco/game/{game_id}/final-score` | 최종 점수 |

### 관전 & 리플레이

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/api/puco/games/{game_id}/speed` | 배속 변경 (1×, 2×, 4×) |
| `POST` | `/api/puco/games/{game_id}/pause` | 일시정지/재개 |
| `GET` | `/api/puco/replays/` | 리플레이 목록 |
| `GET` | `/api/puco/replays/{game_id}` | 리플레이 상세 |

### WebSocket

| Path | 설명 |
|------|------|
| `/api/puco/ws/{game_id}` | 게임 실시간 스트림 |
| `/api/puco/ws/lobby/{room_id}` | 로비 실시간 스트림 |

---

## 🌿 브런치 전략

| 브런치 | 용도 |
|--------|------|
| `main` | 안정 버전, 코드 리뷰 완료된 변경사항 |
| `dev` | 개발 통합 브런치, 기능 개발 및 테스트 |
| `prod` | 프로덕션 배포 브런치, EC2 운영 환경 |

---

## 🧪 테스트

### Backend

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

### Frontend

```bash
cd frontend
npm install
npm test
```

### RL Engine

```bash
cd PuCo_RL
python -m pytest tests/
```

---

## 📊 데이터 & 로그

게임 데이터는 동시에 여러 저장소에 기록됩니다:

| 저장소 | 용도 |
|--------|------|
| **PostgreSQL** | 게임/유저/로그 정본 기록 |
| **Redis** | 실시간 상태 캐시 & pub/sub |
| `data/logs/games/*.jsonl` | ML 재학습용 raw transition |
| `data/logs/replay/*.json` | 사람이 읽는 리플레이 로그 |

---

## 📄 License

This project is for academic and research purposes.
