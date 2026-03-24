# Security Assessment Report
## Puerto Rico AI Battle Platform

> **평가 기준:** OWASP Top 10 · Backend Security Coder · API Security Testing · Kaizen
> **평가 대상:** `castone/backend/` 전체 코드베이스
> **작성일:** 2026-03-24
> **평가자:** AI Security Review (Claude)

---

## 요약 (Executive Summary)

| 등급 | 건수 | 상태 |
|------|------|------|
| 🔴 CRITICAL | 1 | 즉시 조치 필요 |
| 🟠 HIGH | 4 | 우선 처리 필요 |
| 🟡 MEDIUM | 6 | 단기 처리 필요 |
| 🔵 LOW | 5 | 중기 개선 권장 |
| ✅ GOOD | 7 | 잘 구현된 부분 |

**전반적 평가:** 인증 핵심 로직(Google OAuth, JWT)은 잘 구현되어 있으나, **인가(Authorization)**, **비밀정보 관리**, **인프라 노출** 측면에서 심각한 결함이 존재합니다.

---

## 🔴 CRITICAL

### C-01. 실제 시크릿 키가 `.env` 파일에 노출
**파일:** `castone/.env`
**OWASP:** A02 - Cryptographic Failures, A05 - Security Misconfiguration

```env
SECRET_KEY=0c472928437518ea59c3988881ea1d95e5aaac57ab8fd7bcc0f83c48691a4bd2
GOOGLE_CLIENT_ID=425315953027-viu5rcbnb91in1omcgfjbanugdqbd185.apps.googleusercontent.com
```

**문제:**
- `.env` 파일이 Git에 추적되고 있음
- 실제 JWT 서명 키와 Google OAuth Client ID가 레포지토리에 노출
- 해당 `.env`가 Github에 push된 경우, 모든 JWT 토큰 위조 가능
- Google OAuth Client ID 노출 시 피싱 공격 벡터 생성

**수정 방법:**
1. `.gitignore`에 `.env` 추가 (`.env.example`만 커밋)
2. `SECRET_KEY` 즉시 교체 (기존 키로 서명된 모든 JWT는 폐기)
3. `GOOGLE_CLIENT_ID`는 공개 가능하나 `.env.example`로 이동 권장
4. Git 히스토리에서 제거: `git filter-branch` 또는 `git-secrets`

```bash
# 즉시 실행
echo ".env" >> .gitignore
# SECRET_KEY 재생성
python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

---

## 🟠 HIGH

### H-01. Legacy API 전체가 인증 없음
**파일:** `backend/app/api/legacy.py`
**OWASP:** A01 - Broken Access Control, A07 - Identification and Authentication Failures

```python
# 모든 legacy 엔드포인트에 Depends(get_current_user) 없음
@router.post("/new-game")
def new_game(body: NewGameBody):     # ← 인증 없음
    session.reset()
    session.start_game()

@router.post("/bot/set")
def bot_set(body: BotSetBody):       # ← 인증 없음
    session.bot_players[idx] = body.bot_type
```

**영향:**
- 익명 공격자가 `/api/new-game`으로 진행 중인 게임 초기화 가능
- `/api/bot/set`으로 봇 설정 변조 가능
- `/api/game-state`, `/api/final-score` 등 게임 정보 무단 조회 가능

**수정 방법:**
```python
# 최소한 봇 전용 고정 API 키 검증 추가 (Kaizen: 점진적 개선)
from fastapi import Header

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

def require_internal_key(x_api_key: str = Header(...)):
    if x_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
```

---

### H-02. 게임 시작/방 생성 엔드포인트 인증 없음
**파일:** `backend/app/api/v1/game.py`, `backend/app/api/v1/room.py`
**OWASP:** A01 - Broken Access Control

```python
# game.py
@router.post("/{game_id}/start")
async def start_game(game_id: UUID, db: Session = Depends(get_db)):
    # ← get_current_user 없음!
    service = GameService(db)

# room.py
@router.post("/", response_model=GameRoomResponse)
async def create_room(room_info: GameRoomCreate, db: Session = Depends(get_db)):
    # ← 인증 없음 → 무한 방 생성 가능 (리소스 고갈)
