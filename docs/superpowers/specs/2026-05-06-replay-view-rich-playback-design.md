# Replay View Rich Playback Design

작성일: 2026-05-06
범위: `frontend/` 리플레이 상세 화면 UX 개선
관련 파일:
- `frontend/src/components/ReplayViewScreen.tsx`
- `frontend/src/components/GameScreen.tsx`
- `frontend/src/hooks/useReplayPlayer.ts`
- `frontend/src/components/__tests__/ReplayViewScreen.test.tsx`
- `frontend/src/components/__tests__/GameScreen.test.tsx`
- `frontend/src/hooks/__tests__/useReplayPlayer.test.ts`
- `frontend/src/locales/ko.json`
- `frontend/src/locales/en.json`
- `frontend/src/locales/it.json`

## 1. 문제 정의

현재 리플레이 상세 화면은 각 프레임의 `rich_state`를 실제 게임 화면으로 렌더링하지 않고, `<pre>` 안에 JSON 문자열로 그대로 출력한다.

그 결과 사용자 눈에는:

- 게임이 진행되는 느낌이 전혀 없음
- 봇전/실시간 경기처럼 보드 변화가 보이지 않음
- 리플레이가 아니라 디버그 덤프처럼 보임
- 프레임 이동은 가능해도 왜 해당 프레임이 중요한지 이해하기 어려움

사용자 기대는 “리플레이를 보면 실제 Puerto Rico 화면이 진행되는 것처럼 보여야 한다”는 것이다.

## 2. 목표

### 핵심 목표

- `ReplayViewScreen`에서 현재 프레임의 `rich_state`를 `GameScreen`으로 렌더링한다.
- 사용자는 JSON이 아니라 실제 보드/플레이어 패널/히스토리/메타 정보를 본다.
- 재생 컨트롤은 유지하되, 리플레이 전용 읽기 모드로 동작한다.

### UX 목표

- 상단에서 게임 라벨과 뒤로 가기를 확인할 수 있다.
- 재생, 일시정지, 이전/다음 프레임, 10프레임 점프, 시크바, 배속 변경이 가능하다.
- 현재 프레임의 액션/코멘터리를 별도 정보 카드에서 볼 수 있다.
- 아래 본문은 실제 `GameScreen`이 렌더되어 게임 진행처럼 느껴진다.

### 비목표

- 리플레이 도중 액션을 실제로 실행하거나 서버 상태를 바꾸지 않는다.
- WebSocket/SSE 연결을 새로 붙이지 않는다.
- 리플레이 전용 별도 보드 컴포넌트를 새로 만들지 않는다.

## 3. 현재 코드 상태

### 이미 존재하는 좋은 기반

- `ReplayViewScreen.tsx`: 리플레이 상세 fetch와 기본 컨트롤 UI가 이미 있음
- `useReplayPlayer.ts`: 프레임 재생 상태 머신이 이미 있음
- `GameScreen.tsx`: 전체 게임 보드를 렌더링하는 메인 화면이 이미 있음
- `replayMode?: boolean`: `GameScreen`에 이미 존재

### 현재 결함

- `ReplayViewScreen.tsx`가 `frame.rich_state`를 `JSON.stringify(...)`로 출력함
- `GameScreen.tsx` 일부 인터랙티브 블록이 `replayMode`가 아니라 `isBlocked`만 보고 렌더링됨
- `useReplayPlayer.ts`는 새 리플레이/새 프레임 집합이 들어올 때 현재 프레임과 재생 상태를 명시적으로 reset하지 않음

## 4. 설계 원칙

### 원칙 1. 기존 `GameScreen` 재사용

리플레이 전용 보드를 새로 만들지 않는다. 실제 게임 화면과 리플레이 화면이 시각적으로 달라지면 유지보수와 UX 일관성이 모두 깨진다.

### 원칙 2. 리플레이는 완전 읽기 전용

