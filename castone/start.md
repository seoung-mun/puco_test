# Docker로 프로젝트 실행하기

이 문서는 도커(Docker)를 사용하여 터미널 환경에서 본 프로젝트를 실행하는 명령어를 안내합니다.

## 사전 준비
- [Docker](https://www.docker.com/products/docker-desktop/)가 설치되어 있어야 합니다.
- [Docker Compose](https://docs.docker.com/compose/install/)가 설치되어 있어야 합니다.

## 프로젝트 실행 환경 구축

### 1. 이미지 빌드 및 컨테이너 실행
터미널에서 프로젝트 루트 폴더(/Users/seoungmun/Documents/agent_dev/castone)로 이동한 후 아래 명령어를 입력합니다.

```bash
docker-compose up --build
```

- `--build`: Dockerfile의 변경사항이 있을 경우 이미지를 다시 빌드합니다.
- `-d` 옵션을 추가하면 백그라운드에서 실행할 수 있습니다. (`docker-compose up -d`)

### 2. 실행 중인 서비스 확인
컨테이너가 정상적으로 실행 중인지 확인합니다.

```bash
docker-compose ps
```

각 서비스의 주소는 다음과 같습니다:
- **Frontend**: [http://localhost:3000](http://localhost:3000)
- **Backend (API Docs)**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 3. 로그 확인
실행 중인 서비스의 로그를 실시간으로 확인하고 싶을 때 사용합니다.

```bash
docker-compose logs -f
```

### 4. 서비스 중지
실행 중인 컨테이너를 중지하고 삭제합니다.

```bash
docker-compose down
```

- 볼륨(데이터베이스 데이터 등)까지 삭제하려면 `-v` 옵션을 추가합니다. (`docker-compose down -v`)

---

## 문제 해결 (Troubleshooting)

- **포트 충돌**: 3000, 8000, 5432, 6379 포트가 이미 사용 중이라면 해당 프로세스를 종료하거나 `docker-compose.yml`에서 포트를 변경해야 합니다.
- **의존성 설치**: `backend/requirements.txt`나 `frontend/package.json`이 변경되었을 경우 반드시 `--build` 옵션을 사용해 주세요.
