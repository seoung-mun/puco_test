# Prod Channel Multiplayer + PPO Scenario Design

작성일: 2026-05-06
상태: draft
관련 문서: `error_logs.md`, `backend/tests/README.md`
관련 코드: `backend/app/api/channel/`, `backend/app/main.py`, `backend/app/services/agent_registry.py`, `backend/app/services/bot_service.py`, `PuCo_RL/env/pr_env.py`, `PuCo_RL/train/train_ppo_hybrid_server.py`

## 1. 목표와 비목표

### 1.1 목표

- `prod` Docker 환경에서 실제 운영 경로인 `channel` API (`/api/puco/*`) 기준으로 멀티플레이 시나리오를 검증한다.
- 사람 다수 멀티플레이 항목 중 서버가 자동 검증 가능한 핵심 항목을 시나리오 스크립트로 고정한다.
- PPO 서빙 경로가 현재 학습 축과 맞는 `obs_dim=293`, `action_dim=200` 계약을 유지하는지 검증한다.
- PPO가 실제 서빙 경로에서 mask 밖 액션을 고르지 않는지 확인한다.
- `legacy` API가 현재 프론트 기능에 영향이 없다면 `prod`에서만 비활성화하여 공개 표면을 줄인다.
- 사용자는 Docker 컨테이너에서 명령어만 실행하면 검증을 재현할 수 있어야 한다.

### 1.2 비목표

- 프론트엔드 브라우저 자동화 UI 테스트
- Google OAuth 실물 인증 흐름 검증
- `legacy` 코드 완전 삭제
- 운영 중 실제 사용자 게임 데이터 정리 또는 마이그레이션
- PPO 재학습 또는 모델 교체

## 2. 배경과 현재 판단

- 현재 프론트 참조는 `frontend/src/App.tsx`, `frontend/src/components/RoomListScreen.tsx`, `frontend/src/hooks/useGameWebSocket.ts` 기준 모두 `channel` 경로(`/api/puco/*`)를 사용한다.
- `legacy` 라우터는 `backend/app/main.py`에서 여전히 등록되지만, 현재 기능 경로에서 직접 사용되지 않는다.
- `backend` prod 이미지에는 `requests`, `websockets`, `psycopg2-binary`가 이미 포함되어 있다.
- 반면 `pytest`, `httpx`, `pytest-asyncio`는 dev dependency 쪽에 있어 prod 이미지에 없다.
- 따라서 prod 검증은 `pytest` 테스트 파일보다 `python` 실행형 시나리오 스크립트가 더 안전하고 이식성이 높다.
- 별도 `docker compose exec backend python ...`로 실행하는 스크립트는 실행 중인 uvicorn 프로세스의 메모리를 직접 볼 수 없다. 따라서 내부 검증은 DB/Redis 조회와 동일 이미지 안의 코드/모델 로컬 로딩으로 설계해야 한다.

## 3. 채택 접근

### 3.1 선택지 비교

1. `channel` 기반 실행형 prod 시나리오 + `legacy` prod 비활성화
2. `channel` 기반 실행형 prod 시나리오만 추가, `legacy` 유지
3. `legacy` 완전 제거 + `channel` 시나리오 전환

### 3.2 채택안

**1번**을 채택한다.

- 멀티플레이와 PPO 검증은 `prod` 백엔드 컨테이너 안에서 직접 실행하는 Python 시나리오 스크립트 2개로 구현한다.
- 시나리오 대상 API는 전부 `channel` 경로만 사용한다.
- `legacy`는 코드 삭제가 아니라 `prod`에서만 라우터 등록을 끄는 환경 토글 방식으로 비활성화한다.
- `legacy` 관련 기존 테스트와 로컬 개발 흐름은 즉시 깨지지 않도록 유지한다.

## 4. 산출물

다음 네 가지를 이번 작업의 구현 산출물로 둔다.

