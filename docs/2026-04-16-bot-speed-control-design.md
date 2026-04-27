# 봇전 배속 / 일시정지 설계서

> 날짜: 2026-04-16
> 범위: 봇전(전원 봇) 관전 모드 전용
> 상태: 승인됨

---

## 1. 개요

봇전 관전 시 게임 진행 속도를 조절하고 일시정지할 수 있는 기능.
현재 봇 턴 딜레이는 2~3초로 하드코딩되어 있으며, 사용자가 조절할 수 없다.

### 목표

- 배속: x1 / x2 / x4 순환 (버튼 클릭)
- 일시정지: 봇 턴 스케줄링 보류, 재개 시 이어서 진행
- 봇전 관전 모드에서만 동작 (전원 봇 게임)
- 게임별 독립 (다른 유저의 게임에 영향 없음)

### 비목표

- 사람+봇 혼합 게임에서의 배속
- 배속/일시정지 상태의 DB/Redis 영속화
- 리플레이 재생과의 통합

---

## 2. 데이터 모델

게임별 속도 상태를 `GameService` 클래스 변수로 메모리 관리:

```python
_game_speed: dict[str, int] = {}    # game_id -> 1 | 2 | 4
_game_paused: dict[str, bool] = {}  # game_id -> True | False
```

- 기본값: speed=1, paused=False
- 게임 종료(`_on_game_finished`) 시 해당 키 삭제
- DB/Redis 저장 없음 — 서버 재시작 시 x1로 리셋 (허용됨)
- 페이지 새로고침 시 프론트가 GET으로 현재 값 조회

---

## 3. Backend API

### 3.1 엔드포인트

| Method | Path | Body | 응답 | 설명 |
|--------|------|------|------|------|
| `GET` | `/api/puco/games/{game_id}/playback` | — | `{"speed": 1, "paused": false}` | 현재 상태 조회 |
| `POST` | `/api/puco/games/{game_id}/speed` | `{"speed": 2}` | `{"speed": 2}` | 속도 변경 |
| `POST` | `/api/puco/games/{game_id}/pause` | `{"paused": true}` | `{"paused": true}` | 일시정지/재개 |

### 3.2 권한 및 검증

- 모든 엔드포인트: `Authorization: Bearer <token>` 필수 (401)
- 게임이 존재하지 않거나 PROGRESS가 아닌 경우: 404
- **봇전 전용 검증**: 게임의 모든 플레이어가 `BOT_`으로 시작하지 않으면 403
  - 에러: `{"detail": "speed_control_bot_game_only"}`
- speed 값이 1, 2, 4가 아닌 경우: 422

### 3.3 일시정지 동작

```
pause(game_id, paused=True):
    _game_paused[game_id] = True
    # 현재 실행 중인 봇 턴의 sleep은 자연스럽게 끝남
    # 다음 _schedule_next_bot_turn_if_needed() 호출 시 스케줄링 건너뜀

pause(game_id, paused=False):
    _game_paused[game_id] = False
    # 즉시 _schedule_next_bot_turn_if_needed() 호출하여 재개
```

### 3.4 배속 동작

`bot_service.run_bot_turn()` 딜레이 계산 변경:

```python
# 현재 (하드코딩)
delay = 3.0 if is_role_selection else 2.0

# 변경 후
speed = GameService.get_game_speed(game_id)  # 1, 2, or 4
base_delay = 3.0 if is_role_selection else 2.0
delay = base_delay / speed
# x1: 2.0s / 3.0s
# x2: 1.0s / 1.5s
# x4: 0.5s / 0.75s
```

### 3.5 파일 위치

- `backend/app/api/channel/playback.py` — 새 라우터 (3개 엔드포인트)
- `backend/app/schemas/playback.py` — Pydantic 스키마
- `backend/app/main.py` — 라우터 등록
- `backend/app/services/game_service.py` — `_game_speed`, `_game_paused` 딕셔너리 + getter/setter
- `backend/app/services/bot_service.py` — 딜레이 계산 변경

---

## 4. Frontend UI

### 4.1 레이아웃

관전 상단 바에 배속/일시정지 컨트롤 추가:

```
┌─────────────────────────────────────────────────────┐
│  Puerto Rico    관전 중       [ x1 ] [ ❚❚ ] [나가기] │
└─────────────────────────────────────────────────────┘
```

- **배속 버튼** `[ x1 ]`: 현재 속도 표시, 클릭 시 x1 → x2 → x4 → x1 순환
- **일시정지 버튼** `[ ❚❚ ]`: 토글. 일시정지 중이면 `[ ▶ ]`로 변경
- **나가기 버튼**: 기존 로그아웃/나가기 버튼을 오른쪽 끝으로 이동

### 4.2 표시 조건

`isSpectator === true && isBotGame === true` 일 때만 렌더링.

`isBotGame` 판별: `room.players` 전원이 `BOT_`으로 시작하는지, 또는 봇전 생성 API로 만든 게임인지 확인.
→ 간단한 방식: `state.meta.player_order`의 모든 ID가 `BOT_`으로 시작하면 봇전.

### 4.3 상태 관리

