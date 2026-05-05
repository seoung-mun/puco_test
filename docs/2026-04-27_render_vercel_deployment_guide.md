# Castone Render + Vercel 배포 가이드

**작성일:** 2026-04-27  
**대상 배포 구조:** Render 백엔드 + Render Postgres + Render Key Value + Vercel 프론트엔드

## 1. 권장 배포 구조

현재 코드베이스와 예상 트래픽(최대 사용자 40명, 동시 접속 10명 내외)을 기준으로 아래 구성이 가장 무난합니다.

- `frontend`: Vercel
- `backend`: Render Web Service
- `postgresql`: Render Postgres 별도 서비스
- `redis`: Render Key Value 별도 서비스

### 왜 Postgres / Redis를 분리하는가

- 데이터 영속성과 백업은 Render Postgres가 훨씬 안전합니다.
- Redis는 WebSocket 상태 전파와 캐시 성격이 강해서 Key Value로 분리하는 편이 운영이 단순합니다.
- 백엔드 컨테이너 재배포와 DB/Redis 수명주기를 분리할 수 있습니다.
- 현재 규모에서는 큰 스케일링보다 운영 단순성과 장애 격리가 더 중요합니다.

결론:

- **Postgres는 반드시 별도 Render Postgres로 분리 권장**
- **Redis도 Render Key Value로 분리 권장**

## 2. 현재 코드 기준으로 확인한 배포 포인트

### 백엔드

- 배포용 Dockerfile은 [backend/Dockerfile.prod](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/Dockerfile.prod:1) 입니다.
- 컨테이너 시작 시 [backend/entrypoint.sh](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/entrypoint.sh:1) 에서 `alembic upgrade head`를 먼저 실행한 뒤 `uvicorn`을 띄웁니다.
- 헬스체크 엔드포인트는 `/health` 입니다.
- 서버는 기본적으로 `8000` 포트를 사용하지만, 이번에 `PORT` 환경변수를 받도록 맞춰 두었습니다. Render에서 `PORT=10000`으로 두거나, 자동 감지에 맡겨도 됩니다.
- 리플레이는 배포용 이미지에서 `REPLAY_STORAGE_BACKEND=db` 기본값으로 동작하므로, Render에서는 디스크 대신 Postgres `replays` 테이블에 JSONB payload를 저장합니다.

### 프론트엔드

- 프론트는 기존에 same-origin 전제를 강하게 가지고 있었는데, 이번에 `VITE_BACKEND_ORIGIN` 환경변수로 Render 백엔드를 직접 바라볼 수 있게 맞췄습니다.
- `Vercel` SPA 새로고침/딥링크 대응을 위해 [frontend/vercel.json](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/vercel.json:1) 을 추가했습니다.

## 3. 내가 해야 하는 일 체크리스트

### A. 배포 전 준비

1. Git 원격 저장소에 현재 배포할 브랜치를 푸시합니다.
현재 체크아웃 브랜치는 `refactor/adapter` 입니다. 운영 배포라면 안정 브랜치(`main` 등)로 정리해서 배포하는 편이 좋습니다.

2. 아래 시크릿 값을 준비합니다.
- `SECRET_KEY`
- `INTERNAL_API_KEY`
- `GOOGLE_CLIENT_ID`

3. Google Cloud Console에서 OAuth 설정을 준비합니다.
- Authorized JavaScript origins에 프론트 도메인을 추가해야 합니다.
- 최소한 Vercel 운영 도메인 1개는 반드시 등록해야 합니다.

- 이건 어떻게 해? 
- 어떤 프론트 도메인을 추가하라는거야?
- vercel을 먼저 배포하고, 이후에 그 도메인을 추가하라는 소리야?

### B. Render Postgres 만들기

1. Render Dashboard에서 `New > Postgres` 선택
2. 이름 예시: `castone-postgres`
3. Region:
한국/아시아 사용자 위주면 `Singapore` 추천
4. 가장 작은 입문형 유료 플랜부터 시작
5. 생성 후 `Internal Database URL` 확보
- 생성 완료
권장:

- 백엔드와 같은 Region 사용

- 외부 접속은 필요할 때만 열고, 가능하면 제한 IP로 관리
- 이건 어떻게 하는거야?

### C. Render Key Value 만들기

1. Render Dashboard에서 `New > Key Value` 선택
2. 이름 예시: `castone-redis`
3. Region:
백엔드/DB와 동일하게 맞춤
4. Maxmemory policy:
현재 용도는 캐시/상태 전파 성격이 강하므로 `allkeys-lru`가 무난
5. 가장 작은 입문형 플랜부터 시작
6. 생성 후 `Internal URL` 확보
- 일단 이것까지는 끝
권장:

- 가능하면 Internal Authentication을 켜고, 인증 포함 Internal URL을 `REDIS_URL`로 사용

- 이건 어떻게 하는거야?


## 4. Render Web Service 생성 화면 입력값

아래는 지금 Render 웹 서비스 생성 폼에서 채우면 되는 값입니다.

### 기본 항목

- `Name`: `castone-backend`
- `Region`: `Singapore`
한국/아시아 트래픽 기준. Postgres/Key Value와 반드시 동일 Region으로 맞춥니다.
- `Branch`: 배포할 브랜치
지금 작업 기준으론 `refactor/adapter` 이지만, 운영이면 보통 `main` 권장
- `Language`: `Docker`

### Docker 관련 항목

