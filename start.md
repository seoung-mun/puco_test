# Start Guide

처음 레포를 받아서 로컬에서 실행할 때 필요한 최소 절차를 정리한 문서입니다.

## 1. 먼저 받아야 하는 비공개 항목

아래 항목은 Git에 올리지 않고 별도 공유합니다.

- 루트 `.env`
  - 공유 채널: 카카오톡
  - 위치: `castone/.env`
- 모델 체크포인트
  - 공유 채널: 카카오톡
  - 위치: `castone/PuCo_RL/models/<파일명>.pth`
- 모델 sidecar JSON
  - 있으면 같이 받아서 같은 폴더에 둡니다.
  - 위치: `castone/PuCo_RL/models/<파일명>.json`
- Google OAuth 관리 권한 또는 Test user 추가 요청 창구
  - Git에 넣기 애매한 운영 정보이므로 owner가 별도 관리합니다.

## 2. Git에 올리지 않는 이유

아래 항목은 민감 정보이거나 용량이 크고 변경 주기가 달라서 Git 대신 별도 공유가 맞습니다.

- `.env`
  - DB/Redis 비밀번호, API 키, Google OAuth client id 포함
- `PuCo_RL/models/*.pth`
  - 바이너리 체크포인트 파일
- `PuCo_RL/models/*.json`
  - 모델 메타데이터 sidecar
- 개인 로컬 로그/DB/캐시
  - `data/logs/`, `*.db`, `node_modules/` 등

## 3. 필수 배치 위치

### `.env`

- 공유받은 `.env`를 레포 루트에 둡니다.
- 경로:

```text
castone/.env
```

- 최소 확인 키:
  - `DEBUG=true`
  - `GOOGLE_CLIENT_ID=...`
  - `VITE_GOOGLE_CLIENT_ID=...`
  - `MODEL_TYPE=ppo` 또는 `MODEL_TYPE=hppo`
  - `PPO_MODEL_FILENAME=...` 또는 `HPPO_MODEL_FILENAME=...`

### 모델 파일

- 공유받은 `.pth` 파일을 아래 폴더에 둡니다.

```text
castone/PuCo_RL/models/
```

- `.env`의 파일명과 실제 파일명이 정확히 같아야 합니다.

예시:

```env
MODEL_TYPE=ppo
PPO_MODEL_FILENAME=PPO_PR_Server_20260401_214532_step_99942400.pth
```

실제 파일:

```text
castone/PuCo_RL/models/PPO_PR_Server_20260401_214532_step_99942400.pth
```

### sidecar JSON

- 같이 받았다면 `.pth`와 같은 basename으로 같은 폴더에 둡니다.
- 없더라도 표준 `PPO_PR_Server_*.pth` 형식이면 기본 bootstrap metadata로 뜰 수 있습니다.
- 다만 sidecar가 있으면 그 정보를 우선 사용하므로 가능하면 같이 받는 것을 권장합니다.

## 4. 첫 실행 순서

1. 레포 클론

```bash
git clone <repo-url>
cd castone
```

2. 비공개 파일 배치

- `.env`를 루트에 둡니다.
- 모델 체크포인트를 `PuCo_RL/models/`에 둡니다.
- sidecar `.json`이 있으면 같이 둡니다.

3. 파일명/환경값 확인

```bash
ls PuCo_RL/models
grep -E '^(MODEL_TYPE|PPO_MODEL_FILENAME|HPPO_MODEL_FILENAME|GOOGLE_CLIENT_ID|VITE_GOOGLE_CLIENT_ID|DEBUG)=' .env
```

4. Docker 실행

```bash
docker compose up -d --build
docker compose ps
```

5. 서버 상태 확인

```bash
curl http://localhost:8000/health
```

6. 브라우저 접속

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Adminer: `http://localhost:8080`

## 5. 실행 후 바로 확인할 것

- 로그인 화면이 뜨는지
- Google 로그인 버튼이 보이는지
- `docker compose ps`에서 `frontend`, `backend`, `db`, `redis`가 `Up` 상태인지
- backend가 migration 후 정상 기동됐는지

로그 확인:

```bash
docker compose logs backend --tail 100
docker compose logs frontend --tail 100
```

## 6. 자주 막히는 지점

### Google 로그인 실패

- 반드시 `http://localhost:3000` 또는 `http://localhost:5173`로 접속합니다.
- `.env`의 `GOOGLE_CLIENT_ID`, `VITE_GOOGLE_CLIENT_ID`가 비어 있지 않은지 확인합니다.
- OAuth consent screen이 `Testing`이면 팀원 계정이 Test users에 있어야 합니다.

### 모델 로드 실패

- `.env`의 `PPO_MODEL_FILENAME` 또는 `HPPO_MODEL_FILENAME`가 실제 파일명과 일치하는지 확인합니다.
- 모델 파일이 `PuCo_RL/models/` 바로 아래에 있는지 확인합니다.

### 포트 충돌

- `3000`, `8000`, `8080`, `5432`, `6379`를 이미 다른 프로세스가 쓰고 있으면 기존 프로세스를 종료하거나 compose 설정을 바꿉니다.

## 7. 비공개 공유 체크리스트

새 팀원 온보딩 시 아래 4가지를 같이 전달하면 됩니다.

- `.env` 파일
- 사용할 모델 `.pth`
- 있으면 모델 `.json` sidecar
- Google 로그인용 Test user 추가 여부 또는 요청 방법