1. `backend/scripts/prod_scenario_common.py`
   - 테스트 전용 사용자 생성
   - JWT 발급
   - HTTP helper
   - WebSocket helper
   - DB/Redis 조회 helper
   - 생성된 테스트 데이터 cleanup helper

2. `backend/scripts/prod_channel_multiplayer_scenario.py`
   - `channel` 기반 멀티플레이 prod 시나리오

3. `backend/scripts/prod_ppo_contract_scenario.py`
   - PPO 입력/출력 계약 검증 시나리오

4. `backend/app/main.py` + `docker-compose.prod.yml`
   - `legacy` prod 비활성화 토글 추가

## 5. 아키텍처와 파일 책임

### 5.1 공통 helper (`prod_scenario_common.py`)

이 파일은 시나리오 공통 인프라만 담당한다.

- `SessionLocal` 기반 DB 세션 열기
- `User`, `GameSession`, `GameLog`, `Replay` CRUD helper
- `create_access_token()` 기반 JWT 발급
- `requests.Session` 기반 HTTP 요청 helper
- `websockets` 기반 lobby/game WS helper
- 시나리오 생성 자원 추적
  - 생성한 `user_id`
  - 생성한 `game_id`
  - 생성한 redis key prefix
- cleanup
  - `Replay` 삭제
  - `GameLog` 삭제
  - `GameSession` 삭제
  - 테스트 `User` 삭제
  - 생성된 게임 관련 Redis 키 삭제

### 5.2 멀티플레이 시나리오 (`prod_channel_multiplayer_scenario.py`)

책임:

- 실제 `prod` 서버에 HTTP/WS로 붙어 멀티플레이 규칙을 검증한다.
- 각 시나리오마다 외부 관찰 결과와 내부 상태를 함께 확인한다.
- 실패 시 어느 단계에서 어떤 응답/상태가 어긋났는지 사람이 바로 읽을 수 있게 출력한다.

### 5.3 PPO 시나리오 (`prod_ppo_contract_scenario.py`)

책임:

- 현재 prod 이미지 안의 PPO 번들/모델/어댑터 계약을 로컬 로딩으로 검증한다.
- 실제 prod 서버가 PPO 포함 게임을 시작하고 진행할 수 있는지 확인한다.
- 라이브 게임의 bot action 기록이 유효 범위 `0..199` 안에 있는지 확인하고, mask 준수는 동일 prod 이미지 안의 로컬 inference 계약으로 검증한다.

### 5.4 `legacy` 비활성화

`backend/app/main.py`에 다음 형태의 토글을 추가한다.

```python
_ENABLE_LEGACY_API = os.getenv("ENABLE_LEGACY_API", "true").lower() == "true"

if _ENABLE_LEGACY_API:
    app.include_router(legacy_router, prefix="/api", tags=["legacy"])
```

`docker-compose.prod.yml`의 `backend.environment`에는 아래를 추가한다.

```yaml
- ENABLE_LEGACY_API=false
```

이 방식의 장점:

- prod에서만 공개 표면을 줄일 수 있다.
- 로컬/기존 테스트/긴급 롤백은 env 값만 바꾸면 된다.
- `legacy` 의존성이 숨어 있더라도 코드 삭제보다 위험이 훨씬 작다.

## 6. 멀티플레이 시나리오 설계

### 6.1 대상 엔드포인트

- `POST /api/puco/rooms/`
- `GET /api/puco/rooms/`
- `POST /api/puco/rooms/{room_id}/join`
- `POST /api/puco/game/{room_id}/add-bot`
- `DELETE /api/puco/game/{room_id}/bots/{slot_index}`
- `POST /api/puco/game/{room_id}/start`
- `POST /api/puco/rooms/{room_id}/leave`
- `WS /api/puco/ws/lobby/{room_id}`
- `WS /api/puco/ws/{game_id}`
- `GET /api/puco/session/active-game`

### 6.2 인증 방식

실제 Google OAuth는 사용하지 않는다.

