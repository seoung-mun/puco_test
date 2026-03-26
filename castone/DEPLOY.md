# 배포 가이드 — Puerto Rico AI Battle Platform

## 1. GCP VM 프로비저닝

### GCP Console에서 VM 생성
- **이름**: `puco-server`
- **리전**: `asia-northeast3-a` (서울)
- **머신 타입**: `e2-medium` (2 vCPU, 4GB RAM) — ~$25/월
- **OS**: Ubuntu 24.04 LTS
- **디스크**: 30GB standard persistent disk
- **방화벽**: "HTTP 트래픽 허용" 체크 (TCP 80)

### 방화벽 규칙 확인
GCP Console > VPC 네트워크 > 방화벽에서 TCP 80이 열려있는지 확인.

---

## 2. VM 초기 설정

SSH 접속 후:

```bash
# Docker 설치
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Docker 권한 (재접속 필요)
sudo usermod -aG docker $USER
```

재접속 후:

```bash
docker --version
docker compose version
```

---

## 3. 코드 배포

```bash
# 레포 클론 (서브모듈 포함)
git clone --recurse-submodules https://github.com/seoung-mun/puco_test.git
cd puco_test/castone

# 데이터 로그 디렉토리 생성
mkdir -p data/logs
```

---

## 4. .env 파일 생성

```bash
# 시크릿 키 생성
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(64))"
python3 -c "import secrets; print('INTERNAL_API_KEY=' + secrets.token_hex(32))"
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(16))"
python3 -c "import secrets; print('REDIS_PASSWORD=' + secrets.token_hex(16))"
```

위 출력을 참고하여 `.env` 파일 생성:

```bash
cat > .env << 'ENVEOF'
# Database
POSTGRES_USER=puco_user
POSTGRES_PASSWORD=여기에_생성된_값
DATABASE_URL=postgresql://puco_user:여기에_생성된_값@db:5432/puco_rl

# Redis
REDIS_PASSWORD=여기에_생성된_값
REDIS_URL=redis://:여기에_생성된_값@redis:6379/0

# Security
SECRET_KEY=여기에_생성된_값
INTERNAL_API_KEY=여기에_생성된_값
VITE_INTERNAL_API_KEY=INTERNAL_API_KEY와_동일한_값

# Debug
DEBUG=false

# Bot model
MODEL_TYPE=ppo
PPO_MODEL_FILENAME=ppo_agent_update_100.pth

# Google OAuth
GOOGLE_CLIENT_ID=실제_클라이언트_ID

# CORS (VM의 외부 IP로 변경)
ALLOWED_ORIGINS=http://VM외부IP
ENVEOF
```

**중요**: `POSTGRES_PASSWORD`를 `DATABASE_URL`과 `REDIS_PASSWORD`를 `REDIS_URL`에도 동일하게 넣어야 합니다.

---

## 5. Google OAuth 설정

GCP Console > API 및 서비스 > 사용자 인증 정보:

1. OAuth 2.0 클라이언트 ID 선택
2. **승인된 JavaScript 원본** 추가: `http://VM외부IP`
3. **승인된 리디렉션 URI** 추가: `http://VM외부IP/api/v1/auth/google`
4. 저장

---

## 6. 빌드 및 실행

```bash
# 프로덕션 빌드 + 실행
docker compose -f docker-compose.prod.yml up -d --build

# 로그 확인
docker compose -f docker-compose.prod.yml logs -f

# 상태 확인
docker compose -f docker-compose.prod.yml ps
```

---

## 7. Smoke Test

1. 브라우저에서 `http://VM외부IP` 접속
2. Google 로그인
3. 방 생성 → 봇 추가 → 게임 시작
4. 각 페이즈에서 봇 액션 확인

```bash
# DB 로그 확인
docker exec puco_db psql -U puco_user -d puco_rl -c "SELECT count(*) FROM game_logs"

# JSONL 로그 확인
docker exec puco_backend ls -la /data/logs/
```

---

## 8. 유지보수

```bash
# 서비스 재시작
docker compose -f docker-compose.prod.yml restart

# 코드 업데이트
git pull --recurse-submodules
docker compose -f docker-compose.prod.yml up -d --build

# DB 백업
docker exec puco_db pg_dump -U puco_user puco_rl > backup_$(date +%Y%m%d).sql

# 로그 백업
cp -r data/logs/ ~/backup_logs_$(date +%Y%m%d)/
```

---

## 트러블슈팅

| 증상 | 해결 |
|------|------|
| Google 로그인 안됨 | GOOGLE_CLIENT_ID 확인, 승인된 JavaScript 원본에 VM IP 추가 |
| 502 Bad Gateway | `docker logs puco_backend` 확인, DB 마이그레이션 에러 가능 |
| WebSocket 연결 안됨 | nginx.conf의 WebSocket 프록시 설정 확인 |
| 봇이 응답 안함 | `docker logs puco_backend`에서 PuCo_RL import 에러 확인 |
| 포트 80 접속 안됨 | GCP 방화벽에서 HTTP 허용 확인 |