```

**영향:**
- 누구나 임의의 게임을 시작할 수 있음
- 인증 없이 방을 무한 생성 → DB/메모리 소진 (DoS)

**수정:**
```python
# game.py
@router.post("/{game_id}/start")
async def start_game(
    game_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # 추가
):

# room.py
@router.post("/", response_model=GameRoomResponse)
async def create_room(
    room_info: GameRoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # 추가
):
```

---

### H-03. 게임 액션 인가(Authorization) 미검증
**파일:** `backend/app/api/v1/game.py`
**OWASP:** A01 - Broken Access Control (IDOR 패턴)

```python
@router.post("/{game_id}/action")
async def perform_action(
    game_id: UUID,
    action_data: GameAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # JWT 검증은 함
):
    actor_id = str(current_user.id)
    # ← 하지만 current_user가 game_id의 실제 플레이어인지 확인 안 함!
    result = service.process_action(game_id, actor_id, action_int)
```

**영향:**
- 인증된 아무 유저가 남의 게임에 액션 실행 가능
- `game_id`만 알면 다른 플레이어 턴에 끼어들 수 있음

**수정:**
```python
# GameService.process_action 또는 game.py에 추가
room = db.query(GameSession).filter(GameSession.id == game_id).first()
if not room:
    raise HTTPException(status_code=404, detail="Game not found")
if str(current_user.id) not in (room.players or []):
    raise HTTPException(status_code=403, detail="You are not a player in this game")
```

---

### H-04. WebSocket JWT가 URL 쿼리 파라미터로 전송
**파일:** `backend/app/api/v1/ws.py`
**OWASP:** A02 - Cryptographic Failures

```python
@router.websocket("/{game_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    game_id: str,
    token: str = Query(None),  # ← URL에 JWT 노출: ws://server/ws/123?token=eyJ...
):
```

**영향:**
- JWT가 서버 액세스 로그에 평문 기록
- 브라우저 히스토리, 프록시 로그에 노출
- Referrer 헤더로 제3자에게 누출 가능

**수정:**
```python
# 연결 후 첫 메시지로 토큰 전송하는 패턴으로 변경
@router.websocket("/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    await websocket.accept()
    try:
        # 첫 메시지에서 토큰 수신
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        token = auth_msg.get("token")
    except asyncio.TimeoutError:
        await websocket.close(code=1008)
        return
```

---

## 🟡 MEDIUM

### M-01. 헬스 엔드포인트 인프라 정보 노출
**파일:** `backend/app/main.py`

```python
@app.get("/health")
async def health():
    except Exception as e:
        checks["postgresql"] = f"error: {e}"  # ← DB 연결 문자열 노출 가능
        checks["redis"] = f"error: {e}"       # ← Redis 연결 정보 노출 가능
```

**수정:**
```python
checks["postgresql"] = "error"  # 에러 상세 제거
logger.error("PostgreSQL health check failed: %s", e)  # 서버 로그에만 기록
```

---

### M-02. Adminer 포트 인증 없이 공개
**파일:** `docker-compose.yml`

```yaml
adminer:
  ports:
    - "8080:8080"  # ← 인터넷에서 직접 DB 접근 가능
```

**영향:**
- 포트 8080 접근 시 DB 직접 조작 가능
- `puco_user/puco_password`는 추측하기 쉬운 자격증명

**수정:**
```yaml
# 개발 환경에서만 활성화, 또는 localhost 바인딩
adminer:
  ports:
    - "127.0.0.1:8080:8080"  # localhost만 접근 허용
```

---

### M-03. Redis 비밀번호 없음 / 포트 공개
**파일:** `docker-compose.yml`

```yaml
redis:
  ports:
    - "6379:6379"  # ← 인터넷에서 직접 접근 가능, 비밀번호 없음
```

**영향:**
- Redis에 직접 접근 시 게임 상태 조작 가능
- `game:{id}:state` 키를 임의로 수정 가능
- Redis pub/sub 채널 도청 가능

**수정:**
```yaml
redis:
  command: redis-server --requirepass ${REDIS_PASSWORD}
  ports:
    - "127.0.0.1:6379:6379"  # localhost 바인딩
```

---

### M-04. Rate Limiting 전무
**전체 API**
**OWASP:** A04 - Insecure Design

```python
# /api/v1/auth/google — 브루트포스 보호 없음
# /api/v1/{game_id}/action — 무제한 요청 가능
# 모든 legacy 엔드포인트 — 무제한
```

**영향:**
- Auth 엔드포인트 브루트포스 공격
- 게임 액션 스팸으로 봇 AI 과부하 유발 (DoS)
- DB 쓰기 폭탄

**수정 (Kaizen 점진적):**
```python
# slowapi 또는 fastapi-limiter 사용
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/google")
@limiter.limit("10/minute")
async def google_login(request: Request, body: GoogleTokenRequest, ...):
```

---

### M-05. `DEBUG=true` 환경 설정
**파일:** `castone/.env`

```env
DEBUG=true
```

**영향:**
- FastAPI가 DEBUG 모드에서 내부 스택 트레이스를 HTTP 응답에 포함
- 코드 경로, 변수명, 파일 경로 노출

**수정:** 프로덕션 배포 시 `DEBUG=false` 설정

---

### M-06. 게임 액션 payload 크기 미제한
**파일:** `backend/app/schemas/game.py`, `backend/app/api/v1/game.py`

```python
class GameAction(BaseModel):
    payload: Dict[str, Any]  # ← 크기 제한 없음
```

**영향:**
- 수십 MB의 payload 전송으로 메모리 소진 (DoS)

**수정:**
```python
from pydantic import BaseModel, Field

class GameAction(BaseModel):
    game_id: UUID
    action_type: str = Field(max_length=50)
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, v):
        if len(str(v)) > 1024:  # 1KB 제한
            raise ValueError("Payload too large")
        return v
