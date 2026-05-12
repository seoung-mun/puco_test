# AWS 단일 EC2 운영 런북

**대상 인프라**: AWS t3.medium, Ubuntu 22.04 LTS, Seoul (ap-northeast-2)  
**작성일**: 2026-05-12  
**적용 범위**: 백엔드 단일 EC2 + Vercel 프론트엔드 구성  
**보안그룹**: 22(SSH), 80(HTTP)만 외부 개방 / 8000 포트는 내부 전용

> 이 런북만 보고 제3자가 신규 EC2를 기동할 수 있어야 합니다.  
> 모든 명령은 복사-붙여넣기 후 그대로 실행 가능합니다.

---

## 목차

1. [EC2 초기 부트스트랩](#1-ec2-초기-부트스트랩)
2. [코드 가져오기](#2-코드-가져오기)
3. [`.env` 작성 가이드](#3-env-작성-가이드)
4. [서비스 기동](#4-서비스-기동)
5. [헬스 확인](#5-헬스-확인)
6. [Vercel `VITE_API_TARGET` 교체](#6-vercel-vite_api_target-교체)
7. [AWS 리소스 폐기 체크리스트](#7-aws-리소스-폐기-체크리스트)
8. [롤백 시나리오](#8-롤백-시나리오)
9. [일상 운영](#9-일상-운영)
10. [분석 CLI 사용법](#10-분석-cli-사용법)

---

## 1. EC2 초기 부트스트랩

EC2 인스턴스에 최초 SSH 접속 직후 한 번만 실행합니다.

### 1.1 시스템 패키지 업데이트

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

### 1.2 Docker 설치 (공식 apt 저장소)

```bash
# 의존 패키지 설치
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# Docker 공식 GPG 키 추가
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Docker apt 저장소 등록
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker Engine + Compose Plugin 설치
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

### 1.3 현재 사용자를 docker 그룹에 추가

```bash
sudo usermod -aG docker ubuntu
# 그룹 변경 적용 (재로그인 없이)
newgrp docker
```

### 1.4 Git 설치

```bash
sudo apt-get install -y git
```

### 1.5 설치 확인

```bash
docker --version
docker compose version
git --version
```

예상 출력:
```
Docker version 26.x.x, build ...
Docker Compose version v2.x.x
git version 2.x.x
```

---

## 2. 코드 가져오기

```bash
# /opt/castone 에 prod 브랜치 클론
sudo git clone -b prod https://github.com/seoung-mun/puco_test.git /opt/castone

# 소유권을 ubuntu 유저로 변경
sudo chown -R ubuntu:ubuntu /opt/castone

# 클론 확인
ls /opt/castone
```

이후 모든 명령은 `/opt/castone` 에서 실행합니다.

```bash
cd /opt/castone
```

---

## 3. `.env` 작성 가이드

`.env.example`을 복사한 뒤 실제 값으로 채웁니다.

```bash
cp /opt/castone/.env.example /opt/castone/.env
```

편집기로 열어서 아래 항목을 채웁니다.

```bash
nano /opt/castone/.env
```

### 3.1 필수 교체 항목

| 변수 | 설명 | 생성 명령 |
|------|------|-----------|
| `POSTGRES_PASSWORD` | PostgreSQL 비밀번호 (강력한 난수) | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DATABASE_URL` | `POSTGRES_PASSWORD`와 동일 값으로 갱신 | — |
| `REDIS_PASSWORD` | Redis 비밀번호 (강력한 난수) | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `REDIS_URL` | `REDIS_PASSWORD`와 동일 값으로 갱신 | — |
| `SECRET_KEY` | JWT 서명 키 (64자 hex) | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `INTERNAL_API_KEY` | 내부 API 키 (64자 hex) | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `VITE_INTERNAL_API_KEY` | `INTERNAL_API_KEY`와 동일 값 | — |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID | Google Cloud Console |
| `VITE_GOOGLE_CLIENT_ID` | `GOOGLE_CLIENT_ID`와 동일 값 | — |
| `ALLOWED_ORIGINS` | Vercel 프론트엔드 도메인 (예: `https://puco-test.vercel.app`) | — |

### 3.2 프로덕션 고정 값 확인

아래 항목은 그대로 두거나 주석을 참고해서 유지합니다.

```bash
# .env 에서 반드시 이 값이어야 함
DEBUG=false
REPLAY_STORAGE_BACKEND=db
MODEL_TYPE=ppo
PPO_BUNDLE_DIR=ppo-pr-server-semantic293-20260419
```

### 3.3 작성 완료 후 확인

```bash
# 비밀번호/시크릿에 "change-me" 문자열이 남아 있는지 확인 (0건이어야 함)
grep "change-me" /opt/castone/.env && echo "WARNING: 미교체 항목 있음" || echo "OK"
```

---

## 4. 서비스 기동

```bash
cd /opt/castone
docker compose -f docker-compose.prod.yml up -d --build
```

최초 빌드는 5-10분 소요됩니다. 빌드 로그를 보려면 `-d` 없이 실행하세요.

```bash
# 빌드 로그 확인하면서 기동 (포그라운드, Ctrl+C로 종료 후 백그라운드로 재기동)
docker compose -f docker-compose.prod.yml up --build
```

---

## 5. 헬스 확인

### 5.1 컨테이너 상태 확인

```bash
docker compose -f docker-compose.prod.yml ps
```

모든 서비스가 `healthy` 상태여야 합니다.

```
NAME            IMAGE              STATUS                    PORTS
puco_db         postgres:16-alpine Up X minutes (healthy)
puco_redis      redis:7-alpine     Up X minutes (healthy)
puco_backend    castone-backend    Up X minutes (healthy)
```

### 5.2 백엔드 헬스 엔드포인트 확인

```bash
docker compose -f docker-compose.prod.yml exec backend curl -f http://127.0.0.1:8000/health
```

예상 응답 (HTTP 200):

```json
{"status": "ok"}
```

### 5.3 외부에서 HTTP 확인 (EC2 퍼블릭 IP로)

EC2 인스턴스의 퍼블릭 IP를 확인합니다.

```bash
curl -s http://169.254.169.254/latest/meta-data/public-ipv4
```

로컬 머신 또는 별도 터미널에서:

```bash
curl -f http://<EC2_PUBLIC_IP>/health
```

> 80번 포트는 Nginx(컨테이너 내)가 /health 요청을 백엔드 8000으로 프록시합니다.

### 5.4 Alembic 마이그레이션 확인 (최초 기동 시)

```bash
docker compose -f docker-compose.prod.yml exec backend alembic current
```

마이그레이션이 자동 적용됐는지 확인합니다. `head`에 있어야 합니다.

---

## 6. Vercel `VITE_API_TARGET` 교체

프론트엔드는 Vercel에서 서빙됩니다. 백엔드 URL을 EC2로 변경해야 합니다.

### 6.1 EC2 퍼블릭 IP 또는 도메인 확인

```bash
curl -s http://169.254.169.254/latest/meta-data/public-ipv4
```

도메인이 있다면 해당 도메인(예: `api.puco-test.com`)을 사용합니다.

### 6.2 Vercel 환경변수 업데이트

1. [Vercel 대시보드](https://vercel.com/dashboard) 접속
2. 해당 프로젝트(puco-test) 선택
3. **Settings** → **Environment Variables** 이동
4. `VITE_API_TARGET` 항목 찾아서 값 수정:

   ```
   http://<EC2_PUBLIC_IP>
   ```
   또는 도메인이 있다면:
   ```
   https://api.puco-test.com
   ```

5. `VITE_BACKEND_ORIGIN`도 동일 값으로 업데이트

### 6.3 Vercel 재배포

환경변수 저장 후 재배포를 트리거합니다.

```bash
# Vercel CLI가 설치돼 있다면
vercel --prod

# 또는 Vercel 대시보드에서:
# Deployments 탭 → 최근 배포 우클릭 → Redeploy
```

### 6.4 연결 확인

Vercel 도메인으로 접속해서 Google 로그인 및 게임 로비 진입이 되면 성공입니다.

---

## 7. AWS 리소스 폐기 체크리스트

EC2 기동 및 Vercel 연결이 검증된 뒤 기존 AWS 관리형 리소스를 폐기합니다.  
**순서를 지켜야 의존성 오류 없이 삭제 가능합니다.**

> 주의: RDS, ElastiCache 데이터는 복구 불가합니다. 폐기 전 스냅샷이 필요하다면 콘솔에서 먼저 생성하세요.

### 7.1 ECS 서비스 및 클러스터 삭제

1. AWS 콘솔 → **ECS** → 해당 클러스터 선택
2. **Services** 탭 → 각 서비스 선택 → **Delete** (desired count를 0으로 줄인 뒤 삭제)
3. 서비스가 모두 삭제된 뒤 **Clusters** → 클러스터 선택 → **Delete Cluster**

### 7.2 ALB (Application Load Balancer) 삭제

1. AWS 콘솔 → **EC2** → **Load Balancers**
2. 해당 ALB 선택 → **Actions** → **Delete**
3. **Target Groups** → 사용하던 Target Group 선택 → **Actions** → **Delete**

### 7.3 RDS 인스턴스 삭제

1. AWS 콘솔 → **RDS** → **Databases**
2. 해당 DB 인스턴스 선택 → **Actions** → **Delete**
3. 팝업에서 **Create final snapshot**: `[ ]` 체크 해제 (데이터 폐기 승인됨)
4. 확인 문구 입력 후 **Delete**

### 7.4 ElastiCache 클러스터 삭제

1. AWS 콘솔 → **ElastiCache** → **Redis clusters**
2. 해당 클러스터 선택 → **Actions** → **Delete**
3. Final backup 생성 여부 → **No** (캐시 데이터 폐기 승인됨)

### 7.5 보안그룹 삭제

의존 리소스가 모두 삭제된 뒤 보안그룹을 삭제합니다.

1. AWS 콘솔 → **EC2** → **Security Groups**
2. 기존 ECS/ALB/RDS/ElastiCache에서 사용하던 보안그룹 선택
3. **Actions** → **Delete security groups**
4. "associated with" 오류가 뜨면 해당 리소스가 아직 남아 있는 것 → 해당 리소스 먼저 삭제

### 7.6 폐기 완료 확인

| 리소스 | 삭제 확인 | 콘솔 경로 |
|--------|-----------|-----------|
| ECS 클러스터 | `[]` | ECS → Clusters |
| ALB | `[]` | EC2 → Load Balancers |
| Target Group | `[]` | EC2 → Target Groups |
| RDS 인스턴스 | `[]` | RDS → Databases |
| ElastiCache | `[]` | ElastiCache → Redis clusters |
| 보안그룹 (구 스택용) | `[]` | EC2 → Security Groups |

---

## 8. 롤백 시나리오

### 8.1 헬스체크 실패 시 진단 절차

#### Step 1: 컨테이너 상태 확인

```bash
docker compose -f docker-compose.prod.yml ps
```

`unhealthy` 또는 `Exit` 상태의 컨테이너를 확인합니다.

#### Step 2: 해당 컨테이너 로그 확인

```bash
# 백엔드 로그 (마지막 100줄)
docker compose -f docker-compose.prod.yml logs --tail=100 backend

# DB 로그
docker compose -f docker-compose.prod.yml logs --tail=50 db

# Redis 로그
docker compose -f docker-compose.prod.yml logs --tail=50 redis
```

#### Step 3: 자주 발생하는 문제와 해결책

**문제 A: `Connection refused` / DB 연결 실패**

```bash
# .env 의 DATABASE_URL 과 POSTGRES_PASSWORD 가 일치하는지 확인
grep "POSTGRES_PASSWORD\|DATABASE_URL" /opt/castone/.env

# DB 컨테이너가 healthy 상태인지 확인
docker compose -f docker-compose.prod.yml ps db
```

**문제 B: Redis 인증 실패**

```bash
# REDIS_PASSWORD 와 REDIS_URL 일치 여부
grep "REDIS_PASSWORD\|REDIS_URL" /opt/castone/.env
```

**문제 C: 포트 80이 응답 없음**

```bash
# 80 포트 리슨 확인
sudo ss -tlnp | grep ':80'

# frontend 컨테이너 상태 확인
docker compose -f docker-compose.prod.yml ps frontend
docker compose -f docker-compose.prod.yml logs --tail=50 frontend
```

**문제 D: 모델 로드 실패 (backend exit)**

```bash
# PPO_BUNDLE_DIR 이 /opt/castone/models 내에 존재하는지 확인
ls /opt/castone/models/
grep "PPO_BUNDLE_DIR" /opt/castone/.env
```

### 8.2 컨테이너 재빌드 후 재기동

```bash
cd /opt/castone

# 컨테이너 내리기
docker compose -f docker-compose.prod.yml down

# 이미지 재빌드 + 기동
docker compose -f docker-compose.prod.yml up -d --build
```

### 8.3 코드 롤백 (이전 커밋으로)

```bash
cd /opt/castone

# 현재 HEAD 확인
git log --oneline -5

# 특정 커밋으로 되돌리기
git checkout <COMMIT_HASH>

# 재빌드 및 재기동
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

### 8.4 .env 문제로 전체 재시작

```bash
cd /opt/castone

# .env 수정
nano /opt/castone/.env

# 컨테이너 전체 재시작 (볼륨 유지)
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

> DB 볼륨(`pgdata`, `redisdata`)은 `down`만 해도 유지됩니다.  
> 볼륨까지 지우려면 `down -v`를 사용하세요 (DB 데이터 전체 삭제).

---

## 9. 일상 운영

### 9.1 로그 보기

```bash
# 전체 서비스 실시간 로그 (Ctrl+C로 종료)
docker compose -f docker-compose.prod.yml logs -f

# 백엔드만 실시간 로그
docker compose -f docker-compose.prod.yml logs -f backend

# 마지막 200줄만
docker compose -f docker-compose.prod.yml logs --tail=200 backend

# 특정 시간 이후 로그
docker compose -f docker-compose.prod.yml logs --since="2026-05-12T00:00:00" backend
```

### 9.2 컨테이너 재시작

```bash
# 백엔드만 재시작
docker compose -f docker-compose.prod.yml restart backend

# 전체 재시작 (DB/Redis 볼륨 유지)
docker compose -f docker-compose.prod.yml restart

# 전체 내리고 다시 올리기
docker compose -f docker-compose.prod.yml down && docker compose -f docker-compose.prod.yml up -d
```

### 9.3 메모리/리소스 모니터

```bash
# 컨테이너별 실시간 리소스 사용량
docker stats

# 특정 컨테이너만
docker stats puco_backend puco_db puco_redis

# 한 번만 출력 (반복 안 함)
docker stats --no-stream
```

### 9.4 디스크 사용량 확인

```bash
# Docker 전체 사용량
docker system df

# EC2 디스크 전체
df -h

# 로그 볼륨 크기
docker compose -f docker-compose.prod.yml exec backend du -sh /data/logs
```

### 9.5 DB 접속 (필요 시)

```bash
# psql 셸 접속
docker compose -f docker-compose.prod.yml exec db \
  psql -U puco_user -d puco_rl

# 직접 쿼리 실행 예시
docker compose -f docker-compose.prod.yml exec db \
  psql -U puco_user -d puco_rl -c "SELECT count(*) FROM game_sessions;"
```

### 9.6 Alembic 마이그레이션 실행

코드 업데이트 후 스키마 변경이 있을 때:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### 9.7 코드 업데이트 (prod 브랜치 최신화)

```bash
cd /opt/castone
git pull origin prod

# 백엔드 이미지 재빌드 및 재기동
docker compose -f docker-compose.prod.yml up -d --build backend
```

---

## 10. 분석 CLI 사용법

> `analytics_cli.py`는 `backend/scripts/analytics_cli.py`에 위치하며,  
> EC2에 SSH 접속 후 백엔드 컨테이너 내부에서 실행합니다.  
> 모든 명령은 **읽기 전용**입니다 (SELECT만 실행, DB 변경 없음).

### 10.1 기본 실행 패턴

```bash
# EC2 SSH 접속 후
ssh ubuntu@<EC2_PUBLIC_IP>

# /opt/castone 로 이동
cd /opt/castone

# analytics_cli 실행 (모든 서브커맨드 동일 패턴)
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli <subcommand> [options]
```

### 10.2 도움말 확인

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli --help

docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli win-rate-by-bot --help
```

### 10.3 Cookbook 예시

#### 예시 1: 최근 활동 사용자 목록 조회

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli list-users
```

예상 출력:
```
UUID                                  닉네임      총게임수  최근게임
------------------------------------  ----------  --------  ----------------------
a1b2c3d4-e5f6-...                     player_kim  42        2026-05-11 23:50:12
b2c3d4e5-f6a7-...                     player_lee  17        2026-05-11 20:31:05
```

#### 예시 2: 봇 종류별 승률 조회

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli win-rate-by-bot \
  --user-id a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

예상 출력:
```
봇 종류      게임수  승리수  승률
-----------  ------  ------  ------
RANDOM       20      14      70.0%
GREEDY       12       6      50.0%
PPO_v2       10       3      30.0%
```

#### 예시 3: 판수 누적별 봇 대상 승률 (5판 단위)

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli win-rate-by-count \
  --user-id a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  --bucket 5
```

예상 출력:
```
판수구간  게임수  승리수  누적승률
--------  ------  ------  --------
1-5       5       4       80.0%
6-10      5       3       70.0%
11-15     5       2       60.0%
16-20     5       3       65.0%
```

#### 예시 4: 최근 게임 결과 조회

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli recent-games \
  --user-id a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  --limit 10
```

예상 출력:
```
게임ID  종료시각              봇종류  판수  결과
------  --------------------  ------  ----  ----
g-001   2026-05-11 23:50:12   PPO_v2  4     패
g-002   2026-05-11 22:15:44   RANDOM  4     승
g-003   2026-05-11 20:31:05   GREEDY  4     승
```

#### 예시 5: JSON 출력 (파일로 저장하거나 jq로 처리)

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli win-rate-by-bot \
  --user-id a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  --json | jq '.'
```

```bash
# 파일로 저장
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli list-users --json \
  > /tmp/users_$(date +%Y%m%d).json
```

### 10.4 user-id 모르는 경우

`list-users`로 먼저 UUID를 확인한 뒤 다른 서브커맨드에 사용합니다.

```bash
# 전체 사용자 UUID 확인
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli list-users

# 특정 닉네임으로 필터 (list-users 결과를 grep)
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli list-users | grep "player_kim"
```

---

## 부록: 빠른 참조

### SSH 접속

```bash
ssh -i /path/to/puco_capstone.pem ubuntu@<EC2_PUBLIC_IP>
```

### 자주 쓰는 명령 모음

```bash
# 상태 확인
docker compose -f docker-compose.prod.yml ps

# 백엔드 헬스
docker compose -f docker-compose.prod.yml exec backend curl -f http://127.0.0.1:8000/health

# 실시간 로그
docker compose -f docker-compose.prod.yml logs -f backend

# 리소스 사용량
docker stats --no-stream

# 전체 재시작
docker compose -f docker-compose.prod.yml restart
```

### 트러블슈팅 빠른 참조

| 증상 | 먼저 확인할 것 | 명령 |
|------|--------------|------|
| 백엔드 unhealthy | 로그 확인 | `docker compose -f docker-compose.prod.yml logs --tail=50 backend` |
| DB 연결 실패 | .env PASSWORD 일치 여부 | `grep POSTGRES /opt/castone/.env` |
| Redis 인증 실패 | .env REDIS_PASSWORD | `grep REDIS /opt/castone/.env` |
| 80 포트 무응답 | frontend 컨테이너 상태 | `docker compose -f docker-compose.prod.yml ps frontend` |
| 메모리 부족 | 전체 메모리 사용량 | `docker stats --no-stream` |
| 디스크 부족 | Docker 레이어/볼륨 | `docker system df` |
