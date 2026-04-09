# Castone

Castone은 Puerto Rico 보드게임을 웹에서 멀티플레이어와 AI 에이전트로 플레이하고, 운영 로그와 RL 재학습용 데이터까지 함께 남기는 프로젝트입니다.

핵심 구성은 아래 네 축입니다.

- `frontend/`: Vite + React SPA
- `backend/`: FastAPI 서버, 인증, 로비, 게임 진행, 저장
- `PuCo_RL/`: canonical Puerto Rico 엔진, 에이전트, 학습/평가 코드
- `vis/`: DB/JSONL/replay 로그를 Markdown 리포트로 바꾸는 도구

## 저장소 구조

```text
puco_test/
├── frontend/                  # React UI, Vite, nginx 배포 이미지
├── backend/                   # FastAPI, Alembic, 테스트, 운영 스크립트
├── PuCo_RL/                   # 게임 엔진, agent, 학습/평가, 오프라인 replay
├── data/                      # 런타임 로그 산출물
├── vis/                       # lineage / storage / behavior 리포트
├── imgs/                      # 보드게임 도메인 이미지 자산
├── models/                    # 로컬 학습 체크포인트 출력 자리
├── docker-compose.yml         # 개발용 compose
├── docker-compose.prod.yml    # 프로덕션용 compose
└── .env.example               # 환경 변수 예시
```

## 시작 전 준비

1. `.env.example`을 복사해 `.env`를 만듭니다.

```bash
cp .env.example .env
```

2. 아래 값은 실제 환경에 맞게 채웁니다.

- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `SECRET_KEY`
- `INTERNAL_API_KEY`
- `VITE_INTERNAL_API_KEY`
- `GOOGLE_CLIENT_ID`
- `VITE_GOOGLE_CLIENT_ID`

3. placeholder secret만 빠르게 치환하고 싶으면 아래 스크립트를 사용할 수 있습니다.

```bash
python3 backend/scripts/bootstrap_env_secrets.py --env-file .env
```

메모:

- `GOOGLE_CLIENT_ID`와 `VITE_GOOGLE_CLIENT_ID`는 같은 Google OAuth Client ID를 넣는 편이 가장 안전합니다.
- 기본 서빙 모델 파일은 `PuCo_RL/models/`에 이미 포함되어 있습니다.

## 실행 방법

### Dev

개발용 compose는 소스 마운트와 핫 리로드를 사용합니다. 백엔드는 시작할 때 자동으로 `alembic upgrade head`를 실행합니다.

```bash
docker compose up -d --build
docker compose ps
```

기본 접속 주소:

| 서비스 | 주소 |
| --- | --- |
| Frontend | `http://localhost:3000` |
| Backend | `http://localhost:8000` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

선택 사항:

- Adminer가 필요하면 `docker compose --profile adminer up -d adminer`
- 접속 주소는 `http://localhost:8080`

자주 쓰는 점검 명령:

```bash
curl http://localhost:8000/health
docker compose logs -f backend frontend
docker compose exec backend pytest
docker compose exec frontend npm run test
```

### Prod

프로덕션 compose는 프론트를 nginx 정적 서빙으로 빌드하고, 백엔드는 외부로 직접 노출하지 않습니다. 프론트 nginx가 `/api`를 백엔드로 프록시합니다.

```bash
docker compose down
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

기본 접속 주소:

| 서비스 | 주소 |
| --- | --- |
| Frontend | `http://localhost` |
| Backend | 외부 미노출 |

메모:

- `FRONTEND_PORT=3000`처럼 포트를 바꾸면 접속 주소도 그 포트로 바뀝니다.
- `VITE_GOOGLE_CLIENT_ID`, `VITE_INTERNAL_API_KEY`, `VITE_API_TARGET` 같은 프런트 빌드 시점 값이 바뀌면 반드시 `--build`로 다시 올려야 합니다.
- dev와 prod compose를 동시에 띄우지 말고 전환 전에 먼저 `down` 하세요.

프로덕션 상태 확인:

```bash
curl http://localhost/health
docker compose -f docker-compose.prod.yml logs -f frontend backend
```

## 테스트와 기본 점검

백엔드:

```bash
docker compose exec backend pytest
```

프런트엔드:

```bash
docker compose exec frontend npm run test
docker compose exec frontend npm run build
```

로컬에서 직접 프런트를 띄우고 싶다면:

```bash
cd frontend
npm ci
npm run dev
```

이 경우 기본 Vite 주소는 `http://localhost:5173`입니다. 백엔드 CORS 기본 허용 목록도 `3000`, `5173` 둘 다 포함합니다.

## 로그와 저장 위치

실행 중 생성되는 주요 데이터는 아래에 남습니다.

- PostgreSQL `games`, `game_logs`, `users`
- Redis `game:<game_id>:*`
- `data/logs/games/<game_id>.jsonl`
  - ML/lineage 분석용 raw transition 로그
- `data/logs/replay/<game_id>.json`
  - 사람이 읽기 쉬운 backend runtime replay
- `PuCo_RL/logs/replay/*.json`
  - 오프라인 평가 스크립트가 만든 replay

`vis/` 도구는 주로 `data/logs/`와 DB를 읽어서 Markdown 리포트를 만듭니다.

```bash
python vis/render_lineage_report.py \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --lang ko \
  --output vis/output/lineage.md
```

## 현재 문서 맵

- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)
- [PuCo_RL/README.md](PuCo_RL/README.md)
- [data/README.md](data/README.md)
- [vis/README.md](vis/README.md)
- [imgs/README.md](imgs/README.md)
- [models/README.md](models/README.md)

## 런타임 흐름

1. 프런트엔드가 로그인, 방 생성/입장, 액션 요청을 보냅니다.
2. `backend/app/api/` 라우터가 인증과 입력 검증을 처리합니다.
3. `backend/app/services/game_service.py`가 게임 시작, 액션 적용, DB 저장, Redis 동기화를 담당합니다.
4. 실제 규칙 처리와 action mask는 `PuCo_RL/env/`가 담당합니다.
5. 결과는 DB, Redis, `data/logs/`, `PuCo_RL/logs/`에 각각 목적에 맞게 기록됩니다.

## 개발 메모

- Swagger/OpenAPI는 `DEBUG=true`일 때만 `http://localhost:8000/docs`에 열립니다.
- Google 로그인에서 400이 나면 OAuth origin과 `VITE_GOOGLE_CLIENT_ID` 빌드값을 먼저 확인하세요.
- 루트 `models/`는 로컬 학습 산출물 자리이고, 실제 서버 기본 체크포인트는 `PuCo_RL/models/`를 봅니다.
