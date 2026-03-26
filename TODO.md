# Castone 배포 전 통합 기술 명세서 (TODO)

> **최종 갱신:** 2026-03-25 (Task 0.2 구현 완료 + legacy 패키지 분리)
> **대상 브랜치:** `dev`
> **배포 환경:** GCP Cloud Run
> **근거 문서:**
> - `castone/SECURITY_REPORT.md` — OWASP 보안 평가 (C1, H4, M6, L5)
> - `castone/MLOPS_REPORT.md` — MLOps 평가 (C2, H5, M5, L4)
> - `castone/ARCHITECTURE.md` — AS-IS/TO-BE 아키텍처 설계
> - `castone/docs/next_steps_report.md` — 종합 다음 단계 보고서

---


# 현재 발견된 문제


# 오늘 해결할 내용

- api를 legacy,v1 통합하여 1인,다인 플 전체 api 통합
- Task 0.3, Task 0.4 
- 시간되면 Task 1.1, Task 1.2 까지



  남은 항목 (운영자 직접 조치 필요):                                                                                                  
  - DEBUG=false 로 .env 변경 (현재 true)                                                             
  - POSTGRES_PASSWORD, REDIS_PASSWORD를 강력한 값으로 교체                                                                            
  - SECRET_KEY를 python3 -c "import secrets; print(secrets.token_hex(64))" 재생성  


## 현재 상태 요약

| 영역 | 완성도 | 비고 |
|------|--------|------|
| 게임 엔진 (PettingZoo AEC) | ✅ 완료 | terminated/truncated 분리, round/step 추적, Mayor 순차배치 |
| DB 스키마 + Alembic 003 | ✅ 완료 | state_summary JSONB 추가 |
| Redis Pub/Sub + WebSocket | ✅ 완료 | 멀티인스턴스 대응 |
| Google OAuth + JWT 인증 | ✅ 완료 | SECRET_KEY 필수화 |
| RL 데이터 로깅 | ✅ 완료 | PostgreSQL + JSONL 이중 저장 |
| AgentRegistry (PPO/HPPO/Random) | ✅ 완료 | dev 브랜치에서 구현 |
| PuCo_RL upstream sync | ✅ 완료 | Mayor 순차배치 액션, league 학습 스크립트 반영 |
| 보안 (인증/인가) | ✅ Phase 0 완료 | Legacy 키 인증, IDOR 방지, WS 첫메시지 인증 |
| .env 보안 | ✅ 완료 | .gitignore + .env.example 생성 |
| Rate Limiting | ❌ 없음 | 전 엔드포인트 무제한 |
| Docker 최적화 | ⚠️ 미흡 | 단일 스테이지, HEALTHCHECK 없음 |
| MLOps 파이프라인 | ❌ 없음 | 수동 배포, 학습-서빙 환경 불일치 |
| GCP 배포 | ❌ 없음 | Docker Compose만 존재 |
| CI/CD | ❌ 없음 | GitHub Actions 없음 |

---

## Phase 0 — 긴급 보안 패치 ✅ 완료

### Task 0.1 `[SEC C-01]` .env Git 추적 제거 + SECRET_KEY 즉시 교체

**설명:** `.env` 파일에 실제 `SECRET_KEY`와 `GOOGLE_CLIENT_ID`가 Git에 커밋되어 노출 중. 이 키로 JWT 위조 가능.

**대상 파일:**
- `castone/.gitignore` (수정)
- `castone/.env` (재생성)
- `castone/.env.example` (신규)

**구체적 변경 사항:**

```bash
# 1. .gitignore에 추가
echo ".env" >> castone/.gitignore
echo ".env.*" >> castone/.gitignore
echo "!.env.example" >> castone/.gitignore

# 2. Git 히스토리에서 제거
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch castone/.env' \
  --prune-empty --tag-name-filter cat -- --all

# 3. SECRET_KEY 재생성
python -c "import secrets; print(secrets.token_hex(64))"
```

```env
# castone/.env.example
SECRET_KEY=여기에_python_secrets_token_hex_64_결과
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/puco_rl
REDIS_URL=redis://redis:6379/0
GOOGLE_CLIENT_ID=Google_Cloud_Console에서_발급
DEBUG=false
PPO_MODEL_FILENAME=ppo_agent_update_100.pth
POSTGRES_USER=puco_user
POSTGRES_PASSWORD=여기에_강력한_비밀번호
```

**완료 기준:**
- [x] `castone/.gitignore` 생성 (.env, *.pyc, *.pth 등 제외)
- [x] `castone/.env.example` 생성 (실제 값 없는 템플릿)
- [ ] SECRET_KEY 실제 값으로 교체 (운영자가 직접 `.env` 생성 필요)

---

### Task 0.2 `[SEC H-01, H-02]` Legacy API + 게임/방 엔드포인트 인증 추가 ✅

**설명:** Legacy API 전체와 `POST /{game_id}/start`, `POST /rooms/`에 인증이 없어 익명 공격자가 게임 초기화, 방 무한 생성 가능.

