# Replay System Design Spec

작성일: 2026-04-14 (개정: 2026-04-15)
범위: `backend/` replay logging 확장, 새 REST API, `frontend/` 리플레이 UI
원칙: PuCo_RL 수정 없음. 기존 GameScreen 재활용. broadcast 시점만 기록.
참고: `contract.md` Section 2 (API 패턴), Section 5 (Naming Contract), Section 6 (Persistence)

---

## 1. 목표

### 기능 목표

- 완료된 게임을 웹에서 실제 게임 진행처럼 리플레이 재생 (기존 GameScreen 재활용)
- 배속(1x/2x/4x/8x), 일시정지, step 이동 지원
- UUID 대신 사람이 식별하기 좋은 `display_label` 사용 (`MM_DD_Player1_Player2_Player3_NN`)

### UI 흐름 목표

- 로비 → [리플레이] 버튼 → 리플레이 전용 UI 진입
- 리플레이 UI에서 플레이어명(사람 닉네임 또는 봇 타입) 정확 일치 검색
- 검색 결과 10개씩 페이지네이션 (`1 2 3 4 ... 10 > >>` 형태)
- 행 클릭 → "이 게임을 리플레이 하시겠습니까?" 확인 다이얼로그 → Yes 시 리플레이 진입

## 2. 배포 전 선행 작업

- 기존 `data/logs/replay/` 및 `data/logs/games/` 파일 전부 삭제 (테스트/엔진 변경분)
- 기존 v1 replay 파일이 모두 삭제되므로 v1→v2 마이그레이션 로직 불필요
- `_base_payload()`의 `"format"` 값을 `"backend-replay.v2"`로 변경

## 3. Backend — Replay 로깅 변경

### 3.1 ReplayLogger 확장

`ReplayLogger.append_entry()`에 optional `rich_state` 파라미터 추가.

```python
# replay_logger.py — append_entry 시그니처 변경
def append_entry(
    *,
    game_id, title, status, host_id, players, model_versions,
    entry,
    rich_state: dict | None = None,      # 새 파라미터
    final_scores=None, result_summary=None,
):
```

- `rich_state`가 전달되면 entry에 `"rich_state": rich_state` 필드 추가
- `rich_state`가 None이면 기존과 동일 (summary만 저장)

### 3.2 game_service.py 변경

`process_action()` 내에서 ReplayLogger 호출 시점 변경:

```python
# 현재 (line 262-272): 항상 replay entry 기록
# 변경 후:
if room:
    ReplayLogger.append_entry(
        ...,
        entry=replay_entry,
        rich_state=rich_state if not suppress_broadcast else None,  # broadcast 시점만
        final_scores=replay_final_scores,
        result_summary=replay_result_summary,
    )
```

### 3.3 저장 효과

| 시나리오 | 현재 entries | rich_state entries |
| --- | --- | --- |
| 일반 액션 (역할선택, 건축 등) | 1 | 1 (동일) |
| 봇 Mayor batch (colonist 5명) | 5 | 1 (마지막만) |
| 한 게임 전체 (~140 step) | ~140 | ~100-120 |

### 3.4 game_service.py — winner_id 설정 누락 수정

현재 `process_action()`에서 게임 종료 시 `room.status = "FINISHED"`는 설정하지만
`room.winner_id`는 설정하지 않는 버그가 있음. 리플레이 목록에서 승자 표시를 위해 함께 수정:

```python
if result.get("terminated", result["done"]) and room:
    room.status = "FINISHED"
    replay_final_scores, replay_result_summary = build_final_scores_payload(...)
    # 추가: winner_id 설정
    winner_entry = next((s for s in replay_final_scores if s.get("winner")), None)
    if winner_entry:
        room.winner_id = winner_entry.get("actor_id")
```

### 3.5 replay JSON 포맷 변경

`display_label`은 파일에 저장하지 않음 (API 응답 시 동적 생성).

