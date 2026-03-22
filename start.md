# ⚡ Castone Project Quick Start Guide

이 가이드는 Docker를 사용하여 `Castone` 프로젝트를 실행하고 모니터링하는 핵심 명령어들을 정리합니다.

---

## 1. 프로젝트 실행 (Startup)

모든 서비스(프론트엔드, 백엔드, DB, Redis)를 한 번에 빌드하고 실행합니다.

```bash
# castest/castone 폴더로 이동 후 실행
cd castone
docker compose up -d --build
```

- **Frontend**: [http://localhost:3000](http://localhost:3000)
- **Backend API**: [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

---

## 2. 모니터링 및 실시간 로그 (Logging)

### 서비스 전체 로그 확인
```bash
docker compose logs -f
```

### MLOps 데이터 트랜잭션 실시간 모니터링 (JSONL)
PPO 학습용 데이터가 쌓이는 것을 호스트 시스템에서 직접 확인합니다.
```bash
tail -f data/logs/transitions*.jsonl
```

---

## 3. 데이터베이스 접속 (Database)

관측 데이터(`game_logs`) 확인을 위해 DBeaver 등의 툴로 접속하세요.

- **Host**: `localhost`
- **Port**: `5432`
- **Username**: `puco_user`
- **Password**: `puco_password`
- **Database**: `puco_rl`

---

## 4. AI 모델 교체 절차 (PPO Model Swap)

1. 새로운 `.pth` 가중치 파일을 `castone/PuCo_RL/models/` 디렉토리에 넣습니다.
2. `docker-compose.yml` 파일에서 `PPO_MODEL_FILENAME` 환경변수를 새 파일명으로 수정합니다.
3. 백엔드 컨테이너만 재시작합니다.
   ```bash
   docker compose up -d --build backend
   ```

---

## 5. 상세 문서 링크
- **MLOps 데이터 추적 보고서**: [docs/report/mlops_data_tracking_report.md](./castone/docs/report/mlops_data_tracking_report.md)
- **멀티플레이어 아키텍처**: [docs/multiplayer_architecture_design.md](./castone/docs/multiplayer_architecture_design.md)
- **TDD 검증 시나리오**: [tests/TEST_SPEC.md](./tests/TEST_SPEC.md)