리플레이에서 보이는 버튼/선택 UI는 사용자가 실제 액션을 시도할 수 없도록 차단되어야 한다.

### 원칙 3. JSON 디버그 출력 제거

사용자 화면에서 raw JSON은 제거한다. 액션 텍스트와 commentary는 별도 정보 카드로 보여주되, 상태 본문은 게임 화면으로만 보여준다.

### 원칙 4. 기존 테스트 자산을 유지하며 작은 단위로 보강

새 구조는 기존 테스트 범위 위에 얹어서 보호한다.

## 5. 구현 설계

### 5.1 `ReplayViewScreen.tsx`

`ReplayViewScreen`의 책임을 아래처럼 정리한다.

#### 데이터 로드

- `GET /api/puco/replays/{gameId}` 호출
- 새 게임 ID로 진입할 때:
  - `detail` 초기화
  - loading 상태 true
  - notFound/error 초기화

#### 재생 상태

- `useReplayPlayer({ frames })` 사용 유지
- 사용할 값:
  - `currentFrame`
  - `frame`
  - `isPlaying`
  - `speed`
  - `prev`
  - `next`
  - `seek`
  - `stepForward`
  - `toggle`
  - `setSpeed`

#### 상단 UI

- 뒤로 가기 버튼
- `display_label`
- 로딩 / 404 / noFrames 메시지

#### 컨트롤 카드

- `-10`, `이전`, `재생/일시정지`, `다음`, `+10`
- 시크바
- 배속 selector
- 현재 프레임 표시

#### 프레임 정보 카드

- `step`
- `action`
- `commentary`

#### 본문

- `frame.rich_state`를 `GameScreen`에 주입
- 반드시 `replayMode={true}`
- 서버와 상호작용하는 모든 콜백은 no-op
- `onReturnToRooms`는 뒤로 가기와 연결 가능

### 5.2 `GameScreen.tsx`

`GameScreen`은 리플레이 모드에서 “보이기만 하고 동작하지 않는 화면”이 되어야 한다.

#### 리플레이 모드에서 숨길 것