**구현 완료 내용:**
- `backend/app/api/legacy/deps.py` — `INTERNAL_API_KEY` + `require_internal_key` (hmac.compare_digest 타이밍 공격 방지)
- `backend/app/api/v1/game.py` — `start_game`에 `Depends(get_current_user)` 추가
- `backend/app/api/v1/room.py` — `create_room`에 `Depends(get_current_user)` 추가
- `castone/.env.example` — `INTERNAL_API_KEY` 항목 추가

**추가 작업 — legacy.py 패키지 분리:**
단일 파일(581줄)을 기능별 패키지로 분리:
- `backend/app/api/legacy/__init__.py` — 라우터 통합 (main.py 변경 불필요)
- `backend/app/api/legacy/deps.py` — 인증 + 공통 헬퍼
- `backend/app/api/legacy/schemas.py` — Pydantic 모델
- `backend/app/api/legacy/game.py` — 상태 조회 + 단일 플레이어 설정
- `backend/app/api/lobby.py` — 멀티플레이어 로비
- `backend/app/api/actions.py` — 게임 액션 (prefix `/action`)

**완료 기준:**
- [x] Legacy API: `INTERNAL_API_KEY` 설정 시 헤더 없으면 403
- [x] `POST /{game_id}/start`: `Depends(get_current_user)` 추가
- [x] `POST /rooms/`: `Depends(get_current_user)` 추가
- [x] `legacy.py` → `legacy/` 패키지 분리 (main.py import 호환 유지)

---

### Task 0.3 `[SEC H-03]` 게임 액션 IDOR 방지 — 인가 검증

**설명:** 인증된 아무 유저가 `game_id`만 알면 남의 게임에 액션 실행 가능. OWASP A01 - Broken Access Control.

**대상 파일:**
- `backend/app/api/v1/game.py` (수정)

**구체적 변경 사항:**

```python
@router.post("/{game_id}/action")
async def perform_action(
    game_id: UUID,
    action_data: GameAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 인가 검증 추가
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Game not found")
    if str(current_user.id) not in (room.players or []):
        raise HTTPException(status_code=403, detail="You are not a player in this game")

    actor_id = str(current_user.id)
    ...
```

**완료 기준:**
- [x] 해당 게임 플레이어가 아닌 유저가 액션 호출 시 403
- [x] 존재하지 않는 game_id 시 404
- [x] `start_game`에도 동일한 IDOR 검증 적용

---

### Task 0.4 `[SEC H-04]` WebSocket JWT URL 쿼리 → 첫 메시지 인증

**설명:** JWT가 `ws://server/ws/123?token=eyJ...` 형태로 URL에 노출됨. 서버 로그, 브라우저 히스토리, 프록시에 토큰 기록됨.

**대상 파일:**
- `backend/app/api/v1/ws.py` (수정)
- `frontend/src/` WebSocket 연결 코드 (수정)

**구체적 변경 사항:**

```python
# ws.py — 기존
@router.websocket("/{game_id}")
async def websocket_endpoint(
    websocket: WebSocket, game_id: str,
    token: str = Query(None),  # ← 제거
):

# ws.py — 변경 후
@router.websocket("/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    await websocket.accept()
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        token = auth_msg.get("token")
        if not token:
            await websocket.close(code=1008, reason="Token required")
            return
        # JWT 검증
        user = verify_token(token)
    except asyncio.TimeoutError:
        await websocket.close(code=1008, reason="Auth timeout")
        return
    except Exception:
        await websocket.close(code=1008, reason="Invalid token")
        return
    # 이후 기존 로직...
```

```typescript
// Frontend WebSocket 연결 변경
const ws = new WebSocket(`ws://${host}/api/v1/ws/game/${gameId}`);
ws.onopen = () => {
  ws.send(JSON.stringify({ token: accessToken }));  // 첫 메시지로 인증
};
```

**완료 기준:**
- [x] `?token=xxx` 쿼리 파라미터 방식 제거
- [x] 첫 메시지 `{"token": "..."}` 또는 `{"accessToken": "..."}` 인증
- [x] 5초 타임아웃, 실패 시 close(code=1008)
- [x] 인증 성공 시 `{"type": "auth_ok", "player_id": "..."}` 응답
- [ ] 프론트엔드 WebSocket 연결 코드 첫 메시지 방식으로 수정 필요

---

## Phase 1 — 인프라 보안 + Docker 최적화 (1주)

### Task 1.1 `[SEC M-01]` 헬스 엔드포인트 에러 상세 제거

**대상 파일:** `backend/app/main.py`

**구체적 변경 사항:**

```python
# 기존
except Exception as e:
    checks["postgresql"] = f"error: {e}"  # DB 연결 문자열 노출

# 변경
except Exception as e:
    checks["postgresql"] = "error"
    logger.error("PostgreSQL health check failed: %s", e)
