# Task.md — Puerto Rico AI Battle Platform

> 목표: 빠른 배포로 실제 플레이 데이터 수집 (캡스톤 강화학습 성능 검증)
> 마지막 업데이트: 2026-03-26

---

## ✅ 완료된 작업 (claude/sad-allen 브랜치)

- [x] `_action_to_history()` 누락 액션 범위 5개 추가
  - `69-80`: mayor_toggle_island (섬 슬롯 일꾼 배치/회수)
  - `81-92`: mayor_toggle_city (건물 슬롯 일꾼 배치/회수)
  - `64-68`: store_windrose (나침반 보관)
  - `93-97`: craftsman_privilege (생산자 특권)
  - `106-110`: store_warehouse (창고 보관)
- [x] i18n 번역 추가 (ko/en/it) — 위 5개 액션 UI 표시
- [x] `frontend/Dockerfile` production stage (nginx) 추가
- [x] `frontend/nginx.conf` 생성 (SPA fallback + API/WebSocket 프록시)
- [x] `backend/Dockerfile.prod` 생성 (PuCo_RL + 모델 이미지 내 포함)
- [x] `docker-compose.prod.yml` 생성 (production 배포용)
- [x] `DEPLOY.md` GCP VM 배포 가이드 작성
- [x] `.gitmodules` 추가
- [x] 위 내용 `claude/sad-allen` 브랜치에 push 완료

---

## 🔥 즉시 처리 필요 (Blocker)

### 1. `.env` INTERNAL_API_KEY 불일치 수정
- **문제**: 1인/멀티플레이 방 생성 시 모든 legacy API 403 Forbidden
  - `POST /api/set-mode/single` → 403
  - `POST /api/new-game` → 403
  - `POST /api/multiplayer/init` → 403
- **원인**: 두 값이 다름
  ```
  INTERNAL_API_KEY=dev-internal-key-change-me1      ← 백엔드
  VITE_INTERNAL_API_KEY=dev-internal-key-change-me  ← 프론트 (끝에 1 없음)
  ```
- **수정**: `castone/.env`에서 두 값을 동일하게 맞춤
  ```env
  INTERNAL_API_KEY=dev-internal-key-change-me
  VITE_INTERNAL_API_KEY=dev-internal-key-change-me
  ```
- **적용**: `docker compose restart backend frontend`

### 2. Google OAuth localhost 등록
- **문제**: Google 로그인 버튼이 동작하지 않음
- **원인**: Google Cloud Console에 `localhost:3000` 미등록 가능성
- **수정**: Google Cloud Console → 사용자 인증 정보 → OAuth 클라이언트 ID
  - 승인된 JavaScript 원본: `http://localhost:3000` 추가
  - 승인된 리디렉션 URI: 필요시 추가
- **참고**: 이미 등록되어 있다면 브라우저 콘솔 에러 메시지 확인

---

## 🐛 버그 조사 필요

### 3. 개척자(Settler) / 건축가(Builder) 페이즈 2번 반복
- **현상**: 가끔 개척자/건축가 페이즈가 연속으로 2번 실행됨
- **가설**: 봇이 패스만 하던 시절 발생한 phase transition 꼬임 → 위 히스토리 수정 후 재현 여부 확인 필요
- **조사 위치**: `PuCo_RL/env/engine.py` phase transition 로직
- **방법**: 게임 1판 플레이 후 `game_logs` 테이블에서 round/phase 패턴 확인
  ```sql
  SELECT round, step, actor_id, action_data, state_summary->>'phase'
  FROM game_logs
  WHERE game_id = '<game_id>'
  ORDER BY step;
  ```

---

## 🚀 배포 (GCP VM)

### 4. `claude/sad-allen` → `dev` → `main` 머지
- `claude/sad-allen` 브랜치 내용을 `dev`에 머지
- 로컬 테스트 완료 후 `main`에 머지

### 5. GCP VM 프로비저닝
- 인스턴스: `e2-medium` (2 vCPU, 4GB RAM) — 약 $25/월
- 리전: `asia-northeast3-a` (서울)
- OS: Ubuntu 24.04 LTS, 디스크 30GB
- 방화벽: HTTP(80), SSH(22) 허용

### 6. VM 배포 실행
```bash
# VM에서
git clone --recurse-submodules https://github.com/seoung-mun/puco_test.git
cd puco_test/castone

# .env 생성 (production 값으로)
cp .env.example .env
# SECRET_KEY, POSTGRES_PASSWORD, REDIS_PASSWORD 재생성 필요
# python3 -c "import secrets; print(secrets.token_hex(64))"

mkdir -p data/logs
docker compose -f docker-compose.prod.yml up -d --build
```

### 7. Google OAuth production 도메인 등록
- VM 외부 IP를 Google Cloud Console 승인된 JavaScript 원본에 추가
- `http://VM_외부_IP`

### 8. Smoke Test
- `http://VM_IP` 접속 → Google 로그인
- 방 생성 → 봇 2명 → 게임 시작
- 각 페이즈 히스토리 표시 확인
- DB 로그 수집 확인:
  ```bash
  docker exec puco_db psql -U puco_user -d puco_rl -c "SELECT count(*) FROM game_logs"
  docker exec puco_backend ls /data/logs/
  ```

---

## 📋 참고

- 배포 상세 가이드: `castone/DEPLOY.md` (claude/sad-allen 브랜치에 있음)
- Production Docker Compose: `castone/docker-compose.prod.yml`
- Backend Production Dockerfile: `castone/backend/Dockerfile.prod`
- 현재 dev 브랜치 로컬 실행: `docker compose up --build` (개발용)

---

## 📌 범위 밖 (지금은 skip)

- HTTPS / SSL 인증서
- CI/CD 파이프라인 (GitHub Actions)
- Rate limiting
- 모니터링 / 알림
- 모델 핫스왑
- Phase 1~3 보안 강화 태스크
