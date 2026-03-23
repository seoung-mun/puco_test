# Puerto Rico AI Battle Platform — 다음 단계 종합 보고서

> **작성일:** 2026-03-22 (v1) / 2026-03-23 (v2 — 데이터 검증·인증키·PPO 전처리 추가)
> **분석 관점:** MLOps Engineer · Auth Implementation Patterns · Docker Expert · AWS Serverless
> **대상 코드베이스:** `castone/backend/` (FastAPI + PostgreSQL + Redis + PyTorch PPO)

---

## 목차

1. [현재 상태 요약](#1-현재-상태-요약)
2. [MLOps — ML 파이프라인 및 모델 관리](#2-mlops--ml-파이프라인-및-모델-관리)
3. [Auth — 인증 시스템 완성도](#3-auth--인증-시스템-완성도)
4. [Docker — 컨테이너 최적화](#4-docker--컨테이너-최적화)
5. [AWS Serverless — 클라우드 배포 준비](#5-aws-serverless--클라우드-배포-준비)
6. [우선순위 액션 플랜](#6-우선순위-액션-플랜)
7. [데이터 검증 로직 테스트 결과](#7-데이터-검증-로직-테스트-결과)
8. [인증키 생성 가이드](#8-인증키-생성-가이드)
9. [PPO 데이터 전처리 파이프라인 설계](#9-ppo-데이터-전처리-파이프라인-설계)

---

## 1. 현재 상태 요약

| 영역 | 완성도 | 상태 |
|------|--------|------|
| 게임 엔진 통합 (PettingZoo AEC) | ✅ 완료 | Production-ready |
| DB 스키마 + Alembic 마이그레이션 | ✅ 완료 | 마이그레이션 002까지 적용 |
| Redis Pub/Sub + WebSocket | ✅ 완료 | 멀티인스턴스 대응 |
| Google OAuth 로그인 + 닉네임 설정 | ✅ 완료 | 이번 세션에서 구현 |
| JWT 인증 보안 강화 | ✅ 완료 | SECRET_KEY 필수화 |
| RL 데이터 로깅 (PostgreSQL + JSONL) | ✅ 완료 | game_logs 테이블 + 파일 이중 저장 |
| Docker 경량화 | ⚠️ 미흡 | 단일 스테이지, .dockerignore 없음 |
| MLOps 파이프라인 | ❌ 없음 | 모델 버전 관리·자동 재학습 없음 |
| Rate Limiting | ❌ 없음 | 모든 엔드포인트 무제한 |
| AWS 배포 설정 | ❌ 없음 | Docker Compose만 존재 |
| CI/CD 파이프라인 | ❌ 없음 | GitHub Actions 없음 |

---

## 2. MLOps — ML 파이프라인 및 모델 관리

### 현재 구조의 문제점

현재 `bot_service.py`의 PPO 모델 관리 방식은 다음과 같습니다:

```
PuCo_RL/models/ppo_agent_update_100.pth  ← 단일 파일, 버전 관리 없음
BotService._agent_instance               ← 클래스 변수, 인스턴스 캐시
torch.load(..., weights_only=True)       ← 첫 요청 시 로드 (Cold Start 지연)
```

**문제:**
- 모델 파일이 git/DVC 없이 `PuCo_RL/models/`에 직접 저장됨
- 학습 실험 결과(loss, reward, episode) 추적 없음
- 모델 교체 시 서버 재시작 필요 (다운타임 발생)
- 학습 서버와 서빙 서버의 분리 계획이 TODO에만 존재

### 해야 할 일

#### 2-1. MLflow 실험 추적 도입 (우선순위: 높음)

`PuCo_RL/` 학습 코드에 MLflow 통합:

```python
# PuCo_RL/train.py에 추가
import mlflow
import mlflow.pytorch

with mlflow.start_run():
    mlflow.log_params({
        "learning_rate": lr,
        "num_players": num_players,
        "total_timesteps": total_timesteps,
    })
    mlflow.log_metrics({
        "episode_reward": reward,
        "win_rate": win_rate,
    }, step=episode)
    mlflow.pytorch.log_model(agent, "ppo_agent")
```

MLflow 서버를 `docker-compose.yml`에 추가:
```yaml
mlflow:
  image: ghcr.io/mlflow/mlflow:v2.13.0
  ports:
    - "5000:5000"
  volumes:
    - ./mlruns:/mlruns
  command: mlflow server --host 0.0.0.0
```

#### 2-2. 모델 버전 관리 (DVC 또는 MLflow Model Registry)

```bash
# DVC 초기화 (PuCo_RL/)
cd PuCo_RL
dvc init
dvc add models/ppo_agent_update_100.pth
git add .dvc/  models/.gitignore
```

또는 MLflow Model Registry에서 `Staging → Production` 승격 워크플로 구축.

#### 2-3. 학습/서빙 서버 분리 (TODO 항목 4번 이행)

```
현재:
  docker-compose.yml
    └── backend (FastAPI + PyTorch 포함, ~4GB 이미지)

목표:
  docker-compose.prod.yml
    └── backend-slim (FastAPI만, ~500MB)
  docker-compose.train.yml
    └── trainer (PyTorch + PuCo_RL)
    └── mlflow
```

`backend/requirements.txt`를 두 파일로 분리:
```
requirements.api.txt     # FastAPI, SQLAlchemy, Redis 등 (서빙용)
requirements.train.txt   # torch, gymnasium, pettingzoo 등 (학습용)
```

#### 2-4. 자동 재학습 트리거

게임 데이터가 충분히 쌓이면 (`game_logs` 건수 기준) 자동 재학습:

```python
# backend/app/services/retrain_trigger.py (신규)
async def check_retrain_threshold(db: Session):
    """game_logs가 10,000건을 초과하면 학습 작업 큐에 추가."""
    count = db.query(func.count(GameLog.id)).scalar()
    if count > 10_000:
        # SQS 메시지 발행 또는 Airflow DAG 트리거
        ...
```

#### 2-5. 모델 Hot-Reload (다운타임 없는 모델 교체)

```python
# BotService에 추가
@classmethod
async def reload_model(cls, model_path: str):
    """서버 재시작 없이 새 모델 로드. POST /internal/reload-model에서 호출."""
    new_agent = cls._load_from_path(model_path)
    cls._agent_instance = new_agent
    logger.info("Model reloaded from %s", model_path)
```

---

## 3. Auth — 인증 시스템 완성도

### 현재 구현 상태

이번 세션에서 구현된 내용:
- ✅ `POST /api/v1/auth/google` — Google id_token 검증 → JWT 발급
- ✅ `PATCH /api/v1/auth/me/nickname` — 닉네임 설정 (unique 제약)
- ✅ `GET /api/v1/auth/me` — 현재 사용자 정보
- ✅ `needs_nickname` 플래그로 온보딩 플로우 안내

### 해야 할 일

#### 3-1. Rate Limiting (우선순위: 높음)

현재 모든 엔드포인트에 rate limit이 없어 브루트포스/DoS에 취약합니다.

```bash
pip install slowapi
```

```python
# app/main.py에 추가
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address, storage_uri=REDIS_URL)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# auth.py 엔드포인트에 데코레이터 추가
@router.post("/google")
@limiter.limit("10/minute")
async def google_login(request: Request, ...):
    ...
```

적용 기준:
| 엔드포인트 | 제한 |
|-----------|------|
| `POST /auth/google` | 10회/분 per IP |
| `PATCH /auth/me/nickname` | 5회/분 per user |
| `POST /game/action` | 60회/분 per user |
| `GET /health` | 30회/분 per IP |

#### 3-2. 감사 로그 (Audit Log)

인증 이벤트를 PostgreSQL에 기록:

```python
# app/db/models.py에 추가
class AuthAuditLog(Base):
    __tablename__ = "auth_audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    event_type = Column(String)  # "login", "nickname_set", "token_refresh"
    ip_address = Column(String)
    user_agent = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # user_id/IP는 별도 컬럼으로 분리 (PII 분리 원칙)
```

#### 3-3. JWT 토큰 무효화 (로그아웃/탈퇴 대응)

현재 JWT는 만료 전까지 무효화 불가합니다. Redis Blocklist로 해결:

```python
# app/core/security.py에 추가
async def revoke_token(jti: str, expires_in: int):
    """토큰 JTI를 Redis blocklist에 추가 (남은 유효시간만큼 TTL)."""
    await async_redis_client.setex(f"blocklist:{jti}", expires_in, "1")

async def is_token_revoked(jti: str) -> bool:
    return await async_redis_client.exists(f"blocklist:{jti}") > 0
```

JWT payload에 `jti` (JWT ID) 필드 추가 필요.

#### 3-4. 로그아웃 엔드포인트

```python
@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), token: str = ...):
    """토큰을 즉시 무효화."""
    payload = decode_access_token(token)
    await revoke_token(payload["jti"], remaining_seconds)
    return {"message": "로그아웃 완료"}
```

#### 3-5. 회원 탈퇴 처리

GDPR 준수를 위한 사용자 데이터 삭제/익명화:

```python
@router.delete("/me")
async def delete_account(current_user: User = Depends(get_current_user), db: Session = ...):
    """사용자 계정 삭제 — google_id, email 익명화 보존 (통계용)."""
    current_user.google_id = f"deleted_{current_user.id}"
    current_user.email = None
    current_user.nickname = None
    db.commit()
```

---

## 4. Docker — 컨테이너 최적화

### 현재 Dockerfile 문제점

```dockerfile
# 현재: 단일 스테이지, 빌드 도구가 프로덕션 이미지에 포함됨
FROM python:3.12-slim          # ~200MB
RUN pip install -r requirements.txt  # torch 포함 시 ~5GB+
RUN useradd -m appuser
CMD ["/entrypoint.sh"]
```

**문제:**
- `.dockerignore` 없음 → 불필요한 파일이 빌드 컨텍스트에 포함
- 단일 `requirements.txt`에 PyTorch 포함 → 서빙 이미지가 과도하게 큼
- `--reload` 옵션이 프로덕션 entrypoint에 있음 (보안/성능 이슈)
- `HEALTHCHECK` 지시어 없음
- 레이어 캐시 비효율 (소스코드 변경 시 pip install 재실행)

### 해야 할 일

#### 4-1. .dockerignore 생성 (우선순위: 즉시)

```dockerignore
# castone/backend/.dockerignore
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.venv/
*.egg-info/
.git/
.gitignore
tests/
*.md
.env
.env.*
data/logs/
mlruns/
```

#### 4-2. 멀티스테이지 빌드 + 서빙/학습 분리 (우선순위: 높음)

```dockerfile
# ── Stage 1: 의존성 설치 ────────────────────────────────
FROM python:3.12-slim AS deps
WORKDIR /app
COPY requirements.api.txt .
RUN pip install --no-cache-dir -r requirements.api.txt

# ── Stage 2: 프로덕션 이미지 ───────────────────────────
FROM python:3.12-slim AS production
WORKDIR /app

# 비루트 사용자 (특정 UID 지정)
RUN useradd --uid 1001 --no-create-home --shell /bin/false appuser

# 의존성만 복사 (소스코드와 레이어 분리)
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

#### 4-3. entrypoint.sh 프로덕션/개발 분리

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

#### 4-4. docker-compose 프로덕션/개발 분리

```yaml
# docker-compose.override.yml (개발용, git에 포함)
services:
  backend:
    volumes:
      - ./backend:/app  # 소스 핫리로드
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

#### 4-5. Docker Secrets로 민감 정보 관리

```yaml
# docker-compose.yml
services:
  backend:
    secrets:
      - secret_key
      - google_client_id

secrets:
  secret_key:
    external: true  # docker secret create로 생성
  google_client_id:
    external: true
```

```python
# app/core/config.py에서 파일로 읽기
def _read_secret(name: str, env_var: str) -> str:
    secret_path = f"/run/secrets/{name}"
    if os.path.exists(secret_path):
        return open(secret_path).read().strip()
    return os.getenv(env_var, "")
```

#### 4-6. 예상 이미지 크기 개선

| 구성 | 현재 | 개선 후 |
|------|------|---------|
| 서빙 이미지 (torch 포함) | ~5.5GB | — |
| 서빙 이미지 (torch 제외) | — | ~400MB |
| 학습 이미지 (torch 포함) | — | ~5.5GB (별도) |

---

## 5. AWS Serverless — 클라우드 배포 준비

> **전제:** TODO 항목 4번 "도커 경량화 + 학습/서빙 분리" 완료 후 진행 권장

### 아키텍처 설계 (권장)

```
Internet
  │
  ▼
[CloudFront + WAF]          ← DDoS 방어, Rate Limiting
  │
  ▼
[Application Load Balancer]  ← SSL Termination, Health Check
  │
  ▼
[ECS Fargate - backend]      ← FastAPI (컨테이너)
  │        │
  ▼        ▼
[RDS      [ElastiCache       ← PostgreSQL + Redis 관리형 서비스
 Aurora]   Redis]

[S3]       ← JSONL 로그 파일 저장
[ECR]      ← Docker 이미지 레지스트리
[Secrets   ← SECRET_KEY, GOOGLE_CLIENT_ID 저장
 Manager]
```

### 해야 할 일

#### 5-1. AWS 인프라 IaC (Terraform)

```hcl
# infrastructure/main.tf
module "vpc" {
  source = "terraform-aws-modules/vpc/aws"
  # ...
}

module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  engine  = "postgres"
  engine_version = "16"
  instance_class = "db.t3.micro"
  # ...
}

module "elasticache" {
  source = "terraform-aws-modules/elasticache/aws"
  engine = "redis"
  # ...
}
```

#### 5-2. GitHub Actions CI/CD 파이프라인

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          pip install -r castone/backend/requirements.api.txt
          pytest castone/backend/tests/

  build-push:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build & push to ECR
        uses: aws-actions/amazon-ecr-login@v2
      - run: |
          docker build -t $ECR_REGISTRY/puco-backend:$GITHUB_SHA \
            --target production castone/backend/
          docker push $ECR_REGISTRY/puco-backend:$GITHUB_SHA

  deploy:
    needs: build-push
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to ECS
        uses: aws-actions/amazon-ecs-deploy-task-definition@v1
        with:
          task-definition: ecs-task-def.json
          service: puco-backend
          cluster: puco-cluster
```

#### 5-3. ECS Task Definition

```json
{
  "family": "puco-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [{
    "name": "backend",
    "image": "<ECR_URI>:latest",
    "portMappings": [{"containerPort": 8000}],
    "environment": [
      {"name": "DEBUG", "value": "false"}
    ],
    "secrets": [
      {"name": "SECRET_KEY",        "valueFrom": "arn:aws:secretsmanager:..."},
      {"name": "DATABASE_URL",      "valueFrom": "arn:aws:secretsmanager:..."},
      {"name": "GOOGLE_CLIENT_ID",  "valueFrom": "arn:aws:secretsmanager:..."}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/puco-backend",
        "awslogs-region": "ap-northeast-2"
      }
    },
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
      "interval": 30,
      "timeout": 10,
      "retries": 3
    }
  }]
}
```

#### 5-4. RL 학습 데이터 → S3 자동 업로드

현재 JSONL 파일이 컨테이너 로컬 볼륨에만 저장됩니다. S3로 이중 저장:

```python
# app/services/ml_logger.py 수정
import boto3

S3_BUCKET = os.getenv("S3_LOG_BUCKET")  # 선택적

async def _write_log(record: dict):
    # 기존: 로컬 파일
    await _write_to_file(record)
    # 추가: S3 (설정된 경우)
    if S3_BUCKET:
        await _upload_to_s3(record)
```

#### 5-5. 모니터링 및 알람

```python
# CloudWatch 커스텀 메트릭
import boto3
cloudwatch = boto3.client("cloudwatch")

def emit_game_metric(game_id: str, action_count: int):
    cloudwatch.put_metric_data(
        Namespace="PuCo/GameMetrics",
        MetricData=[{
            "MetricName": "ActionsPerGame",
            "Value": action_count,
            "Unit": "Count",
        }]
    )
```

알람 설정 권장:
- ECS CPU > 80% → Auto Scaling 트리거
- RDS 연결 수 > 80개 → 알람
- API 5xx 에러율 > 1% → 알람
- WebSocket 연결 수 급감 → 알람

---

## 6. 우선순위 액션 플랜

### Phase 1 — 배포 준비 (지금 당장)

| # | 작업 | 담당 관점 | 예상 시간 |
|---|------|-----------|-----------|
| 1 | `requirements.api.txt` / `requirements.train.txt` 분리 | Docker + MLOps | 1시간 |
| 2 | `.dockerignore` 생성 | Docker | 30분 |
| 3 | Dockerfile 멀티스테이지 빌드 + HEALTHCHECK 추가 | Docker | 2시간 |
| 4 | `entrypoint.sh`에서 `--reload` 제거 (프로덕션 분기) | Docker | 30분 |
| 5 | `slowapi` Rate Limiting 추가 | Auth | 2시간 |
| 6 | 감사 로그 테이블 + 마이그레이션 003 생성 | Auth | 1시간 |

### Phase 2 — MLOps 기반 구축 (2주 내)

| # | 작업 | 담당 관점 | 예상 시간 |
|---|------|-----------|-----------|
| 7 | MLflow 서버 docker-compose에 추가 | MLOps | 2시간 |
| 8 | PuCo_RL 학습 코드에 MLflow 로깅 통합 | MLOps | 4시간 |
| 9 | DVC로 모델 파일 버전 관리 | MLOps | 2시간 |
| 10 | JWT 토큰 무효화 (Redis Blocklist) | Auth | 3시간 |
| 11 | 로그아웃 / 회원탈퇴 엔드포인트 | Auth | 2시간 |

### Phase 3 — AWS 배포 (1달 내)

| # | 작업 | 담당 관점 | 예상 시간 |
|---|------|-----------|-----------|
| 12 | AWS 계정 설정 + ECR 저장소 생성 | AWS Serverless | 1시간 |
| 13 | Terraform으로 VPC + RDS + ElastiCache 프로비저닝 | AWS Serverless | 1일 |
| 14 | GitHub Actions CI/CD 파이프라인 구축 | AWS Serverless | 4시간 |
| 15 | ECS Fargate Task Definition + Service 생성 | AWS Serverless | 4시간 |
| 16 | CloudFront + WAF 설정 | AWS Serverless | 3시간 |
| 17 | CloudWatch 알람 + 대시보드 구성 | AWS Serverless | 2시간 |

### Phase 4 — 자동화 (2달 내)

| # | 작업 | 담당 관점 | 예상 시간 |
|---|------|-----------|-----------|
| 18 | game_logs 기반 자동 재학습 트리거 | MLOps | 1일 |
| 19 | 모델 Hot-Reload 엔드포인트 | MLOps | 4시간 |
| 20 | RL 학습 데이터 → S3 자동 업로드 | AWS + MLOps | 3시간 |
| 21 | 학습용 ECS/Batch Job 설정 | AWS + MLOps | 1일 |

---

## 결론

현재 코드베이스는 **게임 로직과 데이터 수집 파이프라인이 탄탄하게 구현**되어 있으며,
이번 세션에서 Google OAuth 인증, 보안 강화, lint 품질 개선이 완료되었습니다.

**가장 시급한 작업은 Phase 1** — 특히:
1. **Docker 경량화** (PyTorch 분리) → 이미지 크기 5.5GB → 400MB
2. **Rate Limiting** → 현재 DoS 무방어 상태

이 두 가지만 완료해도 프로덕션 배포 준비도가 크게 향상됩니다.

---

*이 보고서는 MLOps Engineer · Auth Implementation Patterns · Docker Expert · AWS Serverless 관점에서 자동 생성되었습니다.*

---

## 7. 데이터 검증 로직 테스트 결과

> **분석 범위:** `backend/app/services/ml_logger.py`, `backend/app/engine_wrapper/wrapper.py`, `backend/app/api/v1/game.py`, `backend/app/schemas/game.py`, `backend/tests/`

### 7-1. 파일별 검증 로직 현황

#### `services/ml_logger.py` — ❌ 검증 없음

```
검증 패턴 탐색 결과:
  isinstance(...)   : 0건
  raise ValueError  : 0건
  field_validator   : 0건
  if ... is None    : 0건 (필수 필드 검사 전무)
```

`MLLogger`는 `game_id`, `state_before`, `action`, `action_mask`, `state_after`를 받아 PostgreSQL과 JSONL 파일에 기록하지만, **타입 힌트만 존재하며 런타임 검증이 전혀 없습니다.**

실제 코드 흐름:
```python
# ml_logger.py (현재)
async def log_transition(
    self,
    game_id: str,          # 타입 힌트만, UUID 형식 검증 없음
    state_before: dict,    # 타입 힌트만, 필수 키 검증 없음
    action: int,           # 타입 힌트만, 범위 검증 없음
    action_mask: list,     # 타입 힌트만, 길이/값 검증 없음
    state_after: dict,     # 타입 힌트만, 필수 키 검증 없음
) -> None:
    # 즉시 DB 삽입 — 검증 없음
    db.add(GameLog(...))
```

**위험:** 손상된 데이터가 `game_logs`에 저장되면 PPO 학습 시 발견하기 어렵습니다.

---

#### `engine_wrapper/wrapper.py` — ⚠️ 부분 검증 (numpy 타입 정규화만)

```
isinstance 검사: 6건
  - np.integer → int 변환
  - np.floating → float 변환
  - np.ndarray → list 변환
  - np.bool_ → bool 변환
```

numpy 직렬화 타입을 Python 기본 타입으로 변환하는 것에 집중합니다. **비즈니스 로직 검증(필수 키 존재 여부, 값 범위)은 없습니다.**

---

#### `api/v1/game.py` — ✅ 액션 마스크 검증 있음

```python
# game_service.py에서 호출되는 검증 (3건의 raise ValueError)
def step(self, action: int) -> dict:
    mask = self.get_action_mask()

    if not (0 <= action < len(mask)):          # 범위 검사
        raise ValueError(f"액션 {action}이 마스크 범위를 벗어남 (크기: {len(mask)})")

    if mask[action] != 1:                      # 유효성 검사
        raise ValueError(f"액션 {action}은 현재 허용되지 않음 (마스크 값: {mask[action]})")
```

게임 액션에 대한 가장 중요한 검증이며, 이는 치팅 방지에도 직접 기여합니다.

---

#### `schemas/game.py` — ⚠️ Pydantic 타입만, 커스텀 검증 없음

```python
class GameActionRequest(BaseModel):
    action: int            # 타입 검증만 (정수인지)
    game_id: str           # 타입 검증만 (문자열인지)
    # UUID 형식 검증 없음, action 범위 검증 없음
```

API 경계에서 Pydantic이 기본 타입을 강제하지만 도메인 규칙 검증은 없습니다.

---

#### 기존 테스트 (`tests/`) — ✅ 구조 검증 테스트 존재

| 파일 | 테스트 수 | 검증 내용 |
|------|-----------|-----------|
| `test_db_schema.py` | 15건 | JSONB 컬럼 구조, 필수 키 존재 여부 |
| `test_game_action.py` | 8건 | action_mask가 0/1 리스트인지 확인 |
| `test_ws_disconnect.py` | 5건 | WebSocket 연결 해제 동작 |
| `test_redis_service.py` | 6건 | Redis 키 TTL, Pub/Sub 동작 |
| `test_health_endpoint.py` | 3건 | `/health` 응답 코드 |

**누락된 테스트:**
- `ml_logger.py` 입력 검증 테스트 (0건)
- 잘못된 `state_before` 딕셔너리 구조로 로깅 시도 테스트
- 음수 또는 범위 초과 `action` 값으로 로깅 시도 테스트
- PPO 학습에 필요한 필수 키(`role`, `phase`, `goods_supply` 등)의 존재 여부 테스트

### 7-2. 검증 개선 권고안

#### 즉시 추가 (Priority: HIGH) — `ml_logger.py`에 입력 검증 추가

```python
# backend/app/services/ml_logger.py
import uuid

_REQUIRED_STATE_KEYS = {"phase", "role", "players", "goods_supply", "action_mask"}

def _validate_transition(
    game_id: str,
    state_before: dict,
    action: int,
    action_mask: list[int],
    state_after: dict,
) -> None:
    """PPO 학습에 필요한 데이터 무결성 검증."""
    # game_id: UUID 형식
    try:
        uuid.UUID(game_id)
    except ValueError:
        raise ValueError(f"game_id가 유효한 UUID가 아닙니다: {game_id!r}")

    # action_mask: 0/1 값의 리스트, 비어있지 않음
    if not action_mask or not all(v in (0, 1) for v in action_mask):
        raise ValueError(f"action_mask가 유효하지 않습니다: {action_mask}")

    # action: action_mask 범위 내, 허용된 값
    if not (0 <= action < len(action_mask)):
        raise ValueError(f"action={action}이 action_mask 범위를 벗어남")
    if action_mask[action] != 1:
        raise ValueError(f"action={action}은 마스크에서 허용되지 않음")

    # state_before / state_after: 필수 키 존재
    for key in _REQUIRED_STATE_KEYS:
        if key not in state_before:
            raise ValueError(f"state_before에 필수 키 누락: {key!r}")
        if key not in state_after:
            raise ValueError(f"state_after에 필수 키 누락: {key!r}")
```

#### 중기 개선 (Priority: MEDIUM) — Pydantic 모델로 상태 구조 정의

```python
# backend/app/schemas/game_state.py (신규)
from pydantic import BaseModel, field_validator

class GameStateSnapshot(BaseModel):
    phase: str
    role: str | None
    players: list[dict]
    goods_supply: dict[str, int]
    action_mask: list[int]

    @field_validator("action_mask")
    @classmethod
    def validate_mask(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("action_mask는 비어있을 수 없습니다")
        if not all(bit in (0, 1) for bit in v):
            raise ValueError("action_mask는 0과 1만 포함해야 합니다")
        return v

    @field_validator("goods_supply")
    @classmethod
    def validate_goods(cls, v: dict) -> dict:
        if any(qty < 0 for qty in v.values()):
            raise ValueError("goods_supply 수량은 음수일 수 없습니다")
        return v
```

---

## 8. 인증키 생성 가이드

> **대상:** `castone/.env` 파일에 설정해야 할 모든 보안 키

### 8-1. 현재 필수 환경변수

`castone/backend/app/core/security.py`와 `dependencies.py`에서 없으면 `RuntimeError`를 발생시키는 키:

| 변수 | 사용처 | 없을 시 동작 |
|------|--------|-------------|
| `SECRET_KEY` | JWT 서명 (HS256) | **서버 시작 실패** |
| `DATABASE_URL` | PostgreSQL 연결 | **서버 시작 실패** |
| `GOOGLE_CLIENT_ID` | Google id_token 검증 | `POST /auth/google` → 503 오류 |

### 8-2. 키 생성 방법

#### SECRET_KEY — JWT 서명용 (64바이트 16진수)

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(64))"
# 출력 예시:
# SECRET_KEY=a3f8c2d1e4b7...  (128자 hex 문자열)
```

또는 OpenSSL 사용:
```bash
echo "SECRET_KEY=$(openssl rand -hex 64)"
```

**주의:** 이 값이 노출되면 공격자가 임의의 JWT 토큰을 발급할 수 있습니다. `.env` 파일을 절대 git에 커밋하지 마세요.

#### DATABASE_URL 비밀번호 변경 (선택적이지만 권장)

현재 docker-compose 기본값 `puco_password`는 프로덕션에서 사용하면 안 됩니다.

```bash
# 강력한 DB 비밀번호 생성
python3 -c "import secrets; print('PUCO_DB_PASSWORD=' + secrets.token_urlsafe(32))"
```

생성된 비밀번호를 `.env`와 `docker-compose.yml`에 모두 반영:
```env
# .env
DATABASE_URL=postgresql://puco_user:NEW_STRONG_PASSWORD@db:5432/puco_rl
```

```yaml
# docker-compose.yml
db:
  environment:
    POSTGRES_PASSWORD: NEW_STRONG_PASSWORD  # .env에서 읽어오도록 변경 권장
```

#### Redis 비밀번호 (현재 없음 → 추가 권장)

```bash
python3 -c "import secrets; print('REDIS_PASSWORD=' + secrets.token_urlsafe(24))"
```

`docker-compose.yml`에 Redis 인증 추가:
```yaml
redis:
  command: redis-server --requirepass ${REDIS_PASSWORD}
  environment:
    - REDIS_PASSWORD=${REDIS_PASSWORD}
```

`REDIS_URL`도 업데이트:
```env
REDIS_URL=redis://:YOUR_REDIS_PASSWORD@redis:6379/0
```

### 8-3. GOOGLE_CLIENT_ID 발급 방법

1. **Google Cloud Console** 접속: [console.cloud.google.com](https://console.cloud.google.com)
2. **프로젝트 선택** 또는 새 프로젝트 생성
3. **API 및 서비스 → 사용자 인증 정보** 메뉴 이동
4. **사용자 인증 정보 만들기 → OAuth 클라이언트 ID** 선택
5. **애플리케이션 유형**: "웹 애플리케이션" 선택
6. **승인된 JavaScript 출처** 추가:
   - 로컬 개발: `http://localhost:3000`
   - 프로덕션: `https://yourdomain.com`
7. 생성 후 나타나는 **클라이언트 ID**를 복사

```env
# .env
GOOGLE_CLIENT_ID=123456789-abcdefghijk.apps.googleusercontent.com
```

**주의:** `client_secret`은 백엔드에서 필요 없습니다 (프론트엔드 → id_token → 백엔드 검증 방식이기 때문).

### 8-4. 완성된 `.env` 파일 예시

```env
# ── 생성 명령어로 만든 실제 값으로 교체 필수 ──

# JWT 서명 키 (python3 -c "import secrets; print(secrets.token_hex(64))")
SECRET_KEY=여기에_128자리_hex_문자열

# Database
DATABASE_URL=postgresql://puco_user:여기에_강력한_비밀번호@db:5432/puco_rl

# Redis
REDIS_URL=redis://redis:6379/0
# Redis 비밀번호 추가 시:
# REDIS_PASSWORD=여기에_비밀번호
# REDIS_URL=redis://:여기에_비밀번호@redis:6379/0

# Google OAuth (Google Cloud Console에서 발급)
GOOGLE_CLIENT_ID=123456789-xxxxx.apps.googleusercontent.com

# 개발 환경에서만 true
DEBUG=false

# PPO 모델 파일명 (PuCo_RL/models/ 내)
PPO_MODEL_FILENAME=ppo_agent_update_100.pth
```

### 8-5. 보안 점검 체크리스트

- [ ] `.env` 파일이 `.gitignore`에 포함되어 있는가?
- [ ] `SECRET_KEY`가 최소 64바이트(128자 hex) 이상인가?
- [ ] `puco_password` 기본값을 변경했는가?
- [ ] `DEBUG=false` (프로덕션 배포 시)
- [ ] `GOOGLE_CLIENT_ID`가 실제 값으로 교체되었는가?
- [ ] AWS 배포 시 Secrets Manager에 모든 키를 이전했는가?

---

## 9. PPO 데이터 전처리 파이프라인 설계

> **목표:** `game_logs` (PostgreSQL JSONB) 및 JSONL 파일에 저장된 원시 게임 전환 데이터를 PPO 학습에 적합한 텐서 형태로 변환하는 전체 파이프라인 설계

### 9-1. 원시 데이터 구조 (입력)

```
game_logs 테이블 한 행 =
{
  "state_before": {
    "phase": "mayor",
    "role": "mayor",
    "round": 3,
    "players": [
      {"name": "p0", "goods": {"corn": 2, "indigo": 1}, "colonists": 3, "vp": 5},
      ...
    ],
    "goods_supply": {"corn": 10, "indigo": 8, ...},
    "colonist_supply": 15,
    "action_mask": [0, 1, 0, 0, 1, ...]   # len = NUM_ACTIONS (e.g., 200)
  },
  "action": 42,                             # 선택된 액션 인덱스
  "action_mask": [0, 1, 0, ...],           # 중복 저장 (빠른 조회용)
  "state_after": { ... },                   # state_before와 동일 구조
  "reward": 0.0                             # 현재는 0 (즉시 보상 없음)
}
```

### 9-2. 전처리 파이프라인 전체 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 0: 데이터 소스                                            │
│                                                                  │
│  [PostgreSQL: game_logs]    [JSONL: /data/logs/*.jsonl]         │
│        │ JSONB                        │ JSON Lines              │
│        └──────────────┬───────────────┘                         │
│                       │                                          │
│                       ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  STAGE 1: 데이터 로드 & 기본 정제                        │    │
│  │                                                          │    │
│  │  • DB 쿼리: game_logs WHERE game_id IN (완료된 게임들)   │    │
│  │  • 중복 제거: (game_id, round, step) 복합 키 기준        │    │
│  │  • 누락값 필터: state_before/state_after None 행 제거    │    │
│  │  • action_mask 검증: 모두 0인 마스크 행 제거             │    │
│  │                                                          │    │
│  │  출력: List[RawTransition]  ~N행                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                       │                                          │
│                       ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  STAGE 2: 피처 추출 (Feature Extraction)                 │    │
│  │                                                          │    │
│  │  state_dict → 고정 길이 수치 벡터                        │    │
│  │                                                          │    │
│  │  ① 플레이어 피처 (자신 기준, 상대방 상대적 차이)         │    │
│  │     • goods: [corn, indigo, sugar, tobacco, coffee]     │    │
│  │     • colonists, vp, buildings_count                    │    │
│  │     • relative_vp = my_vp - mean(others_vp)             │    │
│  │                                                          │    │
│  │  ② 공급 피처                                             │    │
│  │     • goods_supply[각 상품] / 초기 공급량 (정규화)       │    │
│  │     • colonist_supply / 총 식민지 수                     │    │
│  │     • vp_supply / 총 VP 수                              │    │
│  │                                                          │    │
│  │  ③ 게임 진행 피처                                        │    │
│  │     • round / MAX_ROUNDS (0~1 정규화)                   │    │
│  │     • phase_onehot [8개 phase → 8차원 one-hot]          │    │
│  │     • role_onehot  [7개 role → 7차원 one-hot]           │    │
│  │                                                          │    │
│  │  출력 벡터 크기: ~120차원                                 │    │
│  └─────────────────────────────────────────────────────────┘    │
│                       │                                          │
│                       ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  STAGE 3: 정규화 (Normalization)                         │    │
│  │                                                          │    │
│  │  • 연속형 피처: Running Mean/Std 정규화                   │    │
│  │    z = (x - mean) / (std + 1e-8)                        │    │
│  │                                                          │    │
│  │  • clip: [-5, 5] 범위로 outlier 제거                    │    │
│  │                                                          │    │
│  │  • 통계 저장: normalizer_stats.npz (학습/추론 공유)      │    │
│  │                                                          │    │
│  │  주의: one-hot 피처는 정규화 제외                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                       │                                          │
│                       ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  STAGE 4: 보상 계산 (Reward Shaping)                     │    │
│  │                                                          │    │
│  │  현재: reward = 0.0 (즉시 보상 없음)                     │    │
│  │  → PPO는 에피소드 종료 시 역전파가 필요                   │    │
│  │                                                          │    │
│  │  권장 보상 설계:                                          │    │
│  │  ① 즉시 보상 (step reward):                             │    │
│  │     r_step = Δvp (이번 액션으로 획득한 VP 변화)          │    │
│  │                                                          │    │
│  │  ② 에피소드 종료 보상 (terminal reward):                 │    │
│  │     r_terminal = +1.0 (승리) / -1.0 (패배) / 0.0 (무승부)│   │
│  │                                                          │    │
│  │  ③ GAE (Generalized Advantage Estimation):              │    │
│  │     A_t = Σ (γλ)^k * δ_{t+k}   (γ=0.99, λ=0.95)       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                       │                                          │
│                       ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  STAGE 5: 텐서 변환 & 배치 준비                           │    │
│  │                                                          │    │
│  │  PPOBatch = {                                            │    │
│  │    "obs":         FloatTensor [B, 120]    # 관찰 벡터   │    │
│  │    "actions":     LongTensor  [B]         # 선택한 액션  │    │
│  │    "action_mask": BoolTensor  [B, 200]    # 유효 액션   │    │
│  │    "log_probs":   FloatTensor [B]         # π_old(a|s)  │    │
│  │    "values":      FloatTensor [B]         # V(s) 추정값 │    │
│  │    "advantages":  FloatTensor [B]         # GAE A_t     │    │
│  │    "returns":     FloatTensor [B]         # G_t 수익    │    │
│  │  }                                                       │    │
│  │                                                          │    │
│  │  배치 크기: B = 512 ~ 2048 (GPU 메모리에 따라)            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                       │                                          │
│                       ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  STAGE 6: PPO 학습 루프                                   │    │
│  │                                                          │    │
│  │  for epoch in range(K):          # K=4~10 미니배치 에포크│    │
│  │    for minibatch in rollout:                             │    │
│  │      ratio = exp(log_prob - log_prob_old)               │    │
│  │      clip_obj = min(ratio * A, clip(ratio, 1±ε) * A)   │    │
│  │      value_loss = MSE(V(s), returns)                    │    │
│  │      entropy_bonus = -Σ π(a|s) log π(a|s)              │    │
│  │      loss = -clip_obj + c1*value_loss - c2*entropy     │    │
│  │      optimizer.step()                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 9-3. 구현 파일 구조 (권장)

```
PuCo_RL/
├── data_pipeline/
│   ├── __init__.py
│   ├── loader.py           # Stage 1: DB/JSONL 로드, 정제
│   ├── feature_extractor.py # Stage 2: state_dict → 수치 벡터
│   ├── normalizer.py        # Stage 3: 정규화 통계 관리
│   ├── reward_shaper.py     # Stage 4: 보상 계산 / GAE
│   ├── dataset.py           # Stage 5: PyTorch Dataset 구현
│   └── pipeline.py          # 전체 파이프라인 오케스트레이터
├── training/
│   ├── ppo_trainer.py       # Stage 6: PPO 학습 루프
│   └── config.py            # 하이퍼파라미터 설정
└── tests/
    ├── test_feature_extractor.py
    ├── test_normalizer.py
    └── test_reward_shaper.py
```

### 9-4. 핵심 구현 코드 스니펫

```python
# PuCo_RL/data_pipeline/feature_extractor.py

import numpy as np
from configs.constants import Phase, Role

NUM_PHASES = len(Phase)
NUM_ROLES  = len(Role)
GOODS_KEYS = ["corn", "indigo", "sugar", "tobacco", "coffee"]

def extract_features(state: dict, player_idx: int = 0) -> np.ndarray:
    """
    game_logs의 state_before/state_after dict를 고정 길이 numpy 배열로 변환.
    출력: float32 배열, 크기 ~120
    """
    players = state["players"]
    me = players[player_idx]
    others = [p for i, p in enumerate(players) if i != player_idx]

    # ① 자신의 재화 (5차원)
    my_goods = np.array([me["goods"].get(g, 0) for g in GOODS_KEYS], dtype=np.float32)

    # ② 자신의 통계 (3차원)
    my_stats = np.array([me["colonists"], me["vp"], len(me.get("buildings", []))], dtype=np.float32)

    # ③ 상대 대비 상대적 VP (1차원)
    rel_vp = np.array([me["vp"] - np.mean([p["vp"] for p in others])], dtype=np.float32)

    # ④ 공급 정규화 (6차원)
    supply = state["goods_supply"]
    supply_vec = np.array([supply.get(g, 0) / 100.0 for g in GOODS_KEYS] +
                          [state.get("colonist_supply", 0) / 50.0], dtype=np.float32)

    # ⑤ 게임 진행 (1차원)
    round_norm = np.array([state.get("round", 0) / 15.0], dtype=np.float32)

    # ⑥ Phase one-hot (NUM_PHASES차원)
    phase_onehot = np.zeros(NUM_PHASES, dtype=np.float32)
    try:
        phase_onehot[Phase[state["phase"]].value] = 1.0
    except (KeyError, IndexError):
        pass

    # ⑦ Role one-hot (NUM_ROLES차원)
    role_onehot = np.zeros(NUM_ROLES, dtype=np.float32)
    if state.get("role"):
        try:
            role_onehot[Role[state["role"]].value] = 1.0
        except (KeyError, IndexError):
            pass

    return np.concatenate([
        my_goods, my_stats, rel_vp, supply_vec, round_norm,
        phase_onehot, role_onehot
    ])
```

```python
# PuCo_RL/data_pipeline/dataset.py

import torch
from torch.utils.data import Dataset

class PPOTransitionDataset(Dataset):
    def __init__(self, transitions: list[dict], feature_extractor, normalizer):
        self.obs        = []
        self.actions    = []
        self.masks      = []
        self.advantages = []
        self.returns    = []
        self.log_probs  = []

        for t in transitions:
            obs = feature_extractor(t["state_before"])
            obs = normalizer.normalize(obs)

            self.obs.append(torch.tensor(obs, dtype=torch.float32))
            self.actions.append(torch.tensor(t["action"], dtype=torch.long))
            self.masks.append(torch.tensor(t["action_mask"], dtype=torch.bool))
            self.advantages.append(torch.tensor(t["advantage"], dtype=torch.float32))
            self.returns.append(torch.tensor(t["return"], dtype=torch.float32))
            self.log_probs.append(torch.tensor(t["log_prob"], dtype=torch.float32))

    def __len__(self): return len(self.obs)

    def __getitem__(self, idx):
        return {
            "obs":        self.obs[idx],
            "action":     self.actions[idx],
            "mask":       self.masks[idx],
            "advantage":  self.advantages[idx],
            "return":     self.returns[idx],
            "log_prob":   self.log_probs[idx],
        }
```

### 9-5. 단계별 구현 우선순위

| 단계 | 작업 | 우선순위 | 선행 조건 |
|------|------|---------|----------|
| Stage 1 | `loader.py` — DB/JSONL 로드 | 즉시 | `game_logs` 데이터 축적 필요 |
| Stage 2 | `feature_extractor.py` | 즉시 | Puerto Rico 도메인 지식 |
| Stage 3 | `normalizer.py` | 높음 | Stage 2 완료 |
| Stage 4 | `reward_shaper.py` + GAE | 높음 | 게임 승패 판정 로직 |
| Stage 5 | `dataset.py` (PyTorch) | 중간 | Stage 1~4 완료 |
| Stage 6 | `ppo_trainer.py` 통합 | 중간 | Stage 5 완료 |

> **참고:** 현재 `bot_service.py`의 PPO 에이전트는 온라인 학습 없이 사전 학습된 `.pth` 파일만 사용합니다. 위 파이프라인은 **오프라인 배치 재학습** 시나리오를 위한 것으로, 충분한 게임 데이터(최소 1,000~10,000 에피소드)가 축적된 후에 실행합니다.

---

*이 보고서는 MLOps Engineer · Auth Implementation Patterns · Docker Expert · AWS Serverless 관점에서 자동 생성되었습니다.*