- 맨 위 app header (`Puerto Rico`, `새 게임`, 언어 전환, 로그아웃/관전 badge`)
- `pendingSettlement` overlay
- `craftsman privilege` 선택 overlay
- trader/captain/discard action-card 영역

이유:

- 이 블록들은 실제 사용자 입력을 강하게 요구하거나, replay view의 상위 컨트롤과 역할이 겹친다.
- 일부 버튼은 현재 `interactionLocked`를 보지 않으므로, 노출 시 read-only 계약이 쉽게 깨진다.

#### 리플레이 모드에서 유지할 것

- Meta panel
- 공용 보드
- 플레이어 패널
- San Juan
- History panel
- 엔드게임 패널
- 턴/메타 정보

#### 리플레이 모드에서 허용되는 read-only 시각 정보

- active player highlight
- mayor legal slot highlight (클릭 핸들러 없이)
- history 누적 상태

### 5.3 `useReplayPlayer.ts`

새 리플레이가 로드되거나 프레임 목록이 새 배열로 교체되면:

- 현재 프레임을 0으로 reset
- 재생 상태를 paused로 reset
- 기존 timer를 정리

이유:

- 한 리플레이에서 다른 리플레이로 넘어갈 때 이전 재생 상태가 새 게임에 누수되면 UX가 깨진다.

## 6. 구현 슬라이스

이번 작업은 아래 한 묶음으로 구현한다.

### Task A. Rich replay rendering

완료 조건:

- `ReplayViewScreen`이 더 이상 raw JSON을 출력하지 않는다.
- `GameScreen`이 실제로 렌더링된다.
- 재생 컨트롤이 정상 동작한다.
- replayMode에서 인터랙티브 오버레이가 노출되지 않는다.
- 새 replay 데이터 로드 시 player hook이 reset된다.

대상 파일:

- `frontend/src/components/ReplayViewScreen.tsx`
- `frontend/src/components/GameScreen.tsx`
- `frontend/src/hooks/useReplayPlayer.ts`
- 관련 테스트/locale 파일

## 7. 구체 acceptance criteria

아래 항목이 모두 만족되어야 한다.

1. 리플레이 상세 화면에서 `<pre>` JSON dump가 사라진다.
2. 첫 프레임 로드시 `GameScreen` 기반 UI가 보인다.
3. `다음` 버튼으로 프레임 이동 시 현재 action 카드 정보가 갱신된다.
4. 재생 중 마지막 프레임에 도달하면 자동 정지한다.
5. 새 replay frames가 로드되면 프레임 인덱스는 0으로 돌아가고 재생 상태는 pause 된다.
6. `replayMode=true`일 때 `GameScreen` 상단 앱 헤더가 보이지 않는다.
7. `replayMode=true`일 때 선택형 overlay/trader-captain action-card가 노출되지 않는다.
8. 기존 일반 게임 화면의 pass button disable 동작은 유지된다.

## 8. 테스트 설계

### `ReplayViewScreen.test.tsx`

보호할 것:

- detail fetch 성공 시 `GameScreen`이 replayMode로 렌더링되는지
- next 버튼으로 frame info가 갱신되는지
- 404 notFound 상태
- back 버튼 동작
- HTTP 오류 상태

테스트 전략:

- `GameScreen`은 가벼운 proxy mock으로 대체해도 됨
- 이 테스트의 목적은 “실제 보드를 호출하는 wiring” 보호이지, `GameScreen` 자체 렌더링 품질 검증이 아님

### `useReplayPlayer.test.ts`

추가 보호:

- frames 교체 시 frame index reset
- frames 교체 시 paused reset

### `GameScreen.test.tsx`

추가 보호:

- `replayMode=true`일 때 상단 header 숨김
- 기존 pass button disable 보호 유지

## 9. 리스크와 대응

### 리스크 1. `GameScreen` 요구 state shape가 커서 리플레이 테스트가 무거워질 수 있음

대응:

- `ReplayViewScreen` 테스트에서는 `GameScreen`을 proxy mock으로 대체

### 리스크 2. replayMode에서 일부 인터랙티브 UI가 여전히 살아남을 수 있음

대응:

- overlay/action-card 진입 조건에 `!replayMode`를 명시적으로 추가

### 리스크 3. 기존 일반 게임 UI 회귀

대응:

- 변경은 replayMode 분기에만 한정
- 일반 게임 관련 기존 테스트를 함께 돌림

## 10. 구현자 지침

구현자는 아래를 반드시 지킨다.

- 기존 사용자 변경을 되돌리지 않는다
- 현재 워크트리는 dirty 상태일 수 있으므로 unrelated change를 건드리지 않는다
- replay UI 문제를 해결하기 위해 새 보드 컴포넌트를 만들지 않는다
- `GameScreen` 재사용 원칙을 지킨다
- 테스트는 최소 아래 세 묶음을 우선 실행한다
  - `frontend/src/components/__tests__/ReplayViewScreen.test.tsx`
  - `frontend/src/hooks/__tests__/useReplayPlayer.test.ts`
  - `frontend/src/components/__tests__/GameScreen.test.tsx`

## 11. 리뷰 체크리스트

### Spec review checklist

- 실제 게임 화면이 렌더되는가
- raw JSON 출력이 제거되었는가
- replayMode read-only 계약이 지켜지는가
- 새 replay 로드시 player state reset이 되는가
- 스코프 밖 구조 변경이 없는가

### Code quality checklist

- no-op handler 정리가 과하지 않은가
- 조건 분기가 replayMode에 한정되어 있는가
- 테스트가 wiring과 behavior를 정확히 보호하는가
- locale 키 추가가 필요한 최소 수준인가