- `Root Directory`: 저장소 루트
현재 `backend/Dockerfile.prod`가 루트 컨텍스트에서 `backend/`와 `PuCo_RL/` 둘 다 복사하므로 루트를 기준으로 잡아야 합니다.
- `Dockerfile Path`: `backend/Dockerfile.prod`
- `Docker Command`: 비워두는 것을 권장
이미 Dockerfile의 `CMD ["/entrypoint.sh"]`를 사용하도록 되어 있습니다.

### 인스턴스 타입

- 시작점: 가장 작은 입문형 유료 인스턴스
- 이유:
현재 동접 10명 수준이면 우선 작은 인스턴스로 충분할 가능성이 높고, 부족하면 Render에서 상향하는 편이 낫습니다.

### Health Check

- `Health Check Path`: `/health`

### Environment Variables

아래 값을 Render 백엔드 서비스의 Environment에 넣습니다.

- `PORT=10000`
- `DATABASE_URL=<Render Postgres Internal Database URL>`
- `REDIS_URL=<Render Key Value Internal URL>`
- `SECRET_KEY=<랜덤 시크릿>`
- `INTERNAL_API_KEY=<랜덤 시크릿>`
- `GOOGLE_CLIENT_ID=<Google OAuth Client ID>`
- `ALLOWED_ORIGINS=<Vercel 프론트 운영 도메인>`
- `DEBUG=false`
- `REPLAY_STORAGE_BACKEND=db`

- `MODEL_TYPE=ppo`
- `PPO_BUNDLE_DIR=ppo-pr-server-semantic293-20260419`

    - 현재 운영 PPO는 293-dim bundle 기준이다. `PPO_MODEL_FILENAME`에 예전 210-dim 체크포인트를 직접 넣으면 `expected 210, got 293` 오류가 날 수 있다.
    - 다른 PPO 후보를 올리고 싶다면 bare checkpoint보다 그 체크포인트에서 생성한 bundle을 `PPO_BUNDLE_DIR`로 주입하는 편이 안전하다.

필요 시 추가:

- `HPPO_MODEL_FILENAME=<사용할 때만>`

### ALLOWED_ORIGINS 입력 예시

운영 도메인이 `https://castone.vercel.app` 라면:

```env
ALLOWED_ORIGINS=https://castone.vercel.app
```

커스텀 도메인까지 같이 쓸 거면:

```env
ALLOWED_ORIGINS=https://castone.vercel.app,https://castone.yourdomain.com
```

주의:

- 지금 백엔드는 `allow_credentials=True` 설정이라 `*` 와일드카드 CORS는 쓰지 않는 편이 안전합니다.
- Vercel preview URL까지 모두 허용하려면 정확한 preview origin을 추가로 넣어야 합니다.

## 5. Vercel 프론트 배포 시 입력값

### 프로젝트 생성

- `Framework Preset`: `Vite`
- `Root Directory`: `frontend`
- `Build Command`: `npm run build`
- `Output Directory`: `dist`
- `Install Command`: `npm install`

### Vercel Environment Variables

- `VITE_GOOGLE_CLIENT_ID=<Google OAuth Client ID>`
- `VITE_BACKEND_ORIGIN=https://<render-backend-domain>`

예시:

```env
VITE_BACKEND_ORIGIN=https://castone-backend.onrender.com
```

설명:

- 이제 프론트는 `VITE_BACKEND_ORIGIN` 기준으로 API와 WebSocket을 Render 백엔드에 직접 붙습니다.
- same-origin nginx 프록시에 의존하지 않으므로 Vercel 분리 배포가 쉬워집니다.

## 6. 추천 배포 순서

1. Render Postgres 생성
2. Render Key Value 생성
3. Render Backend Web Service 생성
4. 백엔드 첫 배포 성공 후 `onrender.com` 주소 확인
5. Vercel에서 프론트 배포
6. Vercel 운영 URL 확인
7. Render 백엔드의 `ALLOWED_ORIGINS`를 Vercel 운영 URL로 업데이트
8. Google OAuth Authorized JavaScript origins에 Vercel 운영 URL 추가
9. 최종 스모크 테스트

## 7. 배포 후 확인할 것

### 백엔드

- `GET /health` 가 200인지 확인
- Render 로그에서 `Migration complete.` 확인
- DB/Redis 연결 에러가 없는지 확인

### 프론트

- 첫 화면 로드
- Google 로그인 버튼 표시
- 로그인 성공
- 방 목록 조회
- 방 생성 / 입장
- 실제 WebSocket 연결

## 8. 지금 바로 참고할 실제 파일

- 백엔드 Dockerfile: [backend/Dockerfile.prod](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/Dockerfile.prod:1)
- 백엔드 엔트리포인트: [backend/entrypoint.sh](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/entrypoint.sh:1)
- 환경변수 예시: [.env.example](/Users/seoungmun/Documents/agent_dev/castest/castone/.env.example:1)
- 프론트 Vercel 설정: [frontend/vercel.json](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/vercel.json:1)
- 프론트 백엔드 주소 설정: [frontend/src/config.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/config.ts:1)

## 9. 참고한 공식 문서

- Render Docker 배포: https://render.com/docs/docker
- Render Web Services: https://render.com/docs/web-services
- Render Health Checks: https://render.com/docs/health-checks
- Render Postgres 연결: https://render.com/docs/postgresql-creating-connecting
- Render Key Value: https://render.com/docs/key-value
- Render Regions: https://render.com/docs/regions
- Vercel Rewrites: https://vercel.com/docs/rewrites
- Vercel Vite 배포: https://vercel.com/docs/frameworks/frontend/vite