```json
{
  "format": "backend-replay.v2",
  "game_id": "...",
  "players": [...],
  "entries": [
    {
      "step": 1,
      "action": "Select Role: Settler",
      "commentary": "...",
      "rich_state": { "meta": {...}, "common_board": {...}, "players": {...}, ... },
      "state_summary_before": {...},
      "state_summary_after": {...}
    },
    {
      "step": 42,
      "action": "Mayor: Place colonist on City slot 3",
      "commentary": "...",
      "rich_state": null,
      "state_summary_before": {...},
      "state_summary_after": {...}
    }
  ]
}
```

- `rich_state` 있는 entry = 리플레이 프레임 (프론트가 렌더할 단위)
- `rich_state` 없는 entry = 배치 로그 (ML/감사 용도, 리플레이에서는 건너뜀)

## 4. Backend — Replay REST API

### 4.1 엔드포인트

```
GET /api/puco/replays/                       — 게임 목록 + 검색
GET /api/puco/replays/{game_id}              — 리플레이 상세 데이터
```

Bearer 인증 필요 (contract.md Section 2 패턴 동일).

### 4.2 GET /api/puco/replays/

GameSession 테이블에서 `status='FINISHED'` 쿼리.
모든 필드는 DB 컬럼에서만 읽음 (replay 파일 접근 없음 → O(1) per row).

**쿼리 파라미터:**

| 파라미터 | 타입 | 기본값 | 설명 |
| --- | --- | --- | --- |
| `page` | int | 1 | 1-based 페이지 번호 |
| `size` | int | 10 | 페이지당 항목 수 (UI 명세 고정 10) |
| `player` | str | (없음) | 플레이어명 정확 일치 검색 (사람 닉네임 또는 봇 타입) |

**검색 로직 (`player` 파라미터):**

- `GameSession.players` JSONB의 각 항목 `display_name` 필드와 정확 일치 (대소문자 무시)
- 사람 닉네임: 그대로 비교 (예: `성문`)
- 봇 타입: bot type 토큰과 비교 (예: `Random`, `PPO`, `HPPO`)
- 매칭 SQL: PostgreSQL JSONB 연산자 활용 (`players @> '[{"display_name": "성문"}]'`)
- 검색어 trim 및 lowercase 정규화 후 비교 (저장된 값도 동일 정규화)

**필드 출처:**

- `index`: 검색 결과 전체 기준 1-based 절대 순번 (`(page-1)*size + i + 1`)
- `display_label`: DB 데이터로 동적 생성 (저장하지 않음)
- `human_player_names`: `players` JSONB에서 `is_bot=false`인 항목만 추출, `display_name` 알파벳 오름차순 정렬
- `winner`: `GameSession.winner_id` → 해당 player의 display_name으로 변환
- `played_date`: `GameSession.created_at`을 `YYYY-MM-DD` 형식으로 포맷

**응답:**

```json
{
  "replays": [
    {
      "index": 1,
      "game_id": "000563f2-97cd-4a4e-b30d-a4b867af9259",
      "display_label": "04_13_Random_PPO_성문_01",
      "human_player_names": ["성문"],
      "played_date": "2026-04-13",
      "created_at": "2026-04-13T12:30:00Z",
      "num_players": 3,
      "winner": "성문",
      "players": [
        {"display_name": "Random", "is_bot": true},
        {"display_name": "PPO", "is_bot": true},
        {"display_name": "성문", "is_bot": false}
      ]
    }
  ],
  "page": 1,
  "size": 10,
  "total_items": 47,
  "total_pages": 5
}
```

정렬: `created_at DESC` (최신순).

### 4.3 display_label 생성 로직

```
{MM}_{DD}_{Player1}_{Player2}_{Player3}_{NN}
```

- 봇: bot type (`Random`, `PPO`, `HPPO`, `RuleBased` 등) — `players` JSONB의 `display_name` 그대로
- 사람: 닉네임 (고유값 — contract.md Section 2.2 보장)
- `NN`: 같은 날짜 + 같은 플레이어 조합 내에서 `created_at` 순 번호 (`01`, `02`, ...)
- label은 DB에 저장하지 않고 쿼리 시 동적 생성 (window function 또는 그룹 카운트)
- 게임 삭제 시 순번 재계산 필요 없음 (현재 존재하는 것만 기준으로 동적 부여)