- 시나리오 스크립트가 DB에 테스트 전용 유저를 직접 생성한다.
- 각 유저에 대해 `create_access_token(subject=str(user.id))`로 JWT를 발급한다.
- 모든 HTTP 요청은 `Authorization: Bearer <token>` 헤더 사용
- 모든 WebSocket은 첫 메시지로 `{ "token": "<jwt>" }` 전송

이 방식은 prod 이미지 안에서 반복 실행 가능하고, 외부 Google 설정 의존성을 제거한다.

### 6.3 테스트 유저 정책

- 각 실행마다 고유 접두사(`prod-check-<timestamp>-<rand>`)를 만든다.
- `google_id`, `email`, `nickname`은 이 접두사 기반으로 충돌 없이 생성한다.
- 다른 운영 사용자와 격리된 데이터만 생성하고 정리한다.

### 6.4 시나리오 목록

#### 시나리오 A: prod에서 `legacy` 비활성화 확인

- `POST /api/multiplayer/init` 호출 시 `404` 기대
- `POST /api/lobby/start` 호출 시 `404` 기대
- 목적: prod 공개 표면에서 `legacy` 제거가 실제 반영되었는지 확인

#### 시나리오 B: 대기방 정원 제한

- Host가 방 생성
- Host가 bot 1개 추가
- 사람 1명 입장하여 `2인 + 봇1` 상태 구성
- 추가 사람 1명이 `join` 시 `409` 기대
- 내부 검증:
  - DB `games.players` 길이 == 3
  - `status == "WAITING"`
  - `host_id` 불변

#### 시나리오 C: 비방장 권한 제한

- Host가 방 생성 후 bot 1개 추가
- Bob이 입장하여 `사람 2명 + 봇 1개` 직전 상태를 구성
- Bob이 아래 요청을 시도:
  - `POST /game/{id}/start`
  - `POST /game/{id}/add-bot`
  - `DELETE /game/{id}/bots/{slot}`
- 모두 `403` 기대
- 내부 검증:
  - DB `players`, `status`, `host_id` 변화 없음

#### 시나리오 D: 사람 1자리 동시 입장 경쟁

- Host가 방 생성 후 bot 1개 추가
- 두 유저가 거의 동시에 `join`
- 기대:
  - 한 명 `200`
  - 한 명 `409`
  - DB 최종 `players` 길이 == 3
- 목적:
  - “빈 사람 슬롯 하나에 2명 이상 동시 입장” 처리 확인

#### 시나리오 E: 마지막 슬롯 봇 추가 vs 사람 입장 경쟁

- Host + 사람 1명 상태의 방 생성
- Host의 `add-bot`과 다른 사람의 `join`을 동시에 발사
- 기대:
  - 정확히 하나만 성공
  - 최종 `players` 길이 == 3
  - 절대 `4`가 되지 않음
- 내부 검증:
  - DB 최종 row 확인
  - lobby WS `LOBBY_UPDATE` payload와 DB 상태 일치 확인

#### 시나리오 F: 시작 후 방 목록 노출 변화

- WAITING 방이 목록에 보이는지 확인
- Host가 `start`
- 이후 `GET /rooms/`에서 같은 방이 사라지는지 확인
- 목적:
  - “게임이 시작된 방이 로비에서 어떻게 보이나” 서버 계약 검증

#### 시나리오 G: 플레이 중 사람 이탈 알림

- Host + Bob + bot 1개 조합으로 게임 시작
- Host와 Bob 모두 game WS 연결
- Bob 연결 해제 또는 `leave` 유도
- Host WS에서 `PLAYER_DISCONNECTED` 이벤트 수신 기대
- 내부 검증:
  - Redis `game:{id}:players` 에서 Bob 상태가 `disconnected`
  - DB `games.status` 확인
  - 필요 시 host transfer 또는 room 상태 변화 확인

### 6.5 시나리오 실행 규칙

- 각 시나리오는 독립 room/game을 생성한다.
- 실패 시 그 시나리오의 생성 자원을 남길지 cleanup할지 CLI 옵션으로 제어한다.
- 기본값은 cleanup 수행이다.
- 디버깅을 위해 `--keep-artifacts-on-failure` 옵션을 둔다.

