# TODO — Puerto Rico AI Battle Platform

> 마지막 업데이트: 2026-03-25

---

## 완료됨 ✅

### ML 파이프라인 / 학습-서빙 정합성

- [x] `bot_service.py` 전면 재작성 — `PhasePPOAgent`(HPPO) + `Agent`(PPO) 분기 지원
- [x] 서빙 추론 시 페이즈 컨디셔닝 적용 (`obs_dict["global_state"]["current_phase"]`)
- [x] Obs space를 클래스 변수로 1회 캐시 (추론당 dummy env 생성 제거)
- [x] 모델 로딩 `strict=True` + 실패 시 `strict=False` 폴백
- [x] `EngineWrapper.max_game_steps` 50,000 → 1,200 (학습 환경 동일 값)
- [x] `.env` 및 `.env.example`에 `MODEL_TYPE` / `HPPO_MODEL_FILENAME` 문서화

### 엔진 버그 수정

- [x] `PuCo_RL/env/pr_env.py` — Builder 마스크에 도시 보드 슬롯 체크 추가
  - 대형 건물: 2칸 필요, 소형: 1칸 필요
  - `p.empty_city_spaces < spaces_needed` 시 건물 액션 비활성화

### API 스키마

- [x] `GameAction.game_id` / `GameAction.action_type` → Optional (클라이언트 호환성)

### TDD 엣지케이스 테스트

- [x] `PuCo_RL/tests/test_phase_edge_cases.py` — 엔진 수준 엣지케이스 (5개 페이즈 전체)
- [x] `PuCo_RL/tests/test_mayor_sequential.py` — Mayor 순차 배치 테스트 + `agent_selection` 동기화 버그 수정
- [x] `backend/tests/test_phase_action_edge_cases.py` — API 수준 엣지케이스 44개
  - 인증(401), IDOR(403), 페이로드(400), 마스크 거부, 턴 순서, 페이즈별 규칙

### 테스트 버그 수정

- [x] `test_building_slot_capacity_matches_building_data` — Mayor 규칙 반영 (min_place 수정)
- [x] `test_pass_valid_in_craftsman_phase` — 생산 강제 후 페이즈 진입 확인
- [x] `test_reserved_action_terminates_env` — 예약 액션은 no-op (env 종료 안 함)
- [x] `test_second_user_cannot_act_on_first_users_turn` — 랜덤 거버너 인식 로직 적용

---



# 현재 문제점

- 시장, 상인, 선장 페이즈에서 봇은 그냥 패스했다고만 로그에서 뜸
- 실제로 db에 어떻게 저장되는지 확인 필요

- 개척자, 건축가 페이즈가 2번 반복되는 경우가 존재
- 엣지 케이스 제작 후 테스트 권장








## 즉시 처리 권장 🔥

### 검증 및 측정

- [ ] `max_game_steps=1200` 적합성 검증 — 실제 Puerto Rico 게임 평균 스텝 수 측정
- [ ] Builder 마스크 버그 수정 후 기존 HPPO 모델 성능 변화 확인 (재학습 필요 여부 결정)

### CI/CD 인프라

- [ ] `backend/tests/test_phase_action_edge_cases.py` CI 파이프라인 통합
  - 필요 인프라: PostgreSQL + Redis (테스트 컨테이너 or docker-compose)
- [ ] `PuCo_RL/tests/` pytest 자동화 (GitHub Actions / 로컬 pre-commit hook)

### 알려진 미결 이슈

- [ ] `env/pr_env.py` — UU(Unmerged) 상태 (`git status` 기준) → conflict 해소 및 커밋 필요
- [ ] `train_hppo_selfplay.py` / `train_ppo_selfplay.py` 삭제됨, 관련 문서/참조 정리 필요

---

## 중기 (Near-term) 📋

### 봇 서비스 개선

- [ ] `BotService` 핫 스왑 지원 — 프로세스 재시작 없이 모델 교체
- [ ] HPPO 모델 파일 없을 때 Graceful degradation 개선 (현재: 미초기화 가중치로 실행)

### API / 스키마 개선

- [ ] `GameAction.action_type` 필드 목적 명확화 또는 스키마에서 제거
- [ ] IDOR 보호 확인: `/api/v1/game/{id}/action` 진입 전 `current_user.id ∈ room.players` 검증

### 코드 품질

- [ ] `BUILDING_DATA` 인덱스를 named constant로 추출 (예: `LARGE_BUILDING_FLAG_IDX = 4`)
- [ ] 예약 액션(111-199) 처리 명문화 — 의도된 no-op인지 미구현 기능인지 주석/문서 추가
- [ ] `engine_wrapper/wrapper.py` — `max_game_steps` 를 환경변수로 설정 가능하게

---

## 장기 (Long-term) 🔮

### 테스트

- [ ] `env/pr_env.py` 마스크 생성 로직 전체에 속성 기반 테스트(property-based testing) 도입 (Hypothesis)
- [ ] 학습 환경 하이퍼파라미터 단일 config 파일 관리 (`configs/train_config.yaml`) → 학습-서빙 자동 동기화

### 모델 / 학습

- [ ] 새 마스크(도시 슬롯 포함)로 HPPO 재학습 및 성능 비교
- [ ] 리그 서버(`train_hppo_league_server.py`) 학습 결과 평가 (`evaluate_balance.py`, `evaluate_tournament.py`)

### 인프라

- [ ] Redis Pub/Sub WebSocket 브로드캐스트 부하 테스트
- [ ] PostgreSQL `game_logs` 테이블 파티셔닝 (round 기준) 운영 환경 적용
- [ ] Docker 멀티스테이지 빌드 최적화 (현재 이미지 크기 측정 후 판단)

---

## 참고 문서

- 변경 상세 보고서: [`docs/CHANGES_REPORT.md`](docs/CHANGES_REPORT.md)
- 아키텍처: [`docs/castone_architecture.md`](docs/castone_architecture.md)
- API 명세: [`docs/castone_api_spec.md`](docs/castone_api_spec.md)
- TDD 엣지케이스 목록: [`docs/castone_tdd_edge_cases.md`](docs/castone_tdd_edge_cases.md)
- MLOps 보고서: [`docs/report/mlops_data_tracking_report.md`](docs/report/mlops_data_tracking_report.md)