### 4.4 GET /api/puco/replays/{game_id}

DB 메타 + `data/logs/replay/{game_id}.json`에서 entries 로드.

- `rich_state`가 있는 entries만 필터링해서 `replay_frames` 배열로 제공
- 프론트는 `replay_frames`만 순회하면 됨
- `display_label`은 DB 데이터로 동적 생성

**응답:**

```json
{
  "game_id": "...",
  "display_label": "04_13_Random_PPO_성문_01",
  "players": [...],
  "replay_frames": [
    { "frame_index": 0, "step": 0, "action": "...", "rich_state": {...} },
    { "frame_index": 1, "step": 1, "action": "...", "rich_state": {...} }
  ],
  "total_frames": 120,
  "final_scores": [...]
}
```

### 4.5 에러 핸들링

| 상황 | 응답 |
| --- | --- |
| 검색 결과 0건 | 200 + `replays: []`, `total_pages: 0` |
| `page`가 `total_pages` 초과 | 200 + `replays: []` (방어적, 404 안 함) |
| `game_id`가 DB에 없음 | 404 Not Found |
| DB에 있지만 replay 파일 없음 | 404 + `{"detail": "replay_file_not_found"}` |
| `replay_frames`가 0개 (rich_state 없음) | 200 + `replay_frames: []`, 프론트에서 "리플레이 데이터 없음" 표시 |
| `status`가 FINISHED가 아닌 game_id 직접 접근 | 404 |

### 4.6 구현 위치

- 새 파일: `backend/app/api/replay.py` — router
- 새 파일: `backend/app/schemas/replay.py` — Pydantic 응답 스키마
- `backend/app/main.py` 또는 router 등록부에 추가

## 5. Frontend — 리플레이 UI

### 5.1 화면 흐름

```
LobbyScreen (기존)
  └─ [리플레이] 버튼 (상단)
       └─ ReplayListScreen (새)
            ├─ 검색 바 (플레이어명 정확 일치)
            ├─ 결과 리스트 (10개/페이지)
            ├─ 페이지네이션 (1 2 3 4 ... 10 > >>)
            └─ 행 클릭 → 확인 다이얼로그 → Yes
                 └─ ReplayViewScreen (새)
                      └─ GameScreen (기존, read-only 모드)
```

### 5.2 라우팅

`App.tsx`에 추가:

```
/replay          → ReplayListScreen
/replay/:gameId  → ReplayViewScreen
```

`LobbyScreen`의 [리플레이] 버튼이 `/replay`로 이동.

### 5.3 ReplayListScreen — 상세 설계

#### 5.3.1 레이아웃

```
┌─────────────────────────────────────────────────────────┐
│  ← 로비로                              리플레이 목록     │
├─────────────────────────────────────────────────────────┤
│  [🔍 플레이어명 검색  ___________ ] [검색] [초기화]      │
├─────────────────────────────────────────────────────────┤
│  #  │ 게임 ID                  │ 플레이어     │ 날짜    │
│ ────┼──────────────────────────┼─────────────┼─────────│
│  1  │ 04_13_Random_PPO_성문_01 │ 성문         │ 04-13   │
│  2  │ 04_13_Random_Random_지영 │ 지영         │ 04-13   │
│  3  │ 04_12_PPO_성문_지영_01   │ 성문, 지영   │ 04-12   │
│  ...                                                     │
├─────────────────────────────────────────────────────────┤
│         <<  <  1  2  3  4  ...  10  >  >>             │
└─────────────────────────────────────────────────────────┘
```

#### 5.3.2 컬럼 정의

| 컬럼 | 데이터 출처 | 비고 |
| --- | --- | --- |
| `#` | 응답의 `index` | 검색 결과 전체 기준 절대 순번 |
| 게임 ID | 응답의 `display_label` | 사람이 식별 가능한 라벨 |
| 플레이어 | 응답의 `human_player_names` | 알파벳순, 콤마 구분, 사람만 |
| 날짜 | 응답의 `played_date` | `YYYY-MM-DD` 또는 로케일 포맷 |