```typescript
const [speed, setSpeed] = useState(1);
const [paused, setPaused] = useState(false);

// 마운트 시 GET /playback로 현재 상태 조회
// 버튼 클릭 시 POST /speed 또는 POST /pause 호출 후 로컬 상태 업데이트
```

### 4.4 파일 위치

- `frontend/src/components/GameScreen.tsx` — 관전 바에 버튼 추가
- `frontend/src/App.tsx` — `isBotGame` 판별 로직, playback 상태 prop 전달

---

## 5. TDD 테스트 계획

### 5.1 Backend 테스트 (`backend/tests/test_playback_api.py`)

| # | 테스트 | 검증 내용 |
|---|--------|-----------|
| 1 | `test_playback_requires_auth` | 토큰 없이 호출 시 401 |
| 2 | `test_speed_change_bot_game_only` | 사람 포함 게임에서 호출 시 403 |
| 3 | `test_speed_invalid_value` | speed=3 전송 시 422 |
| 4 | `test_speed_change_accepted` | speed=2 → 200, 응답 확인 |
| 5 | `test_speed_cycles_1_2_4` | 순차 변경 후 GET으로 확인 |
| 6 | `test_pause_accepted` | paused=true → 200 |
| 7 | `test_resume_accepted` | paused=false → 200 |
| 8 | `test_get_playback_default` | 초기 상태 speed=1, paused=false |
| 9 | `test_get_playback_after_change` | 변경 후 GET 값 반영 |
| 10 | `test_nonexistent_game_404` | 없는 game_id → 404 |

### 5.2 Backend 테스트 (`backend/tests/test_bot_speed_delay.py`)

| # | 테스트 | 검증 내용 |
|---|--------|-----------|
| 1 | `test_delay_at_speed_1` | 기본 딜레이 2.0초 |
| 2 | `test_delay_at_speed_2` | 딜레이 1.0초 |
| 3 | `test_delay_at_speed_4` | 딜레이 0.5초 |
| 4 | `test_role_selection_delay_at_speed_4` | 역할 선택 딜레이 0.75초 |
| 5 | `test_pause_blocks_scheduling` | paused=True 시 봇 턴 스케줄링 안 됨 |
| 6 | `test_resume_triggers_scheduling` | paused=False 후 봇 턴 재개 |

### 5.3 Frontend 테스트 (`frontend/src/components/__tests__/GameScreen.test.tsx` 확장)

| # | 테스트 | 검증 내용 |
|---|--------|-----------|
| 1 | `test_speed_buttons_visible_in_bot_spectator` | 봇전 관전 시 배속/일시정지 버튼 표시 |
| 2 | `test_speed_buttons_hidden_in_normal_game` | 일반 게임에서 미표시 |
| 3 | `test_speed_button_cycles` | 클릭 시 x1→x2→x4→x1 순환 |
| 4 | `test_pause_toggle_icon` | 일시정지 ❚❚ ↔ ▶ 전환 |
| 5 | `test_speed_button_calls_api` | 클릭 시 POST /speed 호출 확인 |
| 6 | `test_pause_button_calls_api` | 클릭 시 POST /pause 호출 확인 |

---

## 6. 구현 순서 (TDD)

```
T1. backend/app/schemas/playback.py — Pydantic 스키마
T2. backend/app/services/game_service.py — speed/paused 딕셔너리 + getter/setter
T3. backend/tests/test_playback_api.py — RED (API 테스트 먼저 작성)
T4. backend/app/api/channel/playback.py — GREEN (엔드포인트 구현)
T5. backend/app/main.py — 라우터 등록
T6. backend/tests/test_bot_speed_delay.py — RED (딜레이 테스트 작성)
T7. backend/app/services/bot_service.py — GREEN (딜레이 계산 변경)
T8. backend/app/services/game_service.py — pause 시 스케줄링 보류 로직
T9. frontend 테스트 작성 — RED
T10. frontend UI 구현 — GREEN (GameScreen + App.tsx)
T11. i18n 키 추가 (ko/en/it)
T12. contract.md 업데이트
```

---

## 7. 게임별 독립성 보장

```
User A: game_abc → speed=4, paused=false  (빠르게 관전 중)
User B: game_xyz → speed=1, paused=true   (일시정지 중)
User C: game_abc → speed=4, paused=false  (A와 같은 게임 관전)
```

- 속도/일시정지는 game_id 단위로 저장
- 같은 게임을 여러 명이 관전하면 동일한 속도 적용
- PPO 모델은 공유하지만 추론은 턴마다 독립 호출
- 일시정지는 "해당 게임의 봇 턴 스케줄링 보류"이므로 다른 게임에 영향 없음

---

## 8. 엣지 케이스

| 상황 | 처리 |
|------|------|
| 게임 종료 시 | speed/paused 딕셔너리에서 해당 game_id 삭제 |
| 서버 재시작 | 메모리 초기화 → 모든 게임 x1, 미정지 (허용됨) |
| 새로고침 | 프론트가 GET /playback으로 현재 상태 복원 |
| 일시정지 중 게임 종료 조건 충족 | 마지막 봇 턴이 이미 실행되었으므로 정상 종료 |
| 배속 변경 중 봇 턴 실행 중 | 현재 턴의 sleep은 기존 딜레이로 완료, 다음 턴부터 새 속도 적용 |
