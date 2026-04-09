# Backend

`backend/`는 Castone의 서버 런타임입니다. FastAPI 라우팅, 인증, 로비/게임 상태 관리, `PuCo_RL` 엔진 호출, DB/Redis/로그 저장을 하나의 서비스 경계로 묶습니다.

## 하위 문서

- [app/README.md](app/README.md)
- [alembic/README.md](alembic/README.md)
- [scripts/README.md](scripts/README.md)
- [tests/README.md](tests/README.md)

## 책임

- 채널 기반 REST/WebSocket API 제공
- `PuCo_RL` canonical engine 생성과 step 실행
- PostgreSQL `games`, `game_logs`, `users` 정본 저장
- Redis 상태 캐시와 WebSocket fan-out
- `data/logs/games/*.jsonl`, `data/logs/replay/*.json` 기록
- human/bot 공통 strategy-first Mayor contract 유지

## 실행과 점검

개발용 compose 기준:

```bash
docker compose up -d --build backend db redis
curl http://localhost:8000/health
docker compose exec backend pytest
```

로컬에서 직접 띄우는 경우:

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

메모:

- `entrypoint.sh`는 컨테이너 시작 시 자동으로 `alembic upgrade head`를 수행합니다.
- 직접 실행할 때도 PostgreSQL, Redis, `.env`가 먼저 준비되어 있어야 합니다.

## 런타임 흐름

1. [app/main.py](app/main.py)가 라우터와 미들웨어를 기동합니다.
2. [app/api/channel/README.md](app/api/channel/README.md)의 채널 라우터가 인증과 요청 검증을 처리합니다.
3. [app/services/game_service.py](app/services/game_service.py)가 엔진 step, DB 저장, Redis 동기화, bot 후속 turn 예약을 담당합니다.
4. [app/services/engine_gateway/README.md](app/services/engine_gateway/README.md)를 통해 `PuCo_RL` env/agent/constants에 접근합니다.
5. [app/services/ml_logger.py](app/services/ml_logger.py)와 [app/services/replay_logger.py](app/services/replay_logger.py)가 운영 로그를 파일로 남깁니다.

## 외부 의존성

- 상향 의존: [../frontend/README.md](../frontend/README.md)
- 엔진 의존: [../PuCo_RL/README.md](../PuCo_RL/README.md)
- 로그/리포트: [../data/README.md](../data/README.md), [../vis/README.md](../vis/README.md)
- 인프라: PostgreSQL, Redis, Docker Compose

## 변경 시 확인할 것

- 새 API를 추가할 때는 `channel`과 `legacy` 중 어느 계약에 속하는지 먼저 결정합니다.
- `PuCo_RL` import는 `engine_gateway`와 `engine_wrapper` 밖으로 새지 않게 유지합니다.
- 액션/상태 contract 변경 시 `frontend`, `backend/tests`, `contract.md`를 함께 갱신합니다.
- 로그 필드 추가 시 `vis/` 리포트와 replay parity에 미치는 영향을 같이 확인합니다.