봇 정보는 리스트에서 보이지 않음 (이미 `display_label`에 포함됨).

#### 5.3.3 검색 동작

- 검색 입력 + [검색] 버튼 클릭 → `GET /api/puco/replays/?player={value}&page=1&size=10`
- [초기화] 버튼 → 검색어 클리어 + page 1로 리셋, `?page=1&size=10`
- 빈 검색어로 [검색] 클릭 → `player` 파라미터 없이 전체 목록 조회
- Enter 키 = [검색] 버튼 동작
- 검색 결과 0건 → "검색 결과가 없습니다" 메시지

#### 5.3.4 페이지네이션 동작

페이지네이션 컴포넌트 동작:

| 버튼 | 동작 |
| --- | --- |
| `<<` | 1페이지로 이동 (현재 page=1이면 비활성/숨김) |
| `<` | 이전 페이지 (현재 page=1이면 비활성/숨김) |
| `1 2 3 ...` | 클릭한 페이지로 이동 |
| `>` | 다음 페이지 (마지막이면 비활성) |
| `>>` | 마지막 페이지로 이동 (마지막이면 비활성) |

UI 명세의 `1 2 3 4 ... 10 > >>` 표기는 **page=1 상태**의 표시이며, 이 때는 `<<`/`<` 버튼이 비활성/숨김 처리되어 보이지 않음.

페이지 번호 표시 규칙:

- 전체 페이지 ≤ 7: 모든 페이지 번호 표시 (`1 2 3 4 5 6 7`)
- 전체 페이지 > 7: 현재 페이지 주변 ± 2개 + 처음/끝 + `...`로 축약
  - 예: 현재 5/20 → `1 ... 3 4 5 6 7 ... 20`
  - 예: 현재 1/20 → `1 2 3 4 5 ... 20`
  - 예: 현재 18/20 → `1 ... 16 17 18 19 20`

검색 상태는 페이지 이동 시 유지 (`player` 쿼리 그대로).

#### 5.3.5 행 클릭 → 확인 다이얼로그

행 클릭 시 모달 다이얼로그 표시:

```
┌─────────────────────────────────────┐
│  리플레이를 시청하시겠습니까?       │
│                                     │
│  04_13_Random_PPO_성문_01           │
│  플레이어: 성문                      │
│  날짜: 2026-04-13                   │
│                                     │
│              [취소]    [시청]        │
└─────────────────────────────────────┘
```

- [시청] → `navigate(/replay/${game_id})` → ReplayViewScreen 진입
- [취소] / 배경 클릭 / ESC → 모달 닫기, 목록 유지
- 다이얼로그는 reusable Modal 컴포넌트로 (없으면 새로 작성)

### 5.4 ReplayViewScreen

#### 5.4.1 데이터 로드

- 마운트 시 `GET /api/puco/replays/{game_id}` 호출
- 로딩 중: 스피너 표시
- 404 또는 `replay_frames: []` → "리플레이 데이터를 불러올 수 없습니다" 표시 + 목록으로 돌아가기 버튼

#### 5.4.2 핵심 상태

```typescript
interface ReplayState {
  frames: ReplayFrame[]     // rich_state가 있는 entries만
  currentFrame: number      // 0 ~ totalFrames-1
  isPlaying: boolean
  playbackSpeed: number     // 1, 2, 4, 8
}
```

#### 5.4.3 렌더링 구조

```
┌─────────────────────────────────────┐
│  ← 목록  04_13_Random_PPO_성문_01   │ 타이틀 (display_label)
├─────────────────────────────────────┤
│                                     │
│   GameScreen (read-only)            │ frames[currentFrame].rich_state를
│   기존 게임 화면 그대로              │ GameScreen에 props로 주입
│                                     │
├─────────────────────────────────────┤
│  ◀◀  ◀  ▶/⏸  ▶  ▶▶               │ 컨트롤바
│  ──●────────────────── 42/120      │ 시크바 + 프레임 표시
│  [1x] [2x] [4x] [8x]             │ 배속 선택
│                                     │
│  [현재 액션] Select Role: Settler   │ 현재 프레임의 action 텍스트
└─────────────────────────────────────┘
```