### 6.6 출력 형식

각 시나리오는 아래 구조로 출력한다.

```text
[PASS] scenario_b_capacity_limit
[PASS] scenario_c_non_host_permissions
[FAIL] scenario_e_bot_vs_join_race
  expected: one success + one 409
  actual: add-bot=200 join=200 final_players=4
```

프로세스 종료 코드는 하나라도 실패하면 `1`, 전부 통과하면 `0`이다.

## 7. PPO 계약 시나리오 설계

### 7.1 검증 목적

사용자 요청의 “PPO 에이전트가 정확한 인풋/아웃풋을 지키는지 판단”을 prod 이미지 기준으로 고정한다.

이 시나리오는 세 층을 검증한다.

1. **번들/메타데이터 계약**
2. **로컬 inference 계약**
3. **라이브 서버 동작 계약**

### 7.2 번들/메타데이터 계약

다음을 확인한다.

- `ppo` bot type이 현재 bundle 기반 서빙을 사용 중인지
- bundle manifest가 존재하는지
- manifest의 `obs_dim == 293`
- manifest의 `action_dim == 200`
- adapter module이 semantic293 계열인지
- 현재 prod 이미지의 champion bundle 이름이 기대값과 일치하는지

이 검증은 `backend/app/services/agent_registry.py`, `backend/app/services/model_registry.py`, `PuCo_RL/models/.../manifest.json` 기준으로 수행한다.

### 7.3 로컬 inference 계약

이 검증은 실행 중 서버 메모리가 아니라 동일 prod 이미지 안의 코드/모델 로딩으로 수행한다.

절차:

- 로컬에서 `create_game_engine(num_players=3)` 생성
- 현재 `ppo` wrapper 또는 adapter runtime 로딩
- 관측/마스크를 encoder 또는 wrapper 경로에 넣어 단일 inference 실행
- 다음을 assert:
  - flatten/adapter 결과 input 길이 == 293
  - mask 길이 == 200
  - 반환 action은 `0 <= action < 200`
  - 반환 action이 현재 mask에서 허용된 값

이 검증은 `pr_env.py`와 `train_ppo_hybrid_server.py`가 공유하는 축과 현재 prod 서빙 artifact가 어긋나지 않았는지 확인하는 최소 계약이다.

### 7.4 라이브 서버 계약

절차:

- 테스트 전용 host 유저 생성
- `POST /api/puco/rooms/bot-game` 에 `{"bot_types": ["ppo", "random", "random"]}` 전송
- 응답이 `200`이며 state가 반환되는지 확인
- DB `GameSession`과 `GameLog`를 조회
- 다음을 assert:
  - 게임이 실제 생성됨
  - 진행 중 또는 종료 상태로 정상 전이
  - `GameLog.action_data` 에 기록된 bot action index가 모두 `0 <= action_index < 200`

이 1차 버전의 라이브 계약은 `GameLog.available_options` 파싱에 의존하지 않는다. 이유는 해당 필드의 저장 형태가 시점별로 흔들릴 수 있어 prod 시나리오를 불필요하게 깨뜨릴 가능성이 있기 때문이다.

따라서 **mask-validity의 공식 합격 기준은 §7.3 로컬 inference 계약**으로 둔다. 라이브 서버 계약은 아래 세 가지를 보장하면 합격이다.

1. 현재 서빙 메타데이터가 `293/200` 계약과 일치한다.
2. 동일 prod 이미지 안의 로컬 inference가 mask를 지킨다.
3. 라이브 서버가 PPO 포함 게임을 실제로 시작하고 bot action을 유효 범위 `0..199` 안에 기록한다.

### 7.5 health 보조 확인

PPO 시나리오 시작 전 또는 종료 후 `/health/runtime`를 조회해 다음을 확인한다.

- `checks.serving.status` 가 `ok`
- `artifact_name` 이 `agent_registry`가 현재 `ppo` bot type에 대해 resolve한 champion artifact 이름과 일치