```

---

## 🔵 LOW

### L-01. HTTP 보안 헤더 미설정
**파일:** `backend/app/main.py`

현재 누락된 헤더:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy`
- `Strict-Transport-Security` (HSTS)
- `Referrer-Policy`

**수정:**
```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware
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

---

### L-02. JWT 토큰 취소(Revocation) 불가
**파일:** `backend/app/core/security.py`

```python
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24시간
# Refresh token 없음, 블랙리스트 없음
```

**영향:**
- 토큰 탈취 시 24시간 동안 유효
- 로그아웃해도 토큰 무효화 불가

**수정 (Kaizen 점진적):**
```python
# Redis에 블랙리스트 저장 (로그아웃 시)
async def revoke_token(jti: str, expires_in: int):
    await redis.setex(f"blacklist:{jti}", expires_in, "1")

# JWT에 jti claim 추가
to_encode = {"exp": expire, "sub": str(subject), "jti": str(uuid4())}
```

---

### L-03. ValueError 내부 메시지 HTTP 응답에 노출
**파일:** `backend/app/api/v1/game.py`

```python
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
    # ← 엔진 내부 오류 메시지가 그대로 클라이언트에 전송
```

**수정:**
```python
except ValueError as e:
    logger.warning("Game action failed: %s", e)
    raise HTTPException(status_code=400, detail="Invalid action")
```

---

### L-04. MLLogger 로그 파일 무한 증가
**파일:** `backend/app/services/ml_logger.py`

```python
LOG_DIR = os.path.abspath("../../../data/logs")
# 파일 크기 제한 없음, 로테이션 없음
async with aiofiles.open(log_file, mode='a') as f:
    await f.write(json.dumps(record) + "\n")
```

**영향:**
- 디스크 소진 → 서버 중단
- game_id, actor_id, 전체 게임 상태가 평문으로 파일에 저장

**수정:**
```python
import logging.handlers

# RotatingFileHandler 사용 (100MB × 5개 보관)
handler = logging.handlers.RotatingFileHandler(
    log_file, maxBytes=100*1024*1024, backupCount=5
)
```

---

### L-05. PostgreSQL 포트 공개
**파일:** `docker-compose.yml`

```yaml
db:
  ports:
    - "5432:5432"  # 외부 접근 가능