#### 5.4.4 재생 로직

- `▶` → `setInterval(1000ms / speed)`로 `currentFrame++`
- `⏸` → interval 클리어
- `◀◀` / `▶▶` → 10프레임 점프
- `◀` / `▶` → 1프레임 이동
- 시크바 드래그 → 임의 프레임 이동
- 마지막 프레임 도달 → 자동 정지, 최종 스코어 표시 (EndGamePanel 재활용)

#### 5.4.5 GameScreen 연동

- GameScreen에 `replayMode?: boolean` prop 추가
- `replayMode=true`일 때:
  - 액션 버튼 비활성화 (클릭 불가)
  - WebSocket/SSE 연결 건너뜀
  - state를 외부 props에서 받음 (기존: WebSocket/SSE에서 받음)
- 기존 게임 플레이에는 영향 없음 (`replayMode` 미전달 시 기존 동작)
- contract.md Section 2.6 게임 WebSocket 계약과 충돌 없음 (replayMode는 WS 연결 자체 안 함)

### 5.5 새 파일 목록

| 파일 | 역할 |
| --- | --- |
| `frontend/src/components/ReplayListScreen.tsx` | 리플레이 목록 화면 + 검색 + 페이지네이션 |
| `frontend/src/components/ReplayViewScreen.tsx` | 리플레이 재생 화면 + 컨트롤바 |
| `frontend/src/components/ReplayConfirmModal.tsx` | 리플레이 시청 확인 다이얼로그 |
| `frontend/src/components/Pagination.tsx` | 페이지네이션 컴포넌트 (재사용 가능하게) |
| `frontend/src/hooks/useReplayPlayer.ts` | 재생 상태 관리 hook (play/pause/speed/seek) |
| `frontend/src/hooks/useReplayList.ts` | 목록/검색/페이지 상태 관리 hook |
| `frontend/src/types/replay.ts` | Replay 관련 타입 정의 |

### 5.6 기존 파일 수정

| 파일 | 변경 |
| --- | --- |
| `App.tsx` | 라우팅 추가 (`/replay`, `/replay/:gameId`) |
| `LobbyScreen.tsx` | 상단에 [리플레이] 버튼 추가 |
| `GameScreen.tsx` | `replayMode` prop 추가, read-only 분기 |
| `locales/ko.json`, `en.json`, `it.json` | 리플레이 관련 번역 키 추가 |

### 5.7 i18n 키 (예시)

```
replay.title           "리플레이 목록"
replay.search.placeholder  "플레이어명 정확 일치 검색"
replay.search.button   "검색"
replay.search.reset    "초기화"
replay.search.empty    "검색 결과가 없습니다"
replay.column.index    "#"
replay.column.gameId   "게임 ID"
replay.column.players  "플레이어"
replay.column.date     "날짜"
replay.confirm.title   "리플레이를 시청하시겠습니까?"
replay.confirm.watch   "시청"
replay.confirm.cancel  "취소"
replay.view.back       "← 목록"
replay.view.action     "현재 액션"
replay.view.error      "리플레이 데이터를 불러올 수 없습니다"
```

## 6. 향후 ML 파이프라인 확장 방향 (이번 구현 범위 아님)

현재 구조에서 향후 확장 포인트만 기록:

```
게임 진행 → MLLogger → JSONL (S,A,R,S' + action_mask)
                         ↓
              [향후] transition 수집기 → 일정량 모이면 자동 학습 트리거
                         ↓
              PuCo_RL/train/ 스크립트 외부 래퍼로 호출 (PuCo_RL 수정 없이)
                         ↓
              새 모델 → model_registry 등록 → A/B 평가
```

- `MLLogger`의 JSONL 포맷은 이미 학습에 필요한 데이터 포함 → 변경 불필요
- 확장 시 `backend/app/services/`에 파이프라인 서비스 추가
- `PuCo_RL/` 수정 없음

## 7. 테스트 전략 (TDD)