```

**완료 기준:**
- [ ] `/health` 에러 시 응답에 연결 문자열/스택 트레이스 없음

---

### Task 1.2 `[SEC M-02, M-03, L-05]` Docker 포트 localhost 바인딩 + 자격증명 분리

**대상 파일:** `castone/docker-compose.yml`

**구체적 변경 사항:**

```yaml
services:
  db:
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: puco_rl
    ports:
      - "127.0.0.1:5432:5432"  # localhost만

  redis:
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports:
      - "127.0.0.1:6379:6379"  # localhost만

  adminer:
    ports:
      - "127.0.0.1:8080:8080"  # localhost만

  backend:
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/puco_rl
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
```

**완료 기준:**
- [ ] `docker-compose.yml`에 평문 `puco_password` 없음
- [ ] 모든 포트가 `127.0.0.1` 바인딩
- [ ] Redis에 비밀번호 설정됨

---

### Task 1.3 `[SEC M-04]` slowapi Rate Limiting 적용

**대상 파일:**
- `backend/requirements.txt` (수정: `slowapi` 추가)
- `backend/app/main.py` (수정)
- `backend/app/api/v1/auth.py` (수정)
- `backend/app/api/v1/game.py` (수정)

**구체적 변경 사항:**

```python
# main.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, storage_uri=os.getenv("REDIS_URL"))
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

| 엔드포인트 | 제한 |
|-----------|------|
| `POST /auth/google` | 10/min per IP |
| `PATCH /auth/me/nickname` | 5/min per user |
| `POST /game/action` | 60/min per user |
| `GET /health` | 30/min per IP |

**완료 기준:**
- [ ] 11번째 `/auth/google` 요청이 429 반환

---

### Task 1.4 `[SEC M-05]` 프로덕션 DEBUG=false 기본값

**대상 파일:** `castone/.env.example`

**구체적 변경 사항:** `.env.example`에 `DEBUG=false` 명시 (Task 0.1에서 생성한 파일에 포함)

**완료 기준:**
- [ ] `.env.example`에 `DEBUG=false` 존재

---

### Task 1.5 `[SEC M-06]` 게임 액션 payload 크기 제한

**대상 파일:** `backend/app/schemas/game.py`

**구체적 변경 사항:**

```python
from pydantic import BaseModel, Field, field_validator

class GameAction(BaseModel):
    game_id: UUID
    action_type: str = Field(max_length=50)
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, v):
        if len(str(v)) > 1024:
            raise ValueError("Payload too large (max 1KB)")
        return v
```

**완료 기준:**
- [ ] 2KB payload 전송 시 422 반환

---

### Task 1.6 `[SEC L-01]` HTTP 보안 헤더 미들웨어

**대상 파일:** `backend/app/main.py`

**구체적 변경 사항:**

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)
```

**완료 기준:**
- [ ] 모든 응답에 3개 보안 헤더 포함

---

### Task 1.7 `[SEC L-03]` ValueError 내부 메시지 클라이언트 노출 차단

**대상 파일:** `backend/app/api/v1/game.py`

**구체적 변경 사항:**

```python
# 기존
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))

# 변경
except ValueError as e:
    logger.warning("Game action failed: %s", e)
    raise HTTPException(status_code=400, detail="Invalid action")
```

**완료 기준:**
- [ ] 잘못된 액션 시 응답에 엔진 내부 메시지 없음 (`"Invalid action"`만 반환)

---

### Task 1.8 `[SEC L-04]` MLLogger 로그 로테이션

**대상 파일:** `backend/app/services/ml_logger.py`

**구체적 변경 사항:**

```python
import os

MAX_LOG_SIZE_BYTES = 100 * 1024 * 1024  # 100MB

async def _write_to_file(record: dict):
    log_file = _get_log_path()
    # 파일 크기 확인 후 로테이션
    if os.path.exists(log_file) and os.path.getsize(log_file) > MAX_LOG_SIZE_BYTES:
        rotated = log_file + f".{int(time.time())}"
        os.rename(log_file, rotated)
        # 최대 5개 보관 — 가장 오래된 것 삭제
        _cleanup_old_logs(log_dir, max_keep=5)
    async with aiofiles.open(log_file, mode='a') as f:
        await f.write(json.dumps(record) + "\n")
```

**완료 기준:**
- [ ] 로그 파일 100MB 초과 시 자동 로테이션
- [ ] 최대 5개 파일 보관

---

### Task 1.9 Dockerfile 멀티스테이지 빌드 + HEALTHCHECK

**대상 파일:** `backend/Dockerfile`

**구체적 변경 사항:**

```dockerfile
# ── Stage 1: 의존성 설치 ──
FROM python:3.12-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# ── Stage 2: 프로덕션 이미지 ──
FROM python:3.12-slim AS production
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN useradd --uid 1001 --no-create-home --shell /bin/false appuser
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser alembic/ ./alembic/
COPY --chown=appuser:appuser alembic.ini .
COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
USER 1001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["/entrypoint.sh"]
```

**완료 기준:**
- [ ] `docker images` 기준 이미지 크기 500MB 이하
- [ ] `docker inspect`에 healthcheck 설정 존재
- [ ] 컨테이너가 UID 1001로 실행

---

### Task 1.10 entrypoint.sh 프로덕션/개발 분기

**대상 파일:** `backend/entrypoint.sh`

**구체적 변경 사항:**

```bash
#!/bin/bash
set -e

echo "=== DB Migration ==="
alembic upgrade head