```

**수정:**
```yaml
db:
  ports:
    - "127.0.0.1:5432:5432"  # localhost만 접근
  # 또는 ports 섹션 완전 제거 (서비스간 내부 통신만 사용)
```

---

## ✅ 잘 구현된 보안 사항

| 항목 | 위치 | 설명 |
|------|------|------|
| JWT 시크릿 없으면 서버 시작 거부 | `core/security.py:9` | `RuntimeError` 발생 — Fail-fast 패턴 |
| Google OAuth 토큰 서버 검증 | `api/v1/auth.py:75` | Google 공개 키로 직접 검증 |
| 이메일 인증 여부 확인 | `api/v1/auth.py:91` | `email_verified` 체크 |
| 닉네임 입력 검증 (regex) | `schemas/auth.py:22` | allowlist 패턴 적용 |
| google_id, email 로그 미출력 | `api/v1/auth.py` | PII 로깅 방지 |
| 레이스컨디션 처리 | `api/v1/auth.py:116` | IntegrityError → 재조회 |
| allow_credentials=False | `main.py:33` | CORS 자격증명 비활성화 |
| 액션 마스크 검증 | `game_service.py:65` | 유효하지 않은 액션 즉시 거부 |
| SQLAlchemy ORM 사용 | 전체 DB 접근 | SQL Injection 자동 방지 |

---

## 개선 우선순위 (Kaizen 로드맵)

```
즉시 (24시간 이내)
  ├── C-01: .env를 .gitignore에 추가 + SECRET_KEY 교체
  └── H-01~H-03: 핵심 API 인증/인가 추가

이번 주
  ├── H-04: WebSocket JWT URL → 첫 메시지 방식으로 변경
  ├── M-01: 헬스 엔드포인트 에러 상세 제거
  ├── M-02~M-03: Adminer/Redis/PostgreSQL 포트 localhost 바인딩
  └── M-05: DEBUG=false 설정

이번 달
  ├── M-04: slowapi로 Rate Limiting 추가 (auth 엔드포인트 우선)
  ├── M-06: payload 크기 제한
  ├── L-01: 보안 헤더 미들웨어 추가
  ├── L-03: ValueError 메시지 숨기기
  └── L-04: MLLogger 로테이션 추가

중기
  ├── L-02: JWT refresh token + 블랙리스트
  └── L-05: 프로덕션 배포 시 포트 정리
```

---

## OWASP Top 10 대응 현황

| OWASP | 항목 | 현재 상태 |
|-------|------|-----------|
| A01 | Broken Access Control | 🔴 Legacy 무인증, IDOR 존재 |
| A02 | Cryptographic Failures | 🔴 .env 시크릿 노출 |
| A03 | Injection | ✅ ORM 사용으로 방어 |
| A04 | Insecure Design | 🟡 Rate limiting 없음 |
| A05 | Security Misconfiguration | 🟡 Adminer/Redis/Debug 노출 |
| A06 | Vulnerable Components | ⚪ 미평가 (의존성 스캔 필요) |
| A07 | Auth Failures | 🟠 일부 엔드포인트 미인증 |
| A08 | Software/Data Integrity | ✅ Google OAuth 검증 양호 |
| A09 | Logging/Monitoring | 🟡 로그 있으나 보안 이벤트 미분류 |
| A10 | SSRF | ✅ 외부 요청 없음 |

---

## BFRI 평가 (보안 수정 용이성)

### C-01 + M-02~M-05 수정 (설정 변경)
`BFRI = (5+5) - (1+1+1) = 7` → ✅ Safe — 코드 변경 없이 설정만 수정

### H-01~H-03 수정 (인증/인가 추가)
`BFRI = (4+4) - (2+1+2) = 3` → ⚠️ Moderate — 테스트 필요

### M-04 Rate Limiting
`BFRI = (3+4) - (2+1+1) = 3` → ⚠️ Moderate — 의존성 추가 필요

---

*이 보고서는 코드 정적 분석 기반입니다. 동적 침투 테스트(실제 공격 시뮬레이션)는 별도 수행을 권장합니다.*
