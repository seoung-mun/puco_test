# AWS 단일 EC2 운영 런북

**대상 인프라**: AWS t3.small, 2 vCPU / 2GB RAM, Ubuntu 22.04 LTS, Seoul (ap-northeast-2)
**작성일**: 2026-05-12  
**적용 범위**: 백엔드 단일 EC2 + Vercel 프론트엔드 구성  
**보안그룹**: 22(SSH), 80(HTTP), 443(HTTPS)만 외부 개방 / 8000 포트는 내부 전용

> 이 런북만 보고 제3자가 신규 EC2를 기동할 수 있어야 합니다.  
> 모든 명령은 복사-붙여넣기 후 그대로 실행 가능합니다.
>
> **2GB 원칙**: EC2 안에서 백엔드 이미지를 빌드하지 않습니다. 로컬/CI에서 이미지를 만든 뒤 `docker save` → `scp` → EC2 `docker load`로 올리고, EC2에서는 `docker compose up --no-build`만 실행합니다.

---

## 목차

0. [AWS 콘솔에서 EC2 생성](#0-aws-콘솔에서-ec2-생성)
1. [로컬에서 백엔드 이미지 준비](#1-로컬에서-백엔드-이미지-준비)
2. [EC2 초기 부트스트랩](#2-ec2-초기-부트스트랩)
3. [코드 가져오기](#3-코드-가져오기)
4. [`.env` 작성 가이드](#4-env-작성-가이드)
5. [서비스 기동](#5-서비스-기동)
6. [헬스 확인](#6-헬스-확인)
7. [Vercel `VITE_BACKEND_ORIGIN` 교체](#7-vercel-vite_backend_origin-교체)
8. [AWS 리소스 폐기 체크리스트](#8-aws-리소스-폐기-체크리스트)
9. [롤백 시나리오](#9-롤백-시나리오)
10. [일상 운영](#10-일상-운영)
11. [분석 CLI 사용법](#11-분석-cli-사용법)

---

## 0. AWS 콘솔에서 EC2 생성

AWS 콘솔에서 아래 순서대로 생성합니다.

1. AWS Console → **EC2** → **Instances** → **Launch instances**
2. Name: `puco-prod-backend`
3. Region: `ap-northeast-2` Seoul
4. AMI: **Ubuntu Server 22.04 LTS**, architecture **64-bit (x86)**
5. Instance type: **t3.small** (2 vCPU, 2GB RAM)
6. Key pair: 기존 `.pem` 선택 또는 새 key pair 생성 후 로컬에 저장
7. Network: 기본 VPC 또는 운영 VPC 선택, public subnet 선택, **Auto-assign public IP: Enable**
8. Security group inbound rules:
   - SSH `22/tcp`: 내 현재 IP만 허용
   - HTTP `80/tcp`: `0.0.0.0/0`, `::/0` 허용
   - HTTPS `443/tcp`: `0.0.0.0/0`, `::/0` 허용
   - `8000`, `5432`, `6379`는 외부 공개 금지
9. Storage: gp3 **30GB** 권장 (Docker image + Postgres volume 여유분)
10. Advanced details: IAM role 없음, user data 비움, termination protection은 필요 시 활성화
11. Launch instance
12. EC2 → **Elastic IPs** → Allocate Elastic IP → 생성한 인스턴스에 Associate

SSH 접속은 로컬 터미널에서 실행합니다.

```bash
chmod 400 /path/to/puco_capstone.pem
ssh -i /path/to/puco_capstone.pem ubuntu@<EC2_ELASTIC_IP>
```

---

## 1. 로컬에서 백엔드 이미지 준비

EC2가 2GB이므로 백엔드 이미지는 로컬 머신이나 CI에서 빌드합니다. t3.small은 x86_64이므로 `linux/amd64`로 빌드합니다.

```bash
cd /Users/seoungmun/Documents/agent_dev/castest/castone
git switch prod

# EC2에서 사용할 backend image 생성
docker buildx build \
  --platform linux/amd64 \
  -t castone-backend:prod \
  -f backend/Dockerfile.prod \
  --load .

# tar 파일로 저장
docker save castone-backend:prod \
  -o /tmp/castone-backend-prod-amd64.tar

# EC2로 전송
scp -i /path/to/puco_capstone.pem \
  /tmp/castone-backend-prod-amd64.tar \
  ubuntu@<EC2_ELASTIC_IP>:/tmp/
```

---

## 2. EC2 초기 부트스트랩

EC2 인스턴스에 최초 SSH 접속 직후 한 번만 실행합니다.

### 2.1 시스템 패키지 업데이트

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

### 2.2 Docker 설치 (공식 apt 저장소)

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

### 2.3 현재 사용자를 docker 그룹에 추가

```bash
sudo usermod -aG docker ubuntu
# 그룹 변경 적용 (재로그인 없이)
newgrp docker
```

### 2.4 Git 설치

```bash
sudo apt-get install -y git jq
```

### 2.5 설치 확인

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

## 3. 코드 가져오기

```bash
# /opt/castone 에 운영 브랜치 클론
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

## 4. `.env` 작성 가이드

EC2에는 `.env.example` 대신 슬림한 서버 전용 템플릿인 `.env.ec2.example`을 사용합니다.
이미 로컬에서 잘 쓰고 있는 `.env`가 있다면, 서버에서 손으로 하나씩 다시 입력하지 말고
로컬에서 EC2용 파일을 만든 뒤 업로드하는 방식을 권장합니다.

### 4.0 권장 방식: 로컬 `.env`에서 EC2용 `.env` 생성

```bash
cd /Users/seoungmun/Documents/agent_dev/castest/castone

# 현재 로컬 .env 값을 최대한 가져와서 EC2용 최소 env 생성
python3 backend/scripts/build_ec2_env.py --source .env --output .env.ec2

# 생성된 파일에서 아래 값은 꼭 확인/수정
# - PUBLIC_BACKEND_HOST
# - ALLOWED_ORIGINS
# - BACKEND_IMAGE_TAG
# - GOOGLE_CLIENT_ID

# EC2에 바로 업로드
scp -i /path/to/puco_capstone.pem \
  /Users/seoungmun/Documents/agent_dev/castest/castone/.env.ec2 \
  ubuntu@<EC2_ELASTIC_IP>:/opt/castone/.env
```

### 4.1 대안 방식: EC2에서 템플릿 복사 후 작성

```bash
cp /opt/castone/.env.ec2.example /opt/castone/.env
```

편집기로 열어서 아래 항목을 채웁니다.

```bash
nano /opt/castone/.env
```

### 4.2 필수 교체 항목

| 변수 | 설명 | 생성 명령 |
|------|------|-----------|
| `POSTGRES_PASSWORD` | PostgreSQL 비밀번호 (강력한 난수) | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `REDIS_PASSWORD` | Redis 비밀번호 (강력한 난수) | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SECRET_KEY` | JWT 서명 키 (64자 hex) | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `INTERNAL_API_KEY` | 내부 API 키 (64자 hex) | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID | Google Cloud Console |
| `ALLOWED_ORIGINS` | Vercel 프론트엔드 도메인 (예: `https://puco-test.vercel.app`) | — |
| `BACKEND_IMAGE_TAG` | EC2에 `docker load`한 백엔드 이미지 태그 | `prod` |
| `PUBLIC_BACKEND_HOST` | Caddy가 HTTPS 인증서를 발급받을 공개 백엔드 hostname | `<EC2_PUBLIC_IP>.sslip.io` |

> **ALLOWED_ORIGINS** — Vercel 배포 URL (예: `https://puco-test.vercel.app`). 기본값 `localhost:5173` 은 반드시 Vercel 도메인으로 교체.  
> **VITE_GOOGLE_CLIENT_ID / VITE_INTERNAL_API_KEY** — EC2 `.env` 파일이 아닌 **Vercel 프로젝트 설정 → Environment Variables** 에 설정해야 합니다. Section 7.2 참고.

### 4.3 프로덕션 고정 값 확인

아래 항목은 그대로 두거나 주석을 참고해서 유지합니다.

```bash
# .env 에서 반드시 이 값이어야 함
DEBUG=false
REPLAY_STORAGE_BACKEND=db
BACKEND_IMAGE_TAG=prod
PUBLIC_BACKEND_HOST=<EC2_PUBLIC_IP>.sslip.io
MODEL_TYPE=ppo
PPO_BUNDLE_DIR=ppo-pr-server-semantic293-20260419
```

### 4.4 작성 완료 후 확인

```bash
# 비밀번호/시크릿에 "change-me" 문자열이 남아 있는지 확인 (0건이어야 함)
grep "change-me" /opt/castone/.env && echo "WARNING: 미교체 항목 있음" || echo "OK"
```

---

## 5. 서비스 기동

먼저 로컬에서 전송한 이미지를 EC2 Docker에 로드합니다.

```bash
cd /opt/castone
docker load -i /tmp/castone-backend-prod-amd64.tar
docker image ls castone-backend
```

그 다음 빌드 없이 컨테이너를 기동합니다.

```bash
docker compose -f docker-compose.prod.yml up -d --no-build
```

> t3.small/2GB에서는 `docker compose ... up --build`를 기본 절차로 사용하지 않습니다. 이미지 빌드는 로컬/CI에서 수행하고 EC2는 실행만 담당합니다.

---

## 6. 헬스 확인

### 6.1 컨테이너 상태 확인

```bash
docker compose -f docker-compose.prod.yml ps
```

모든 서비스가 `healthy` 상태여야 합니다.

```
NAME            IMAGE              STATUS                    PORTS
puco_db         postgres:16-alpine Up X minutes (healthy)
puco_redis      redis:7-alpine     Up X minutes (healthy)
puco_backend    castone-backend    Up X minutes (healthy)
puco_caddy      caddy:2-alpine     Up X minutes
```

### 6.2 백엔드 헬스 엔드포인트 확인

```bash
docker compose -f docker-compose.prod.yml exec backend curl -f http://127.0.0.1:8000/health
```

예상 응답 (HTTP 200):

```json
{"status": "ok"}
```

### 6.3 외부에서 HTTPS 확인 (sslip.io hostname으로)

EC2 인스턴스의 퍼블릭 IP를 확인합니다.

```bash
# EC2 퍼블릭 IP 확인 (IMDSv2 방식)
TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
curl -sH "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/public-ipv4

# 또는 외부 서비스 사용 (더 간단)
curl -s ifconfig.me
```

로컬 머신 또는 별도 터미널에서:

```bash
curl -f https://<EC2_PUBLIC_IP>.sslip.io/health
```

> `80`은 Let's Encrypt 인증서 발급/갱신과 HTTP→HTTPS 리다이렉트에 사용됩니다. 실제 Vercel 프론트는 `https://<EC2_PUBLIC_IP>.sslip.io`를 호출해야 합니다.

### 6.4 Alembic 마이그레이션 확인 (최초 기동 시)

```bash
docker compose -f docker-compose.prod.yml exec backend alembic current
```

마이그레이션이 자동 적용됐는지 확인합니다. `head`에 있어야 합니다.

---

## 7. Vercel `VITE_BACKEND_ORIGIN` 교체

프론트엔드는 Vercel에서 서빙됩니다. 백엔드 URL을 EC2로 변경해야 합니다.

### 7.1 EC2 퍼블릭 IP 또는 도메인 확인

```bash
# EC2 퍼블릭 IP 확인 (IMDSv2 방식)
TOKEN=$(curl -sX PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
curl -sH "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/public-ipv4

# 또는 외부 서비스 사용 (더 간단)
curl -s ifconfig.me
```

테스트용 도메인은 `<EC2_PUBLIC_IP>.sslip.io`를 사용합니다. 예: `3.38.63.58.sslip.io`.
개인 도메인이 있다면 해당 도메인(예: `api.puco-test.com`)을 `PUBLIC_BACKEND_HOST`로 사용할 수 있습니다.

### 7.2 Vercel 환경변수 업데이트

1. [Vercel 대시보드](https://vercel.com/dashboard) 접속
2. 해당 프로젝트(puco-test) 선택
3. **Settings** → **Environment Variables** 이동
4. `VITE_BACKEND_ORIGIN` 항목 찾아서 값 수정:

   ```
   https://<EC2_PUBLIC_IP>.sslip.io
   ```
   또는 도메인이 있다면:
   ```
   https://api.puco-test.com
   ```

5. `VITE_GOOGLE_CLIENT_ID` 도 Environment Variables 에 설정 (`.env` EC2 파일이 아닌 Vercel 대시보드에서 설정해야 프론트엔드 빌드에 주입됨)
6. `VITE_INTERNAL_API_KEY` 도 Environment Variables 에 설정 (`INTERNAL_API_KEY` 와 같은 값)

> 현재 프론트엔드는 Vercel에서 `VITE_BACKEND_ORIGIN`, `VITE_GOOGLE_CLIENT_ID`, `VITE_INTERNAL_API_KEY`를 사용합니다. `VITE_API_TARGET`은 더 이상 Vercel 연결 검증 기준으로 사용하지 않습니다. Vercel 페이지가 HTTPS이므로 `VITE_BACKEND_ORIGIN`도 반드시 `https://...`여야 합니다.

### 7.3 Vercel 재배포

환경변수 저장 후 재배포를 트리거합니다.

```bash
# Vercel CLI가 설치돼 있다면
vercel --prod

# 또는 Vercel 대시보드에서:
# Deployments 탭 → 최근 배포 우클릭 → Redeploy
```

### 7.4 연결 확인

Vercel 도메인으로 접속해서 Google 로그인 및 게임 로비 진입이 되면 성공입니다.

---

## 8. AWS 리소스 폐기 체크리스트

EC2 기동 및 Vercel 연결이 검증된 뒤 기존 AWS 관리형 리소스를 폐기합니다.  
**순서를 지켜야 의존성 오류 없이 삭제 가능합니다.**

> 주의: RDS, ElastiCache 데이터는 복구 불가합니다. 폐기 전 스냅샷이 필요하다면 콘솔에서 먼저 생성하세요.

### 8.1 ECS 서비스 및 클러스터 삭제

1. AWS 콘솔 → **ECS** → 해당 클러스터 선택
2. **Services** 탭 → 각 서비스 선택 → **Delete** (desired count를 0으로 줄인 뒤 삭제)
3. 서비스가 모두 삭제된 뒤 **Clusters** → 클러스터 선택 → **Delete Cluster**

### 8.2 ALB (Application Load Balancer) 삭제

1. AWS 콘솔 → **EC2** → **Load Balancers**
2. 해당 ALB 선택 → **Actions** → **Delete**
3. **Target Groups** → 사용하던 Target Group 선택 → **Actions** → **Delete**

### 8.3 RDS 인스턴스 삭제

1. AWS 콘솔 → **RDS** → **Databases**
2. 해당 DB 인스턴스 선택 → **Actions** → **Delete**
3. 팝업에서 **Create final snapshot**: `[ ]` 체크 해제 (데이터 폐기 승인됨)
4. 확인 문구 입력 후 **Delete**

### 8.4 ElastiCache 클러스터 삭제

1. AWS 콘솔 → **ElastiCache** → **Redis clusters**
2. 해당 클러스터 선택 → **Actions** → **Delete**
3. Final backup 생성 여부 → **No** (캐시 데이터 폐기 승인됨)

### 8.5 보안그룹 삭제

의존 리소스가 모두 삭제된 뒤 보안그룹을 삭제합니다.

1. AWS 콘솔 → **EC2** → **Security Groups**
2. 기존 ECS/ALB/RDS/ElastiCache에서 사용하던 보안그룹 선택
3. **Actions** → **Delete security groups**
4. "associated with" 오류가 뜨면 해당 리소스가 아직 남아 있는 것 → 해당 리소스 먼저 삭제

### 8.6 폐기 완료 확인

| 리소스 | 삭제 확인 | 콘솔 경로 |
|--------|-----------|-----------|
| ECS 클러스터 | `[]` | ECS → Clusters |
| ALB | `[]` | EC2 → Load Balancers |
| Target Group | `[]` | EC2 → Target Groups |
| RDS 인스턴스 | `[]` | RDS → Databases |
| ElastiCache | `[]` | ElastiCache → Redis clusters |
| 보안그룹 (구 스택용) | `[]` | EC2 → Security Groups |

---

## 9. 롤백 시나리오

### 9.1 헬스체크 실패 시 진단 절차

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

# backend 컨테이너 상태 확인
docker compose -f docker-compose.prod.yml ps backend
docker compose -f docker-compose.prod.yml logs --tail=50 backend
```

**문제 D: 모델 로드 실패 (backend exit)**

```bash
# PPO_BUNDLE_DIR 이 /opt/castone/models 내에 존재하는지 확인
ls /opt/castone/models/
grep "PPO_BUNDLE_DIR" /opt/castone/.env
```

### 9.2 새 이미지 로드 후 재기동

```bash
cd /opt/castone

# 로컬/CI에서 새로 빌드한 tar를 /tmp로 전송한 뒤 EC2에서 로드
docker load -i /tmp/castone-backend-prod-amd64.tar

# 빌드 없이 새 이미지로 재기동
docker compose -f docker-compose.prod.yml up -d --no-build backend
```

### 9.3 코드 롤백 (이전 커밋으로)

```bash
cd /opt/castone

# 현재 HEAD 확인
git log --oneline -5

# 특정 커밋으로 되돌리기
git checkout <COMMIT_HASH>

# 해당 커밋으로 로컬/CI에서 다시 만든 image tar를 EC2에 전송한 뒤 로드
docker load -i /tmp/castone-backend-rollback-amd64.tar

# 빌드 없이 재기동
docker compose -f docker-compose.prod.yml up -d --no-build backend
```

### 9.4 .env 문제로 전체 재시작

```bash
cd /opt/castone

# .env 수정
nano /opt/castone/.env

# 컨테이너 전체 재시작 (볼륨 유지)
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --no-build
```

> DB 볼륨(`pgdata`, `redisdata`)은 `down`만 해도 유지됩니다.  
> 볼륨까지 지우려면 `down -v`를 사용하세요 (DB 데이터 전체 삭제).

---

## 10. 일상 운영

### 10.0 DB 스냅샷 (배포/변경 전 권장)

```bash
# DB 스냅샷 (배포/변경 전 권장)
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U "${POSTGRES_USER:-puco_user}" puco_rl \
  > /tmp/puco_rl_$(date +%Y%m%d_%H%M%S).sql

# 확인
ls -lh /tmp/puco_rl_*.sql
```

### 10.1 로그 보기

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

### 10.2 컨테이너 재시작

```bash
# 백엔드만 재시작
docker compose -f docker-compose.prod.yml restart backend

# 전체 재시작 (DB/Redis 볼륨 유지)
docker compose -f docker-compose.prod.yml restart

# 전체 내리고 다시 올리기
docker compose -f docker-compose.prod.yml down && docker compose -f docker-compose.prod.yml up -d --no-build
```

### 10.3 메모리/리소스 모니터

```bash
# 컨테이너별 실시간 리소스 사용량
docker stats

# 특정 컨테이너만
docker stats puco_backend puco_db puco_redis

# 한 번만 출력 (반복 안 함)
docker stats --no-stream
```

### 10.4 디스크 사용량 확인

```bash
# Docker 전체 사용량
docker system df

# EC2 디스크 전체
df -h

# 로그 볼륨 크기
docker compose -f docker-compose.prod.yml exec backend du -sh /data/logs
```

### 10.5 DB 접속 (필요 시)

```bash
# POSTGRES_USER 기본값은 puco_user — .env에서 변경했다면 해당 값으로 대체
# psql 셸 접속
docker compose -f docker-compose.prod.yml exec db \
  psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl

# 직접 쿼리 실행 예시
docker compose -f docker-compose.prod.yml exec db \
  psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl -c "SELECT count(*) FROM games;"
```

### 10.6 Alembic 마이그레이션 실행

코드 업데이트 후 스키마 변경이 있을 때:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### 10.7 코드 업데이트 (배포 브랜치 최신화)

```bash
cd /opt/castone

# 운영 배포는 prod 브랜치를 사용합니다.
git pull origin prod

# 로컬/CI에서 같은 브랜치 기준으로 새 image tar를 만든 뒤 EC2에 전송
docker load -i /tmp/castone-backend-prod-amd64.tar

# 빌드 없이 재기동
docker compose -f docker-compose.prod.yml up -d --no-build backend
```

---

## 11. 분석 CLI 사용법

> `analytics_cli.py`는 `backend/scripts/analytics_cli.py`에 위치하며,
> EC2에 SSH 접속 후 백엔드 컨테이너 내부에서 실행합니다.
> 모든 명령은 **읽기 전용**입니다 (SELECT만 실행, DB 변경 없음).

### 11.1 기본 실행 패턴

```bash
# EC2 SSH 접속 후
ssh ubuntu@<EC2_PUBLIC_IP>

# /opt/castone 로 이동
cd /opt/castone

# analytics_cli 실행 (모든 서브커맨드 동일 패턴)
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli <subcommand> [options]
```

### 11.2 도움말 확인

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli --help

docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli win-rate-by-bot --help
```

### 11.3 Cookbook 예시

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

### 11.4 user-id 모르는 경우

`list-users`로 먼저 UUID를 확인한 뒤 다른 서브커맨드에 사용합니다.

```bash
# 전체 사용자 UUID 확인
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli list-users

# 특정 닉네임으로 필터 (list-users 결과를 grep)
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli list-users | grep "player_kim"
```

### 11.5 실데이터 검증 전제

이 절의 목적은 "로컬 fixture/목 데이터가 아니라 EC2 배포 환경의 실제 DB 데이터를 읽는다"는 것을 확인하는 것입니다. 검증 데이터는 Vercel 프론트에서 직접 로그인한 뒤 생성하고 종료한 게임이어야 합니다.

검증 전에 아래 흐름을 먼저 수행합니다.

1. Vercel 프론트에서 Google 로그인
2. 새 게임을 2-5개 생성
3. 게임을 끝까지 진행해 `FINISHED` 상태로 만들기
4. 리플레이 목록 화면에서 방금 생성한 게임이 보이는지 1차 확인

브라우저 콘솔에서 현재 로그인 토큰이 필요하면 아래 값을 복사합니다.

```javascript
localStorage.getItem('access_token')
```

### 11.6 DB 원본 SQL 확인

최근 생성된 사용자, 게임, 리플레이 row를 DB에서 직접 확인합니다.

```bash
cd /opt/castone

# 최근 사용자 확인
docker compose -f docker-compose.prod.yml exec db \
  psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl \
  -c "SELECT id, nickname, email, created_at FROM users ORDER BY created_at DESC LIMIT 10;"

# 최근 종료 게임 확인
docker compose -f docker-compose.prod.yml exec db \
  psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl \
  -c "SELECT id, status, players, winner_id, created_at FROM games ORDER BY created_at DESC LIMIT 10;"

# 최근 리플레이 payload 확인
docker compose -f docker-compose.prod.yml exec db \
  psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl \
  -c "SELECT game_id, jsonb_array_length(payload->'entries') AS entries, payload ? 'final_scores' AS has_final_scores, created_at FROM replays ORDER BY created_at DESC LIMIT 10;"
```

검증할 사용자 UUID를 지정합니다.

```bash
USER_ID=<Vercel에서_게임을_생성한_사용자_UUID>
```

해당 사용자의 완료 게임 수와 승수를 SQL로 직접 계산합니다.

```bash
docker compose -f docker-compose.prod.yml exec db \
  psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl \
  -v user_id="$USER_ID" \
  -c "SELECT COUNT(*) AS finished_games, COUNT(*) FILTER (WHERE winner_id = :'user_id') AS wins FROM games WHERE status = 'FINISHED' AND players @> jsonb_build_array(:'user_id');"
```

봇 타입별 승률도 SQL로 직접 계산합니다. 한 게임 안에 같은 봇 타입이 여러 번 있어도 한 번만 카운트합니다.

```bash
docker compose -f docker-compose.prod.yml exec db \
  psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl \
  -v user_id="$USER_ID" \
  -c "WITH user_games AS (
        SELECT id, players, winner_id
        FROM games
        WHERE status = 'FINISHED'
          AND players @> jsonb_build_array(:'user_id')
      ),
      bot_games AS (
        SELECT DISTINCT
          g.id,
          regexp_replace(p.actor_id, '^BOT_', '') AS bot_type,
          g.winner_id
        FROM user_games g
        CROSS JOIN LATERAL jsonb_array_elements_text(g.players) AS p(actor_id)
        WHERE p.actor_id LIKE 'BOT_%'
      )
      SELECT
        bot_type,
        COUNT(*) AS games,
        COUNT(*) FILTER (WHERE winner_id = :'user_id') AS wins,
        ROUND((COUNT(*) FILTER (WHERE winner_id = :'user_id'))::numeric / NULLIF(COUNT(*), 0), 4) AS win_rate
      FROM bot_games
      GROUP BY bot_type
      ORDER BY games DESC;"
```

### 11.7 CLI 결과 대조

위 SQL 결과와 아래 CLI 결과가 같은 값을 보여야 합니다.

```bash
# 사용자별 완료 게임 수
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli list-users --json

# 최근 게임 목록
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli recent-games --user-id "$USER_ID" --limit 20 --json

# 봇 타입별 승률
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli win-rate-by-bot --user-id "$USER_ID" --json

# 판수 누적별 승률
docker compose -f docker-compose.prod.yml exec backend \
  python -m scripts.analytics_cli win-rate-by-count --user-id "$USER_ID" --bucket 5 --json
```

통과 기준:

- `list-users`의 `total_games`가 SQL의 `finished_games`와 일치
- `recent-games`에 방금 만든 게임 ID 또는 생성 시각이 포함
- `win-rate-by-bot`의 `games`, `wins`, `win_rate`가 직접 SQL 결과와 일치
- CLI 결과가 비어 있다면 `USER_ID`가 `games.players` 배열에 들어 있는 UUID와 같은지 먼저 확인

### 11.8 Replay UI 검증

API와 UI를 함께 확인합니다.

```bash
EC2_ORIGIN=https://<EC2_PUBLIC_IP>.sslip.io
TOKEN=<브라우저_localStorage_access_token>
GAME_ID=<replays_목록에서_확인한_game_id>

# 리플레이 목록 API
curl -s "$EC2_ORIGIN/api/puco/replays/?page=1&size=10" \
  -H "Authorization: Bearer $TOKEN" | jq '.replays[0]'

# 리플레이 상세 API
curl -s "$EC2_ORIGIN/api/puco/replays/$GAME_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '{game_id, total_frames, first_frame_has_rich_state: (.replay_frames[0].rich_state != null)}'
```

통과 기준:

- 목록 API에 방금 만든 게임이 포함
- 상세 API의 `total_frames`가 1 이상
- 첫 프레임의 `rich_state`가 `null`이 아님
- Vercel 화면에서 리플레이 상세 진입 시 JSON 텍스트가 아니라 게임 보드 UI가 렌더링됨
- 재생/일시정지, 이전/다음, 슬라이더 이동 시 화면의 보드 상태가 바뀜

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
| 80 포트 무응답 | backend 컨테이너 상태 | `docker compose -f docker-compose.prod.yml ps backend` |
| 메모리 부족 | 전체 메모리 사용량 | `docker stats --no-stream` |
| 디스크 부족 | Docker 레이어/볼륨 | `docker system df` |