echo "=== Starting server ==="
if [ "${DEBUG}" = "true" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
        --workers 2 \
        --log-level info
fi
```

**완료 기준:**
- [ ] `DEBUG=false` 시 `--reload` 플래그 없음, `--workers 2` 사용

---

### Task 1.11 requirements 파일 분리 (서빙/학습)

**대상 파일:**
- `backend/requirements.api.txt` (신규)
- `backend/requirements.train.txt` (신규)

**구체적 변경 사항:**

`requirements.api.txt` — torch 제외:
```
fastapi>=0.110
uvicorn[standard]
sqlalchemy>=2.0
psycopg2-binary
alembic
redis
aiofiles
python-jose[cryptography]
google-auth
httpx
pydantic>=2.0
slowapi
```

`requirements.train.txt` — 학습용 전체:
```
-r requirements.api.txt
torch
torchvision
gymnasium
pettingzoo
tensorboard
```

**완료 기준:**
- [ ] `pip install -r requirements.api.txt` 성공, torch 미포함
- [ ] 서빙 이미지 크기 ~400MB (torch 5.5GB 제거)

---

## Phase 1.5 — 데이터 무결성 + MLOps 긴급 (1주)

### Task 1.12 `[ML C-01]` 학습 환경 max_game_steps 통일 → 재학습

**설명:** PPO 모델이 `max_game_steps=2000`에서 학습됐으나 실제 게임은 ~11,000스텝. 서빙 환경은 dev에서 50000으로 수정 완료.

> **⚠️ PuCo_RL upstream 구조 변경 (2026-03-25 반영)**
> upstream/main merge로 `train_ppo_selfplay.py` → `train_ppo_selfplay_server.py`로 교체됨.
> 새 학습 스크립트 목록: `train_ppo_selfplay_server.py`, `train_hppo_league_server.py`, `train_hppo_selfplay_server.py`, `train_phase_ppo_selfplay_server.py`, `train_phase_ppo_league_server.py`
> Mayor 액션 공간 변경: 69-92 (toggle) → 69-72 (순차 배치), `mayor_slot_idx` observation 추가

**대상 파일:** `PuCo_RL/train_ppo_selfplay_server.py` (기존 `train_ppo_selfplay.py` 대체됨)

**구체적 변경 사항:**

```python
# train_ppo_selfplay_server.py 내 make_env() 확인 후
MAX_GAME_STEPS = int(os.environ.get("MAX_GAME_STEPS", "50000"))

def make_env():
    return PuertoRicoEnv(num_players=NUM_PLAYERS, max_game_steps=MAX_GAME_STEPS)
```

**완료 기준:**
- [x] PuCo_RL upstream/main 로컬 merge 완료
- [ ] `train_ppo_selfplay_server.py`의 `max_game_steps` 확인 및 50000 설정
- [ ] 변경된 Mayor 액션 공간(69-72)에서 새 모델 재학습 완료

---

### Task 1.13 `[ML C-02]` MLLogger 로그 → 학습 파이프라인 연결 또는 JSONL 제거

**설명:** MLLogger가 raw dict를 JSONL에 저장하지만 학습 스크립트는 flatten된 벡터가 필요. 데이터 수집은 되지만 실제 재학습에 사용 불가한 Dead Code 파이프라인.

**대상 파일:** `backend/app/services/ml_logger.py`

**권장 옵션:** PostgreSQL `game_logs`를 단일 진실의 원천으로 통합, 오프라인 export 스크립트 작성

```python
# scripts/export_training_data.py (신규)
"""game_logs → 학습용 numpy 배열 변환 스크립트"""
from utils.env_wrappers import flatten_dict_observation

def export_from_db(game_ids: list[str], output_path: str):
    for log in query_game_logs(game_ids):
        flat_obs = flatten_dict_observation(log.state_before, obs_space)
        # → numpy 배열로 저장
```

**완료 기준:**
- [ ] export 스크립트 존재 및 실행 가능
- [ ] 또는 JSONL에 `flat_obs_before` 필드 추가

---

### Task 1.14 `[ML H-03]` BotService obs_space 캐싱

**설명:** 봇 추론마다 `PuertoRicoEnv()` 인스턴스를 생성함. 3인 봇 게임에서 ~7,300번 불필요한 환경 초기화.

**대상 파일:** `backend/app/services/bot_service.py:103-105`

**구체적 변경 사항:**

```python
class BotService:
    _cached_obs_space = None

    @classmethod
    def _get_obs_space(cls):
        if cls._cached_obs_space is None:
            dummy = PuertoRicoEnv(num_players=3)
            dummy.reset()
            cls._cached_obs_space = dummy.observation_space("player_0")["observation"]
        return cls._cached_obs_space

    @staticmethod
    def get_action(bot_type: str, game_context: Dict[str, Any]) -> int:
        obs_space = BotService._get_obs_space()  # 캐시된 값 사용
        flat_obs = flatten_dict_observation(raw_obs, obs_space)
        ...
```

**완료 기준:**
- [ ] `PuertoRicoEnv()` 생성이 서버 라이프사이클에서 1회만 발생

---

### Task 1.15 `[ML M-04]` strict=False 가중치 로딩 경고 강화

**대상 파일:** `PuCo_RL/agents/wrappers.py:36`

**구체적 변경 사항:**

```python
# 기존
agent.load_state_dict(state, strict=False)
logger.info("가중치 로드 완료 (strict=False): %s", model_path)

# 변경
missing, unexpected = agent.load_state_dict(state, strict=False)
if missing:
    logger.warning("로드 누락 레이어 (%d개): %s", len(missing), missing[:5])
if unexpected:
    logger.warning("예상 외 레이어 (%d개): %s", len(unexpected), unexpected[:5])
if not missing and not unexpected:
    logger.info("가중치 완전 로드: %s", model_path)
```

**완료 기준:**
- [ ] 레이어 불일치 시 warning 로그에 누락/예상외 레이어 목록 출력

---

### Task 1.16 `[ML M-05]` ml_logger.py 입력 검증 추가

**대상 파일:** `backend/app/services/ml_logger.py`

**구체적 변경 사항:**

```python
import uuid as _uuid

_REQUIRED_STATE_KEYS = {"phase", "role", "players", "goods_supply", "action_mask"}

def _validate_transition(game_id, state_before, action, action_mask, state_after) -> bool:
    """PPO 학습에 필요한 데이터 무결성 검증. 실패 시 False 반환."""
    try:
        _uuid.UUID(str(game_id))
    except ValueError:
        logger.warning("ml_logger: 유효하지 않은 game_id: %r", game_id)
        return False

    if not action_mask or not all(v in (0, 1) for v in action_mask):
        logger.warning("ml_logger: 유효하지 않은 action_mask")
        return False

    if not (0 <= action < len(action_mask)):
        logger.warning("ml_logger: action=%d이 mask 범위 초과", action)
        return False

    for key in _REQUIRED_STATE_KEYS:
        if key not in (state_before or {}):
            logger.warning("ml_logger: state_before 필수 키 누락: %s", key)
            return False

    return True

async def log_transition(self, game_id, state_before, action, action_mask, state_after, **kwargs):
    if not _validate_transition(game_id, state_before, action, action_mask, state_after):
        return  # 게임 흐름 차단하지 않음
    # 기존 저장 로직...
```

**완료 기준:**
- [ ] 잘못된 데이터 입력 시 warning 로그 + DB/JSONL 미저장
- [ ] 정상 데이터는 기존대로 저장

---

### Task 1.17 감사 로그 테이블 + Alembic migration 004

**대상 파일:**
- `backend/app/db/models.py` (수정)
- `backend/alembic/versions/004_add_auth_audit_log.py` (신규)

**구체적 변경 사항:**

```python
# models.py
class AuthAuditLog(Base):
    __tablename__ = "auth_audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    event_type = Column(String)  # "login", "nickname_set", "token_refresh", "logout", "account_delete"
    ip_address = Column(String)
    user_agent = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

**완료 기준:**
- [ ] `alembic upgrade head` 성공
- [ ] `auth_audit_logs` 테이블 존재
- [ ] 로그인 시 감사 로그 행 생성

---

## Phase 2 — 인증 고도화 + MLOps 기반 (2주)

### Task 2.1 `[SEC L-02]` JWT 토큰 무효화 (Redis Blocklist)

**대상 파일:**
- `backend/app/core/security.py` (수정)
- `backend/app/dependencies.py` (수정)

**구체적 변경 사항:**

```python
# security.py — JWT에 jti 추가
from uuid import uuid4

def create_access_token(subject: str, ...):
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "jti": str(uuid4()),  # 추가
    }
    ...

async def revoke_token(jti: str, expires_in: int):
    """토큰 JTI를 Redis blocklist에 추가."""
    await async_redis_client.setex(f"blocklist:{jti}", expires_in, "1")

async def is_token_revoked(jti: str) -> bool:
    return await async_redis_client.exists(f"blocklist:{jti}") > 0
```

```python
# dependencies.py — blocklist 확인 추가
async def get_current_user(...):
    payload = decode_access_token(token)
    jti = payload.get("jti")
    if jti and await is_token_revoked(jti):
        raise HTTPException(status_code=401, detail="Token revoked")
    ...
```

**완료 기준:**
- [ ] 무효화된 토큰으로 요청 시 401
- [ ] Redis에 `blocklist:{jti}` 키 존재 (TTL 확인)

---

### Task 2.2 로그아웃 + 회원탈퇴 엔드포인트

**대상 파일:** `backend/app/api/v1/auth.py`

**구체적 변경 사항:**

```python
@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), ...):
    payload = decode_access_token(token)
    remaining = payload["exp"] - int(time.time())
    await revoke_token(payload["jti"], remaining)
    # 감사 로그 기록
    return {"message": "로그아웃 완료"}

@router.delete("/me")
async def delete_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.google_id = f"deleted_{current_user.id}"
    current_user.email = None
    current_user.nickname = None
    db.commit()
    # 토큰 무효화 + 감사 로그
    return {"message": "계정 삭제 완료"}
```

**완료 기준:**
- [ ] 로그아웃 후 토큰 무효
- [ ] 탈퇴 후 `users` 테이블에 PII null, 행 보존

---

### Task 2.3 `[ML H-01]` 모델 저장 시 메타데이터 포함

**대상 파일:** `PuCo_RL/train_ppo_selfplay.py`

**구체적 변경 사항:**

```python
torch.save({
    "model_state_dict": agent.state_dict(),
    "metadata": {
        "version": run_name,
        "timestamp": int(time.time()),
        "total_steps": global_step,
        "win_rate": float(win_rate),
        "avg_score": stats.get("avg_score", 0),
        "hyperparams": {
            "lr": LEARNING_RATE,
            "gamma": GAMMA,
            "max_game_steps": MAX_GAME_STEPS,
        }
    }
}, model_path)
```

**완료 기준:**
- [ ] `.pth` 파일에 `metadata` 딕셔너리 포함
- [ ] `torch.load(path)["metadata"]["win_rate"]` 접근 가능

---

### Task 2.4 `[ML H-02]` AgentRegistry 모델 핫스왑 (LRU → 파일 해시)

**대상 파일:** `backend/app/services/agent_registry.py`

**구체적 변경 사항:**

```python
import hashlib

class AgentRegistry:
    _instances: Dict[str, AgentWrapper] = {}
    _model_hashes: Dict[str, str] = {}

    @classmethod
    def get_wrapper(cls, bot_type: str, obs_dim: int) -> AgentWrapper:
        cfg = AGENT_REGISTRY.get(bot_type, AGENT_REGISTRY["random"])
        model_path = _resolve_model_path(cfg)

        current_hash = _file_hash(model_path) if model_path else None
        cache_key = f"{bot_type}:{obs_dim}"

        if cache_key not in cls._instances or cls._model_hashes.get(cache_key) != current_hash:
            logger.info("모델 (재)로드: %s, hash=%s", bot_type, current_hash)
            cls._instances[cache_key] = cfg["wrapper_cls"](model_path=model_path, obs_dim=obs_dim)
            cls._model_hashes[cache_key] = current_hash

        return cls._instances[cache_key]

def _file_hash(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
```

**완료 기준:**
- [ ] 모델 `.pth` 파일 교체 후 서버 재시작 없이 새 모델 적용
- [ ] `lru_cache` 데코레이터 제거

---

### Task 2.5 `[ML H-04]` 실험 추적 W&B 또는 MLflow 통합

**대상 파일:**
- `PuCo_RL/train_ppo_selfplay.py` (수정)
- `castone/docker-compose.yml` (수정 — MLflow 서비스 추가, 선택)

**구체적 변경 사항:**

```python
# train_ppo_selfplay.py
try:
    import wandb
    wandb.init(project="puco-rl", name=run_name, config={
        "lr": LEARNING_RATE, "gamma": GAMMA, "max_game_steps": MAX_GAME_STEPS,
    })
    USE_WANDB = True
except ImportError:
    USE_WANDB = False

# 학습 루프 내
if USE_WANDB:
    wandb.log({"episode_reward": reward, "win_rate": win_rate}, step=global_step)
```

```yaml
# docker-compose.yml (선택: MLflow 로컬 서버)
mlflow:
  image: ghcr.io/mlflow/mlflow:v2.13.0
  ports:
    - "127.0.0.1:5000:5000"
  volumes:
    - ./mlruns:/mlruns
  command: mlflow server --host 0.0.0.0
```

**완료 기준:**
- [ ] 학습 실행 후 실험 UI(W&B 또는 MLflow)에서 params/metrics 확인 가능

---

### Task 2.6 `[ML M-02]` 학습 하이퍼파라미터 설정 파일 분리

**대상 파일:** `PuCo_RL/configs/ppo_config.yaml` (신규)

**구체적 변경 사항:**

```yaml
# configs/ppo_config.yaml
learning_rate: 2.5e-4
num_steps: 4096
gamma: 0.99
gae_lambda: 0.95
ent_coef: 0.01
clip_coef: 0.2
max_game_steps: 50000
num_players: 3
total_timesteps: 50000000
```

```python
# train_ppo_selfplay.py
import yaml
with open("configs/ppo_config.yaml") as f:
    config = yaml.safe_load(f)
LEARNING_RATE = config["learning_rate"]
# ...
```

**완료 기준:**
- [ ] 학습 스크립트에 하드코딩된 상수 제거
- [ ] config 파일 변경으로 하이퍼파라미터 조정 가능

---

### Task 2.7 `[ML M-03]` Self-play Opponent Pool 영속성

**대상 파일:** `PuCo_RL/train_ppo_selfplay.py:268`

**구체적 변경 사항:**

```python
# Checkpoint 저장 시 opponent pool 포함
torch.save({
    "model_state_dict": agent.state_dict(),
    "optimizer_state_dict": optimizer.state_dict(),
    "opponent_pool": [opp.state_dict() for opp in opponent_pool[-5:]],
    "global_step": global_step,
    "metadata": {...},
}, checkpoint_path)

# 로드 시 복원
if "opponent_pool" in checkpoint:
    for opp_state in checkpoint["opponent_pool"]:
        opp = Agent(obs_dim=obs_dim, action_dim=200)
        opp.load_state_dict(opp_state)
        opponent_pool.append(opp)
```

**완료 기준:**
- [ ] 학습 재시작 시 opponent pool 복원
- [ ] Checkpoint 파일에 `opponent_pool` 키 존재

---

## Phase 3 — GCP 클라우드 배포 (1개월)

### Task 3.1 docker-compose 프로덕션/개발 분리

**대상 파일:**
- `castone/docker-compose.override.yml` (신규 — 개발용)
- `castone/docker-compose.prod.yml` (신규 — 프로덕션)

**구체적 변경 사항:**

```yaml
# docker-compose.override.yml (개발용)
services:
  backend:
    volumes:
      - ./backend:/app
    environment:
      - DEBUG=true
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# docker-compose.prod.yml (프로덕션)
services:
  backend:
    build:
      target: production
    environment:
      - DEBUG=false
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
```

**완료 기준:**
- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`에 `--reload` 없음

---

### Task 3.2 Terraform IaC 기초 인프라 (GCP)

**대상 파일:** `infrastructure/` 디렉토리 (신규)

**구체적 변경 사항:**

```
infrastructure/
├── main.tf             # provider, backend 설정
├── variables.tf        # 변수 정의
├── outputs.tf          # 출력 값
├── modules/
│   ├── vpc/            # VPC + 서브넷
│   ├── cloud-sql/      # PostgreSQL 16
│   ├── memorystore/    # Redis 7
│   └── artifact-registry/  # Docker 이미지 저장소
```

리전: `asia-northeast3` (서울)

**완료 기준:**
- [ ] `terraform plan` 성공
- [ ] VPC, Cloud SQL, Memorystore, Artifact Registry 프로비저닝

---

### Task 3.3 GitHub Actions CI/CD

**대상 파일:** `.github/workflows/deploy.yml` (신규)

**구체적 변경 사항:**

```yaml
name: Deploy to GCP
on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r castone/backend/requirements.api.txt
      - run: pytest castone/backend/tests/

  build-push:
    needs: test
    steps:
      - uses: google-github-actions/auth@v2
      - uses: google-github-actions/setup-gcloud@v2
      - run: |
          gcloud auth configure-docker asia-northeast3-docker.pkg.dev
          docker build -t $REGISTRY/puco-backend:$GITHUB_SHA \
            --target production castone/backend/
          docker push $REGISTRY/puco-backend:$GITHUB_SHA

  deploy:
    needs: build-push
    steps:
      - run: |
          gcloud run deploy puco-backend \
            --image $REGISTRY/puco-backend:$GITHUB_SHA \
            --region asia-northeast3
```

**완료 기준:**
- [ ] main push 시 워크플로 실행
- [ ] Artifact Registry에 이미지 존재
- [ ] Cloud Run 서비스 업데이트

---

### Task 3.4 Cloud Run 서비스 정의

**구체적 변경 사항:**
- WebSocket 지원: 세션 친화성(session affinity) 활성화
- Secret Manager에서 `SECRET_KEY`, `DATABASE_URL`, `GOOGLE_CLIENT_ID` 주입
- 최소 인스턴스 1개 (cold start 방지)
- 메모리 1Gi, CPU 1

**완료 기준:**
- [ ] Cloud Run에서 `/health` 200 응답
- [ ] WebSocket 연결 정상 작동

---

### Task 3.5 Cloud Armor (WAF) + Cloud CDN

**구체적 변경 사항:**
- Cloud Armor 보안 정책: Rate Limiting (2000 req/5min per IP), SQL Injection 필터, XSS 필터
- Cloud CDN: 정적 에셋 캐싱 (프론트엔드)
- HTTPS 강제 (Cloud Load Balancer + 관리형 SSL 인증서)

**완료 기준:**
- [ ] WAF 규칙 활성화 확인
- [ ] HTTP → HTTPS 리다이렉트 작동

---

### Task 3.6 Cloud Monitoring + 알람 대시보드

**구체적 변경 사항:**
- 알람: CPU > 80% → 오토스케일링, API 5xx > 1% → 알람, WebSocket 연결 수 급감 → 알람
- 대시보드: 요청 수, 응답 시간, 에러율, 게임 수 추이
- Cloud Run 자동 스케일링 설정 (min=1, max=10)

**완료 기준:**
- [ ] Cloud Monitoring 대시보드에 메트릭 표시
- [ ] 알람 테스트 발생 확인

---

## Phase 4 — 시스템 자동화 + 아키텍처 전환 (2개월)

### Task 4.1 `[ARCH Phase 3]` Frontend Legacy → v1 API 전환

**설명:** ARCHITECTURE.md의 핵심 목표. 현재 프론트엔드가 Legacy API로 POST 폭탄을 보내는 구조를 v1 API + WebSocket 수신으로 전환.

**대상 파일:** `frontend/src/` 전체 WebSocket/API 호출 코드

**구체적 변경 사항:**
- 인간 액션: `POST /api/v1/game/action` 1회만 호출
- 상태 업데이트: WebSocket `STATE_UPDATE` 이벤트로 수신
- 봇 턴: 프론트엔드 관여 없음 (서버 백그라운드 처리)

**완료 기준:**
- [ ] Legacy API (`/api/*`) 호출 0건
- [ ] WebSocket으로 봇 턴 결과 수신

---

### Task 4.2 RL 데이터 GCS 자동 업로드

**대상 파일:** `backend/app/services/ml_logger.py`

**구체적 변경 사항:**

```python
from google.cloud import storage

GCS_BUCKET = os.getenv("GCS_LOG_BUCKET")

async def _upload_to_gcs(record: dict):
    if not GCS_BUCKET:
        return
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(f"logs/transitions_{date.today()}.jsonl")
    blob.upload_from_string(json.dumps(record) + "\n", content_type="application/json")
```

**완료 기준:**
- [ ] GCS 버킷에 JSONL 파일 존재

---

### Task 4.3 `[ML H-05]` 자동 학습-검증-배포 파이프라인

**대상 파일:** `backend/app/services/retrain_trigger.py` (신규), `scripts/validate_model.py` (신규)

**구체적 변경 사항:**

```python
# retrain_trigger.py
async def check_retrain_threshold(db: Session):
    count = db.query(func.count(GameLog.id)).scalar()
    cooldown_key = "retrain:cooldown"
    if count > THRESHOLD and not await redis.exists(cooldown_key):
        # GCE 학습 Job 트리거 또는 Pub/Sub 메시지
        await redis.setex(cooldown_key, 86400, "1")  # 24시간 쿨다운
```

```python
# scripts/validate_model.py
def validate(model_path, baseline_path):
    """새 모델 vs 기존 모델 대전. win_rate > 0.55이면 통과."""
    ...
```

**완료 기준:**
- [ ] game_logs N건 초과 시 자동 트리거
- [ ] 검증 통과 모델만 배포

---

### Task 4.4 학습 전용 GCE/Vertex AI Job

**대상 파일:** `infrastructure/modules/training/` (신규)

**구체적 변경 사항:**
- GPU가 필요한 경우: Vertex AI Custom Training Job
- CPU 전용: GCE VM (spot instance)
- `requirements.train.txt` 이미지 사용
- 학습 완료 시 GCS에 모델 업로드 → Hot-Reload 트리거

**완료 기준:**
- [ ] 클라우드에서 학습 완료
- [ ] 모델 아티팩트 GCS/MLflow에 저장

---

## 부록 A — OWASP Top 10 대응 현황

| OWASP | 항목 | 현재 상태 | 해당 Task |
|-------|------|-----------|-----------|
| A01 | Broken Access Control | 🔴 Legacy 무인증, IDOR | Task 0.2, 0.3 |
| A02 | Cryptographic Failures | 🔴 .env 시크릿 Git 노출 | Task 0.1 |
| A03 | Injection | ✅ ORM 사용으로 방어 | — |
| A04 | Insecure Design | 🟡 Rate Limiting 없음 | Task 1.3 |
| A05 | Security Misconfiguration | 🟡 포트/Debug 노출 | Task 1.1, 1.2, 1.4 |
| A06 | Vulnerable Components | ⚪ 미평가 | — |
| A07 | Auth Failures | 🟠 일부 미인증 | Task 0.2 |
| A08 | Software/Data Integrity | ✅ Google OAuth 양호 | — |
| A09 | Logging/Monitoring | 🟡 보안 이벤트 미분류 | Task 1.17 |
| A10 | SSRF | ✅ 외부 요청 없음 | — |

## 부록 B — 보안 점검 체크리스트

- [ ] `.env` 파일이 `.gitignore`에 포함
- [ ] SECRET_KEY 최소 64바이트 (128자 hex)
- [ ] `puco_password` 기본값 변경
- [ ] Redis 비밀번호 설정
- [ ] `DEBUG=false` (프로덕션)
- [ ] CORS `allow_origins` 실제 도메인으로 제한 (현재 `*` 아님 확인)
- [ ] 모든 포트 localhost 바인딩 (프로덕션)
- [ ] GCP 배포 시 Secret Manager 사용

## 부록 C — 인증키 생성 가이드

```bash
# SECRET_KEY (JWT 서명용 — 64바이트 hex)
python -c "import secrets; print(secrets.token_hex(64))"

# POSTGRES_PASSWORD (강력한 DB 비밀번호)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# REDIS_PASSWORD
python -c "import secrets; print(secrets.token_urlsafe(24))"

# GOOGLE_CLIENT_ID
# → Google Cloud Console → API 및 서비스 → 사용자 인증 정보 → OAuth 2.0 클라이언트 ID
```

## 부록 D — PPO 데이터 전처리 파이프라인 참조 구조

```
PuCo_RL/data_pipeline/          (Phase 4에서 구현)
├── loader.py                   # DB/JSONL → RawTransition 로드
├── feature_extractor.py        # state_dict → 고정 길이 수치 벡터 (~120차원)
├── normalizer.py               # Running Mean/Std 정규화
├── reward_shaper.py            # 즉시 보상(Δvp) + 종료 보상(±1) + GAE
├── dataset.py                  # PyTorch Dataset (PPOBatch 텐서)
└── pipeline.py                 # 전체 오케스트레이터
```