이 검증은 prod 서빙 degraded 상태를 빠르게 감지하기 위한 보조 확인이다.

## 8. cleanup 전략

원격 또는 prod 성격의 데이터 오염을 막기 위해 cleanup을 기본 동작으로 한다.

정리 순서:

1. 생성한 room/game ID 목록 수집
2. 해당 game의 `Replay` 삭제
3. 해당 game의 `GameLog` 삭제
4. 해당 `GameSession` 삭제
5. 생성한 test user 삭제
6. 생성한 Redis key 정리

제약:

- cleanup은 **이번 스크립트가 생성한 ID에만** 적용한다.
- 기존 운영 데이터는 절대 건드리지 않는다.

## 9. 오류 처리와 안전장치

### 9.1 안전장치

- base URL 기본값은 `http://127.0.0.1:8000`
- 스크립트는 `--base-url` 변경 시 명시적으로 출력한다
- cleanup 대상은 전부 실행 중 생성한 ID로만 제한한다
- `legacy` 비활성화는 env 토글이라 문제가 생기면 compose env만 되돌리면 된다

### 9.2 실패 시 진단 정보

실패 시 아래 정보를 출력한다.

- HTTP status/body
- WS에서 받은 마지막 이벤트
- DB room row 요약 (`status`, `players`, `host_id`)
- Redis player state 요약
- PPO 시나리오의 경우 bundle manifest 요약 (`bundle_id`, `obs_dim`, `action_dim`)

## 10. 구현 후 실행 명령

구현 완료 후 사용자는 아래 순서로 실행한다.

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend python scripts/prod_channel_multiplayer_scenario.py --base-url http://127.0.0.1:8000
docker compose -f docker-compose.prod.yml exec backend python scripts/prod_ppo_contract_scenario.py --base-url http://127.0.0.1:8000
```

디버깅 목적으로 생성 데이터를 남기고 싶다면:

```bash
docker compose -f docker-compose.prod.yml exec backend python scripts/prod_channel_multiplayer_scenario.py --base-url http://127.0.0.1:8000 --keep-artifacts-on-failure
docker compose -f docker-compose.prod.yml exec backend python scripts/prod_ppo_contract_scenario.py --base-url http://127.0.0.1:8000 --keep-artifacts-on-failure
```

## 11. 수용 기준

- prod compose에서 `legacy` 경로가 비활성화된다.
- 멀티플레이 시나리오 스크립트가 `channel` 경로만 사용해 실행된다.
- 사람 다수 멀티플레이 핵심 항목이 PASS/FAIL로 구분되어 출력된다.
- PPO 시나리오가 `obs_dim=293`, `action_dim=200`, valid masked action 계약을 검증한다.
- 두 스크립트 모두 비정상 시 종료 코드 `1`, 정상 시 `0`.
- cleanup 기본 동작으로 테스트 데이터가 남지 않는다.

## 12. 구현 분해

후속 implementation plan에서는 아래 순서로 분해한다.

1. `legacy` prod 비활성화 토글 추가
2. 공통 helper 스크립트 작성
3. 멀티플레이 시나리오 작성
4. PPO 계약 시나리오 작성
5. prod compose 기준 실행 검증
6. 실패 메시지와 cleanup 보강

## 13. 결정 로그

- prod 검증은 `pytest`가 아니라 실행형 Python 스크립트로 간다. 이유는 prod 이미지에 dev test dependency가 없기 때문이다.
- 인증은 Google OAuth 대신 DB 직생성 사용자 + JWT 발급으로 간다. 이유는 반복 실행성과 외부 의존성 제거 때문이다.
- `legacy`는 삭제가 아니라 prod 비활성화다. 이유는 현재 기능 회귀 위험 없이 보안 표면만 줄이는 것이 목적이기 때문이다.
- PPO 검증은 live HTTP 결과만으로 끝내지 않고, 동일 prod 이미지 안의 로컬 wrapper/adapter inference 계약까지 함께 본다.
