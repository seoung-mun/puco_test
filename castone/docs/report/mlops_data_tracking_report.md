# MLOps 데이터 보존 및 모니터링 가이드 (Castone AI)

이 문서는 Castone 프로젝트에 구축된 MLOps 데이터 수집 파이프라인의 구조와 이를 모니터링/활용하는 구체적 방법을 명시합니다.

## 1. 강화학습(RL) 학습 스냅샷 수집 (JSONL 로그)
AI 모델(PPO)의 오프라인 자율학습(Offline RL) 재학습을 지원하기 위해, 플레이어가 갱신하는 모든 **상태(State), 행동(Action), 보상(Reward)** 은 실시간으로 수집되어 로컬 파일로 적재됩니다.

- **저장 위치**: `castest/castone/data/logs/` 하위
- **파일 포맷**: `transitions_YYYY-MM-DD.jsonl` (JSONL 형태의 Row 단위 로깅)
- **실시간 모니터링 방법 (DevOps)**:
  호스트 터미널에서 다음 명령어를 통해 실시간으로 어떤 데이터 트랜잭션이 저장되고 있는지 관찰할 수 있습니다.
  ```bash
  tail -f /Users/seoungmun/Documents/agent_dev/castest/castone/data/logs/transitions*.jsonl
  ```

## 2. 플레이어 및 봇의 게임 진행 기록 (PostgreSQL)
게임 리플레이 뷰, 통계, AI의 의사결정 이력 등은 관계형 데이터베이스인 PostgresDB에 누적됩니다. 
AI가 어떠한 `action_mask` 하에서 무슨 행동을 골랐는지 상세 데이터가 남습니다.

- **테이블 위치**: `game_logs` 테이블
- **DB 접속 정보 (로컬 DBeaver / pgAdmin 등)**:
  - **Host**: `localhost`
  - **Port**: `5432`
  - **User**: `puco_user`
  - **Password**: `puco_password`
  - **Database**: `puco_rl` 
- **DB 모니터링 쿼리 예시**:
  ```sql
  SELECT game_id, round, step, actor_id, action_data, state_before 
  FROM game_logs 
  ORDER BY created_at DESC 
  LIMIT 50;
  ```

## 3. 학습 가중치(.pth) 파일 적용 및 런타임 갱신 절차
외부 서버(클라우드) 또는 로컬에서 새롭게 학습된 PPO PyTorch 모델을 현재 서비스 중인 게임 서버에 탑재하는 무중단/경량 파이프라인입니다.

1. **학습된 모델 저장**:
   새로운 `.pth` 파일(예: `ppo_agent_update_200.pth`)을 `castest/castone/PuCo_RL/models/` 디렉터리에 복사합니다.

2. **환경변수 스왑(Docker Compose 적용)**:
   `castone/docker-compose.yml` 파일 내부 백엔드 서버(`backend`)의 환경변수 영역에 다음을 선언하거나 변경합니다.
   ```yaml
   services:
     backend:
       environment:
         - PPO_MODEL_FILENAME=ppo_agent_update_200.pth
   ```

3. **도커 컨테이너 재시작**:
   백엔드 컨테이너를 재기동하여 모델 가중치만 새롭게 메모리에 반영합니다. (DB나 Redis 상태는 보존됨)
   ```bash
   docker compose up -d --build backend
   ```
   *참고: `bot_service.py` 에서는 모델 가중치(`strict=False` 옵션 활용)를 로드하므로, Network Architecture(파라미터 형태)가 완전히 변경되지 않는 한 런타임 크래시 없이 즉각 새로운 지능이 적용됩니다.*