룰: Docker에서만 테스트. 비즈니스 로직 엣지케이스 위주. import 에러 체크 X.

### Backend 테스트

| 테스트 파일 | 검증 내용 |
| --- | --- |
| `test_replay_api_list.py` | FINISHED 게임만 반환, 페이징, 정렬(최신순), `index` 절대 순번 |
| `test_replay_api_search.py` | 사람 닉네임 정확 일치, 봇 타입 정확 일치, 0건 검색, 대소문자 무시 |
| `test_replay_api_detail.py` | game_id로 replay 데이터 반환, replay_frames 필터링, 파일 없음 404 |
| `test_replay_display_label.py` | label 포맷, 같은 날짜+조합 중복 시 순번 부여, 게임 삭제 후 재계산 |
| `test_replay_rich_state_logging.py` | broadcast 시점에만 rich_state 저장, suppress 시 null |
| `test_replay_winner_id_set.py` | 게임 종료 시 winner_id가 DB에 정상 기록되는지 |
| `test_human_player_names_sort.py` | 사람만 추출 + 알파벳 오름차순 정렬 |

### Frontend 테스트

| 테스트 파일 | 검증 내용 |
| --- | --- |
| `ReplayListScreen.test.tsx` | API 호출, 목록 렌더링, 검색 입력, 0건 메시지 |
| `Pagination.test.tsx` | `<< < 1 2 ... > >>` 표시 규칙, 비활성 상태, 클릭 핸들러 |
| `ReplayConfirmModal.test.tsx` | 모달 열고 닫기, [시청] 클릭 시 navigate, ESC 닫기 |
| `ReplayViewScreen.test.tsx` | 프레임 네비게이션, 배속, 일시정지, 마지막 프레임 자동 정지 |
| `useReplayPlayer.test.ts` | hook 상태 관리 (play/pause/speed/seek) |
| `useReplayList.test.ts` | 검색/페이지/초기화 상태 흐름 |
| `GameScreen.test.tsx` (기존 확장) | `replayMode=true` 시 액션 버튼 비활성화, WS 연결 안 함 |

### TDD 적용 순서

각 기능은 다음 순서로 진행:

1. 실패하는 테스트 작성 (Red)
2. 최소 코드로 통과 (Green)
3. 리팩터 (Refactor)

엣지케이스 우선:

- 검색 결과 0건
- 페이지 초과 접근
- replay 파일 누락
- rich_state 0개 게임
- 봇 타입과 닉네임이 같은 경우 (예: 닉네임 "Random") → 둘 다 매칭

## 8. contract.md 갱신 필요 항목

이 기능 완료 후 `contract.md`에 추가:

### Section 2에 추가

```markdown
### 2.8 Replay

- `GET /api/puco/replays/`
- `GET /api/puco/replays/{game_id}`

계약:

- 두 엔드포인트 모두 bearer 인증이 필요하다.
- 목록은 `status='FINISHED'` 게임만 반환한다.
- `display_label` 포맷은 `MM_DD_Player1_Player2_Player3_NN`이며 응답 시 동적으로 생성된다.
- `?player=<name>` 정확 일치 검색을 지원한다 (사람 닉네임 또는 봇 타입, 대소문자 무시).
- 페이지 크기 기본은 10이며 정렬은 `created_at DESC`다.
- `replay_frames`는 `rich_state`가 있는 entry만 필터링한 배열이다.
- 게임이 DB에 없거나 status가 FINISHED가 아니면 404다.
- 게임은 있으나 replay 파일이 없으면 404 + `detail: "replay_file_not_found"`다.
```

### Section 6에 추가

```markdown
- replay JSON v2: `data/logs/replay/{game_id}.json`
  - format key: `"backend-replay.v2"`
  - broadcast 시점(`suppress_broadcast=False`)에만 entry에 `rich_state` 포함
  - suppressed step은 summary만 저장, 리플레이 재생에서 건너뜀
```

### `process_action` 동작 변경 반영

Section 2.5 `action` 계약에 다음 항목 추가:

```markdown
- 게임 종료 시 `room.winner_id`가 final_scores의 winner actor_id로 설정된다.
```
