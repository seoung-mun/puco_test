# Mayor Sequential Cutover Design

작성일: 2026-04-13
대상 저장소: `puco_test`
참조 upstream: `https://github.com/dae-hany/PuertoRico-BoardGame-RL-Balancing.git`
실제 확인한 branch: `origin/refactor/mayor-sequential-placement`
관련 문서: `contract.md`, `design/dual_mayor_engine_design.md`

## 1. Understanding Summary

- 현재 로컬 기준 Castone의 supported Mayor contract는 `69-71` 단일 전략 선택이다.
- 프론트는 `MayorStrategyPanel`을 통해 전략 3개 버튼만 노출한다.
- channel API는 sequential Mayor를 공식적으로 비지원하며 `mayor-distribute` 공개 경로도 닫혀 있다.
- 다만 코드베이스 안에는 과거 sequential Mayor 흔적과 legacy route 일부가 남아 있다.
- 요청사항의 핵심은 Mayor를 다시 "순차 배치"로 바꾸되, 이미 지나간 선택은 되돌릴 수 없게 만드는 것이다.
- 이 변경은 `PuCo_RL`만 바꾸면 끝나지 않고 backend contract, bot handling, frontend UI/test, replay/fingerprint까지 함께 바꿔야 안전하다.
- 테스트는 단순 import 검증이 아니라 실제 비즈니스 규칙과 엣지 케이스 중심으로 작성하고, 실행도 Docker Compose 경로만 사용해야 한다.
- 사람은 토글 방식으로 하되, 마찬가지로 한 mayor 페이즈에서 한 선택은 되돌릴 수 없다
  - 일단 프론트에서 모든 선택을 받고, 그걸 백엔드에서 순차 방식으로 처리되게끔 한다.



## 2. Current State Diagnosis

### 2.1 Contract 기준 현재 정식 Mayor 계약

`contract.md` 기준 현재 supported action band는 다음과 같다.

- `69-71`: Mayor strategy
- `72-75`: 현재 public contract에서는 비지원
- 비지원 항목
  - `POST /api/puco/game/{game_id}/mayor-distribute`
  - sequential Mayor cursor/meta (`mayor_slot_idx`, `mayor_can_skip`)
  - slot-by-slot Mayor placement REST / public contract

즉, 지금 시스템은 "전략 1회 선택 -> 엔진이 한번에 배치 완료"를 정식 계약으로 보고 있다.

### 2.2 실제 코드 기준 현재 상태

관찰 결과:

- `PuCo_RL/env/pr_env.py`
  - Mayor에서 실제로 처리하는 액션은 `69-71` 뿐이다.
- `PuCo_RL/env/engine.py`
  - `action_mayor_strategy()`는 존재한다.
  - 현재 엔진 본문에는 순차 Mayor용 `action_mayor_place()` 및 cursor state가 사실상 표준 경로로 살아 있지 않다.
- `backend/app/api/channel/game.py`
  - sequential Mayor distribution은 `410`으로 막아 둔 상태다.
- `frontend/src/components/GameScreen.tsx`
  - Mayor phase에서 `MayorStrategyPanel`만 렌더링한다.
- `frontend/src/components/MayorStrategyPanel.tsx`
  - 전략 버튼 3개, preview 문구, 69/70/71 action index를 하드코딩한다.
- `backend/app/services/bot_service.py`
  - Mayor에서는 invalid action이 들어와도 `69-71`로 normalize 한다.
- `backend/app/services/scenario_regression.py`
  - Mayor 회귀 시나리오가 `expected_actions={69,70,71}`, `forbidden_actions={72,73,74,75}`를 전제한다.
- `backend/app/services/model_registry.py`
  - fingerprint가 `castone.action-space.strategy-first.v1`, `castone.mayor.strategy-first.v1`에 고정되어 있다.

### 2.3 Legacy 코드는 그대로 복원해도 안 되는 이유

`backend/app/api/legacy/actions.py`에는 `mayor-place`, `mayor-finish-placement`, `mayor-distribute` 흔적이 남아 있다. 하지만 이것을 그대로 public contract로 되살리는 것은 위험하다.

이유:

- 현재 channel API 흐름과 분리되어 있다.
- 현재 `action_translator.py`에는 `mayor_toggle()`가 없다.
- 현재 serializer contract는 cursor metadata를 더 이상 내려주지 않는다.
- 현재 frontend는 slot-based interactive UI를 렌더링하지 않는다.
- 현재 bot safety, replay logging, scenario regression은 strategy-first 가정 위에 서 있다.

결론:

- "남아 있는 레거시를 노출"하는 접근은 권장하지 않는다.
- "현행 channel contract 위에서 sequential Mayor를 다시 정의"하는 접근이 더 안전하다.

### 2.4 Baseline Docker Test Snapshot

실제 Docker Compose 환경에서 확인한 기준선은 아래와 같다.

- backend strategy-first Mayor 계약 테스트: green
- frontend strategy-first Mayor UI 테스트: green
- `PuCo_RL` sequential/dual-mayor 계열 테스트: red

의미:

- 현재 제품 레이어는 아직 strategy-first Mayor 계약에 맞춰져 있다.
- upstream `PuCo_RL` Mayor semantics를 그대로 수용하면 backend/frontend 계약 조정이 반드시 뒤따라야 한다.

## 3. Branch Import Command Playbook

사용자가 원하는 것은 upstream repo의 `refactor/mayor-*` 브랜치 내용을 현재 저장소의 `PuCo_RL` 폴더에 반영하는 것이다.

실제 clone 후 확인한 결과, 현재 remote에 존재하는 Mayor 관련 브랜치는 아래 하나다.

- `origin/refactor/mayor-sequential-placement`

또한 이 브랜치는 내가 초기에 가정했던 `72-75 amount-based sequential`이 아니라,
Mayor를 "slot-direct sequential"로 바꾼다.

- `120-131`: island slot 0-11에 colonist 1명 배치
- `140-151`: city slot 0-11에 colonist 1명 배치
- `69-71` strategy band는 이 브랜치에서 제거되는 방향이다.

현재 로컬 repo의 `origin`은 별도 저장소(`seoung-mun/puco_test`)이므로, upstream remote를 따로 추가하는 방식이 가장 안전하다.

### 3.1 안전한 기본 순서

```bash
cd /Users/seoungmun/Documents/agent_dev/castone/puco_test

# 1) upstream remote 추가
git remote add puco-upstream https://github.com/dae-hany/PuertoRico-BoardGame-RL-Balancing.git

# 2) mayor 관련 브랜치만 fetch
git fetch puco-upstream 'refs/heads/refactor/mayor-*:refs/remotes/puco-upstream/refactor/mayor-*'

# 3) remote branch 확인
git branch -r | rg 'puco-upstream/refactor/mayor-'
```

### 3.2 가져오기 전에 diff만 먼저 확인

```bash
BRANCH='puco-upstream/refactor/mayor-sequential-placement'

git diff --stat main.."$BRANCH" -- PuCo_RL
git diff main.."$BRANCH" -- PuCo_RL/env PuCo_RL/tests
```

이 단계에서 반드시 확인할 것:

- action index가 바뀌는지
- `PuCo_RL/env/engine.py`, `PuCo_RL/env/pr_env.py` 둘 다 바뀌는지
- `PuCo_RL/tests`가 같이 바뀌는지

### 3.3 실제로 `PuCo_RL`만 작업 트리에 반영

```bash
git switch -c feat/mayor-sequential-cutover

# upstream branch의 PuCo_RL 폴더만 현재 작업 트리에 덮어오기
git restore --source "$BRANCH" --worktree --staged -- PuCo_RL

# 결과 확인
git status --short
git diff --cached --stat
```

### 3.4 worktree로 별도 검토하고 싶은 경우

```bash
git worktree add ../puco_test-mayor-review "$BRANCH"
```

이 방식은 upstream branch 전체 내용을 별도 디렉터리에서 검토할 수 있어, `PuCo_RL`만 옮겨와도 되는지 판단할 때 유용하다.

### 3.5 중요한 주의점

실제 diff 기준 이 브랜치는 `PuCo_RL` 엔진만 건드리는 작은 브랜치가 아니다.

주요 변경 파일:

- `env/engine.py`
- `env/pr_env.py`
- `agents/shipping_rush_agent.py`
- `tests/test_engine.py`
- `tests/balance_test.py`
- `tests/test_mayor_strategy.py` 삭제
- 일부 train 스크립트

`PuCo_RL`만 가져오는 것은 다음 조건일 때만 안전하다.

- upstream branch가 엔진 내부 로직만 바꾼다.
- backend/frontend action contract를 건드리지 않는다.

하지만 이번 Mayor 변경은 contract break 가능성이 높다. 따라서 이번 설계는 아래 첫 번째 경로를 전제로 한다.

- upstream branch의 `PuCo_RL`를 기준 구현으로 반영한다.
- 같은 작업 안에서 로컬 `backend`/`frontend`를 새 Mayor contract에 맞춰 함께 수정한다.

## 4. Design Options

### Option A. Upstream-Compatible Full Sequential Cutover

정의:

- Human/Bot 모두 Mayor를 slot-direct sequential action으로 처리한다.
- `120-131`: island slot direct placement
- `140-151`: city slot direct placement
- `69-71` strategy band는 제거하거나 더 이상 legal하지 않게 만든다.

장점:

- 단일 Mayor semantics
- 문서와 실제 동작이 단순해진다

단점:

- 현재 bot wrapper와 모델 정책이 깨질 수 있다
- replay/model fingerprint 전면 수정 필요
- 기존 Mayor strategy 회귀 테스트를 전부 다시 써야 한다
- RL 재학습 또는 adapter가 사실상 필요하다

-- a로 확정 그리고 봇은 파일로 된 룰 베이스의 봇들 제외하고, 모델 파일로 된 봇들은 새롭게 저 방식대로 학습된 모델을 따로 줄거야
/Users/seoungmun/Documents/agent_dev/castest/castone/PuertoRico-BoardGame-RL-Balancing/PPO_PR_Server_hybrid_selfplay_curriculum_5billion_from_scratch_20260412_122638_step_481689600.pth
이 파일이야

### Option B. Recommended For Castone: Human Sequential, Bot Strategy 유지

정의:

- Human player는 sequential Mayor를 사용한다.
- Bot player는 기존 strategy band (`69-71`)를 유지한다.
- backend는 `player_control_modes`를 기준으로 human/bot Mayor contract를 분기한다.

장점:

- 사용자 요구사항인 "순차 배치, 한번 선택하면 수정 불가"를 human UX에 정확히 반영할 수 있다
- existing bot/model investment를 최대한 보존할 수 있다
- `dual_mayor_engine_design.md`의 일부 사고 구조를 재사용할 수 있다

단점:

- Mayor contract가 actor type에 따라 달라진다
- serializer와 frontend에 cursor metadata를 다시 열어 줘야 한다
- 테스트 축이 2개(human sequential, bot strategy)로 늘어난다

### Option C. Frontend-only Sequential Illusion

정의:

- UI는 sequential처럼 보이게 하지만 실제 서버 액션은 여전히 69-71 전략 선택만 보낸다.

장점:

- 구현이 가장 작다

단점:

- 요구사항을 충족하지 못한다
- 실제 배치 결과와 UI 단계가 어긋날 수 있다
- 디버깅이 가장 어려워진다

결론:

- 일반론으로는 `Option B`가 Castone 운영 리스크가 더 낮다.
- 하지만 현재 사용자가 명시적으로 선택한 방향은
  - upstream branch를 그대로 `PuCo_RL`에 반영
  - `backend/frontend`를 그 계약에 맞게 수정
- 따라서 본 작업의 실제 기준안은 `Option A. Upstream-Compatible Full Sequential Cutover`로 고정한다.

## 5. Selected Design

이 문서의 나머지 구현 설계는 `Option A`를 기준으로 읽는다.

- `PuCo_RL`는 upstream `refactor/mayor-sequential-placement`를 그대로 반영한다.
- Mayor action contract는
  - `120-131`: island slot direct placement
  - `140-151`: city slot direct placement
- `69-71` strategy band는 더 이상 Mayor public contract가 아니다.

## 5.1 Product Rule

새 Mayor UX 규칙:

- Mayor turn의 actor는 human/bot 구분 없이 같은 sequential contract를 사용한다.
- 아마 봇과 사람 플레이어 기준으로 좀 다르게 해야할거야
- 봇은 engine.py, pr_env.py 대로 학습됬을거라 그것대로 해야하고,
- 사람은 ux를 위해 토글 방식으로 선택하되, 한 페이즈 당 한번 선택하면 되돌릴수 없게 
- action은 "현재 legal한 island/city slot 중 하나 선택"이다.
- 선택 직후 해당 slot은 즉시 확정된다.
- 이미 선택해 점유된 slot은 다시 수정할 수 없다.
- 별도의 cursor 이동이나 skip action은 두지 않는다.
- 현재 player의 unplaced colonists가 0이 되거나 legal slot이 더 없으면 다음 player로 넘어간다.

bot 규칙:

- bot도 같은 sequential slot-direct action contract를 사용한다.
- bot policy/heuristic은 현재 합법 빈 슬롯 중 하나를 골라야 한다.

## 5.2 PuCo_RL 변경 설계

핵심 대상:

- `PuCo_RL/env/engine.py`
- `PuCo_RL/env/pr_env.py`
- `PuCo_RL/agents/shipping_rush_agent.py`
- `PuCo_RL/tests/test_engine.py`
- `PuCo_RL/tests/balance_test.py`

### 엔진 변경 방향

이번 작업에서 `PuCo_RL`는 "부분 이식"보다 "upstream branch를 source of truth로 삼는 교체"에 가깝다.

핵심 규칙:

- `69-71` Mayor strategy path는 더 이상 Mayor 표준 경로가 아니다.
- Mayor turn의 legal action은 빈 섬 슬롯과 아직 수용 인원이 남은 도시 슬롯만 노출한다.
- slot 하나를 선택할 때마다 colonist 1명이 즉시 해당 위치에 확정 배치된다.
- 같은 slot을 다시 수정하는 action은 존재하지 않는다.
- 남은 colonist가 0이 되거나 더 이상 합법 슬롯이 없으면 다음 player로 넘어간다.
- human/bot 모두 같은 Mayor action band를 사용한다.

실제 upstream branch 기준 action space:

- `120-131`: island slot `0-11`
- `140-151`: city slot `0-11`

엔진 레벨에서 맞춰야 할 포인트:

- `engine.step()`이 Mayor에서 `120-131`, `140-151`만 처리하도록 유지
- `action_mayor_place_colonist(player_idx, is_city, slot_idx)`를 Mayor의 단일 진입점으로 사용
- `valid_action_mask()`가 빈 섬 타일, 수용 인원이 남은 건물만 legal로 켜도록 유지
- `action_mayor_strategy()`와 `player_control_modes` 기반 Mayor 분기를 local backend/frontend에서 더 이상 가정하지 않도록 정리

주의할 점:

- upstream `pr_env.py`에는 `unplaced_colonists >= empty_slots`일 때 Mayor auto-fill을 일부 수행하는 경로가 있다.
- 이 동작을 그대로 유지할지, backend UX 혼선을 줄이기 위해 auto-action 범위를 축소할지는 통합 시점에 명시적으로 결정해야 한다.
- 설계 권장안은 "합법 choice가 1개뿐인 경우에만 auto-action"으로 제한하는 것이다.

### "한번 선택하면 바꿀 수 없음"을 엔진에서 보장하는 방식

이 규칙은 프론트에서 막는 것만으로는 부족하고, 엔진이 보장해야 한다.

중요:

- 실제 upstream branch는 amount-choice가 아니라 slot-direct sequential이다.
- 즉 "현재 슬롯에 몇 명 넣을지"가 아니라 "지금 배치할 빈 슬롯 하나를 선택"하는 방식이다.

필수 원칙:

- 배치 직후 해당 slot은 occupancy/capacity 상태가 바뀌므로 mask에서 즉시 사라진다.
- 이미 colonist가 들어간 plantation slot은 다시 legal해지지 않는다.
- capacity가 찬 building slot은 다시 legal해지지 않는다.
- 이전 선택을 취소하는 action band나 toggle route를 두지 않는다.

즉, "undo"와 "toggle" 개념을 액션 스페이스에서 제거한다. irreversibility는 cursor가 아니라 "slot state의 즉시 변경"으로 보장된다.

### 제안하는 엔진 테스트 포인트

- 빈 plantation slot만 `120 + slot_idx`로 legal해야 함
- 빈 building capacity가 남은 slot만 `140 + slot_idx`로 legal해야 함
- 이미 점유된 plantation에 다시 배치하려 하면 에러여야 함
- capacity가 찬 building에 다시 배치하려 하면 에러여야 함
- `69-71`은 Mayor에서 legal하면 안 됨
- 마지막 colonist를 놓거나 마지막 legal slot을 채우면 다음 player로 정확히 넘어가야 함

## 5.3 Backend 변경 설계

핵심 대상:

- `backend/app/services/game_service_support.py`
- `backend/app/services/state_serializer.py`
- `backend/app/services/action_translator.py`
- `backend/app/services/bot_service.py`
- `backend/app/services/scenario_regression.py`
- `backend/app/services/replay_logger.py`
- `backend/app/api/channel/game.py`
- `backend/app/engine_wrapper/wrapper.py`

### backend contract 변경 원칙

channel API는 계속 `POST /api/puco/game/{game_id}/action` 단일 엔드포인트를 유지한다.

변경점은 payload shape가 아니라 Mayor legal action band와 action 설명 체계다.

- Mayor turn 전체 legal actions:
  - `120-131`: island slot direct placement
  - `140-151`: city slot direct placement
- `69-71`은 더 이상 Mayor public contract가 아니다.

이 구조가 좋은 이유:

- API surface를 늘리지 않는다
- turn validation, auth, websocket broadcast 흐름을 그대로 유지한다
- backend guard는 action mask만 바꾸면 된다

### serializer/meta 설계

upstream Mayor는 cursor-driven이 아니므로, 예전 `mayor_slot_idx` 같은 cursor metadata를 복원할 필요는 없다.

기본 원칙:

- `action_mask`를 Mayor legality의 canonical source로 유지한다.
- frontend는 board slot index와 action index의 고정 매핑으로 legal slot을 렌더링한다.

권장 convenience field:

- `meta.mayor_phase_mode = "slot-direct"`
- `meta.mayor_remaining_colonists`
- `meta.mayor_legal_island_slots` (`[0, 2, 5]` 형태)
- `meta.mayor_legal_city_slots` (`[1, 4]` 형태)

이 필드들은 필수는 아니지만, frontend가 mask를 직접 파싱하는 중복 로직을 줄여 준다.

### bot service

현재 `BotService.normalize_selected_action()`은 Mayor면 무조건 `69-71`로 normalize 한다. full cutover에서는 이 로직이 그대로 있으면 bot이 전부 깨진다.

권장 변경:

- Mayor에서 `69-71` normalization을 제거한다.
- bot 모델이 legacy Mayor action을 내놓으면, backend가 legal slot mask를 보고 heuristic fallback을 수행한다.
- fallback 우선순위는 별도 helper로 고정한다.
  - 예: island productive tile 우선 -> city 생산건물 우선 -> 나머지 legal slot
- 이 fallback은 "모델 재학습 전 임시 브리지"로 문서화한다.

### replay/logger/model fingerprint

변경 필요:

- `replay_logger.describe_action()`
  - `120-131`을 `mayor.place.island.{slot}`로 설명
  - `140-151`을 `mayor.place.city.{slot}`로 설명
- `scenario_regression.py`
  - Mayor expected/forbidden action band를 새 contract로 교체
  - legacy `69-71` Mayor 의존 시나리오를 제거 또는 별도 migration fixture로 격리
- `model_registry.py`
  - action-space fingerprint를 명시적으로 bump 한다
  - 예: `castone.action-space.slot-mayor.v1`, `castone.mayor.slot-direct.v1`

핵심 판단:

- backend는 old Mayor semantics를 숨기지 말고, fingerprint와 replay text까지 같이 바꿔야 한다.
- bot compatibility는 "legacy action normalize"가 아니라 "legal-slot heuristic bridge"로 해결하는 편이 덜 위험하다.

## 5.4 Frontend 변경 설계

핵심 대상:

- `frontend/src/App.tsx`
- `frontend/src/components/GameScreen.tsx`
- `frontend/src/components/MayorStrategyPanel.tsx` 제거 또는 대체
- 신규 `frontend/src/components/MayorSequentialPanel.tsx`
- `frontend/src/components/CityGrid.tsx`
- `frontend/src/components/IslandGrid.tsx`
- `frontend/src/components/PlayerPanel.tsx`
- `frontend/src/types/gameState.ts`
- `frontend/src/locales/*.json`

### 권장 UI 구조

기존 `MayorStrategyPanel`을 억지로 늘리기보다 새 컴포넌트로 분리하는 편이 낫다.

권장안:

- `MayorStrategyPanel.tsx`: 제거
- 신규 `MayorSequentialPanel.tsx`:
  - "배치할 빈 위치를 선택하세요" 안내
  - 남은 colonist 수 표시
  - legal island/city slot 안내
  - 클릭 즉시 확정되는 규칙 설명
  - 이전 선택은 되돌릴 수 없다는 경고 문구

### 보드 상호작용

현재 `CityGrid`, `IslandGrid`는 pure presentational이다.

필요한 확장:

- highlight용 `activeSlotId?: string`
- 클릭용 `onMayorSlotAction?: (zone: "island" | "city", slotIdx: number) => void`
- legal 여부 표시용 `mayorLegal?: boolean`
- illegal slot은 시각적으로 비활성 처리

이번 upstream 호환 설계에서는 "버튼으로 amount 고르기"가 아니라 "보드 슬롯 직접 클릭"이 기본 UX다.

권장 UX:

- legal slot만 hover/click 가능
- 클릭 즉시 `submitAction(120 + idx)` 또는 `submitAction(140 + idx)` 호출
- 선택 후 즉시 최신 상태를 받아 재렌더링
- 이미 채워진 slot은 다시 클릭 affordance를 제공하지 않음

### App/GameScreen 변경

현재:

- `selectMayorStrategy(actionIndex: 69 | 70 | 71)`

변경 후:

- `selectMayorSlot(actionIndex: number)`
- bot turn인 경우 Mayor human panel 렌더링 금지 유지
- human Mayor turn인 경우 `MayorSequentialPanel` 렌더링

### i18n

기존 문구는 전략 중심이라 거의 전부 교체 대상이다.

새 문구 예시:

- "배치할 빈 위치를 선택하세요."
- "건물과 타일 중 합법 위치만 선택할 수 있습니다."
- "이 선택은 즉시 확정되며 되돌릴 수 없습니다."
- "이미 colonist가 배치된 위치는 다시 선택할 수 없습니다."

## 5.5 Contract Update Plan

`contract.md`는 최소 다음 항목을 수정해야 한다.

### Game REST / Mayor

현재:

- Mayor도 human/bot 공통으로 `POST /action` 한 번에 처리

수정:

- channel surface는 그대로 `POST /action`
- Mayor는 `120-131`, `140-151` band 기반 slot-direct sequential 처리
- 추가 Mayor 전용 REST route는 열지 않는다

### GameState Contract

현재:

- `mayor_slot_idx`, `mayor_can_skip`는 더 이상 포함되지 않는다

수정:

- cursor metadata는 복원하지 않는다
- 예:
  - `mayor_phase_mode`
  - `mayor_remaining_colonists`
  - `mayor_legal_island_slots`
  - `mayor_legal_city_slots`

### Action Contract

현재:

- `69-71`: Mayor strategy

수정 권장:

- `69-71`: Mayor public contract에서 제거 또는 reserved legacy band로 명시
- `120-131`: Mayor sequential island slot-direct
- `140-151`: Mayor sequential city slot-direct

## 5.6 Decision Log

### D1. 기준안은 upstream-compatible full cutover다

- 대안: dual Mayor
- 이유: 사용자가 upstream branch를 그대로 `PuCo_RL`에 반영하고, backend/frontend를 그 계약에 맞추는 방향을 명시적으로 선택했기 때문

### D2. sequential Mayor는 amount-choice가 아니라 slot-direct다

- 대안: current-slot amount choice
- 이유: 실제 upstream branch의 action space와 일치시키기 위함

### D3. 입력은 보드 슬롯 직접 클릭으로 간다

- 대안: 별도 Mayor button panel
- 이유: upstream action index가 slot과 1:1 매핑되고, frontend도 이를 직접 표현하는 편이 자연스럽기 때문

### D4. action_mask를 canonical source로 유지한다

- 대안: cursor metadata 복원
- 이유: upstream Mayor는 cursor 기반이 아니므로 불필요한 추상화를 되살리지 않기 위함

### D5. channel endpoint는 추가하지 않는다

- 대안: `/mayor-place`, `/mayor-finish`, `/mayor-distribute` 재공개
- 이유: 현재 channel contract를 유지하는 편이 테스트/운영 부담이 작음

### D6. bot 호환성은 heuristic bridge로 완충한다

- 대안: legacy `69-71` Mayor normalize 유지
- 이유: public contract를 다시 이중화하지 않고도 old model failure를 흡수할 수 있기 때문

## 6. TDD Plan

이 작업은 반드시 "RED -> GREEN -> REFACTOR" 단위로 나눠야 한다.

## 6.1 RED Cycle 1: Engine slot legality

먼저 실패해야 하는 테스트:

- Mayor turn에서 empty island/city slot만 legal한지
- `69-71`이 Mayor에서 더 이상 legal하지 않은지
- full building / occupied plantation이 mask에서 꺼지는지

추천 파일:

- `PuCo_RL/tests/test_engine.py`
- 신규 `PuCo_RL/tests/test_mayor_slot_direct.py`

핵심 케이스:

- empty plantation slot -> `120 + idx` legal
- building capacity remaining -> `140 + idx` legal
- occupied plantation -> illegal
- full building -> illegal
- Mayor turn에서 `69-71` 전부 illegal

## 6.2 RED Cycle 2: Irreversibility

실패해야 하는 테스트:

- action 한 번 이후 같은 slot이 mask에서 즉시 사라져야 함
- 같은 slot에 재배치 시 예외가 나야 함
- 마지막 colonist 또는 마지막 legal slot 이후 turn이 넘어가야 함

핵심 케이스:

- island slot 3 배치 후 `120 + 3`가 더 이상 legal하지 않음
- city slot 5가 capacity 2에서 2명이 되면 `140 + 5`가 사라짐
- replay/history에 같은 slot 재편집 action이 남지 않음

## 6.3 RED Cycle 3: Backend channel contract

실패해야 하는 테스트:

- Mayor REST action이 `120-131`, `140-151`만 허용되는지
- legacy `69-71` Mayor action을 보내면 막히는지
- wrong-turn actor가 legal Mayor slot action을 보내면 막히는지

추천 파일:

- `backend/tests/test_phase_action_edge_cases.py`
- 신규 `backend/tests/test_mayor_slot_contract.py`

핵심 케이스:

- `mask[120:132]`, `mask[140:152]`가 Mayor state와 일치
- `69-71` 전송 시 `400`
- 이미 가득 찬 slot action 전송 시 `400`

## 6.4 RED Cycle 4: Serializer/UI slot sync

실패해야 하는 테스트:

- serializer가 board slot 정보와 action mask만으로 legal slot 렌더링을 가능하게 하는지
- optional convenience field가 mask와 어긋나지 않는지

추천 파일:

- `backend/tests/test_mayor_serializer_contract.py`
- `frontend/src/components/__tests__/MayorSequentialPanel.test.tsx`

핵심 케이스:

- legal island slot 배열과 `action_mask[120:132]`가 일치
- legal city slot 배열과 `action_mask[140:152]`가 일치
- 남은 colonist가 0이면 panel이 즉시 사라지거나 다음 player로 넘어감

## 6.5 RED Cycle 5: Frontend irreversible UX

실패해야 하는 테스트:

- strategy 버튼이 더 이상 보이지 않는지
- legal slot 클릭 시 올바른 action index가 전송되는지
- illegal slot은 disabled/unbound인지

추천 파일:

- `frontend/src/__tests__/App.mayor-flow.test.tsx`
- 신규 `frontend/src/components/__tests__/MayorSequentialPanel.test.tsx`

핵심 케이스:

- human Mayor turn에서 strategy buttons가 보이면 실패
- island slot 2 click -> `122` 전송
- city slot 7 click -> `147` 전송
- 이미 찬 slot은 클릭해도 전송되지 않음

## 6.6 RED Cycle 6: Bot safety and regression

실패해야 하는 테스트:

- bot model이 legacy Mayor action을 반환해도 backend가 legal slot fallback으로 안전하게 진행하는지
- scenario regression이 새 Mayor contract 기준으로 통과하는지

추천 파일:

- `backend/tests/test_bot_service_safety.py`
- `backend/tests/test_scenario_regression_harness.py`

핵심 케이스:

- legacy Mayor prediction -> nearest legal slot heuristic으로 변환
- no legal slot이면 turn advance 또는 pass-equivalent branch가 정상 동작
- replay/logger 문구가 slot-direct semantics를 남김

## 7. Docker Test Execution Plan

원칙:

- 새 테스트용 DB를 따로 만들지 않는다
- compose가 사용하는 기존 PostgreSQL/Redis를 그대로 쓴다
- 테스트는 backend/frontend 컨테이너에서만 실행한다

## 7.1 Bring-up

```bash
cd /Users/seoungmun/Documents/agent_dev/castone/puco_test
docker compose up -d --build db redis backend frontend
docker compose ps
```

## 7.2 Backend focused tests

```bash
docker compose exec backend pytest \
  tests/test_phase_action_edge_cases.py \
  tests/test_mayor_slot_contract.py \
  tests/test_mayor_serializer_contract.py \
  tests/test_bot_service_safety.py \
  tests/test_scenario_regression_harness.py \
  -q
```

## 7.3 Engine/PuCo_RL focused tests

```bash
docker compose exec backend pytest \
  /PuCo_RL/tests/test_engine.py \
  /PuCo_RL/tests/test_mayor_slot_direct.py \
  /PuCo_RL/tests/balance_test.py \
  -q
```

## 7.4 Frontend Mayor tests

```bash
docker compose exec frontend npm run test -- \
  src/__tests__/App.mayor-flow.test.tsx \
  src/components/__tests__/MayorSequentialPanel.test.tsx
```

## 7.5 Rollup check

```bash
docker compose exec backend pytest -q
docker compose exec frontend npm run test
```

주의:

- 이번 작업은 Mayor action contract를 건드리므로 최소한 targeted suite 이후 full suite까지 보는 것이 안전하다.
- Docker daemon이 떠 있지 않으면 테스트 실행 자체가 불가능하므로, 먼저 Docker Desktop이 정상 기동되어야 한다.

## 8. Rollout Order

권장 순서:

1. upstream branch에서 `PuCo_RL` 차이만 검토
2. `PuCo_RL`를 upstream branch 기준으로 반영
3. engine/env 쪽 slot-direct Mayor 테스트부터 RED 작성
4. engine/env 최소 구현 또는 upstream 반영분 정합화
5. backend serializer/action mask/guard 조정
6. bot heuristic bridge 및 replay/regression 보정
7. frontend panel 교체
8. contract.md 갱신
9. Docker targeted tests
10. Docker full regression

## 9. Risks

### Risk 1. Old bot/model outputs가 Mayor에서 대량 invalid가 될 수 있음

대응:

- `69-71` fallback을 제거하는 대신 legal-slot heuristic bridge를 둔다
- action-space fingerprint를 강제로 올린다

### Risk 2. Frontend가 action mask와 board index를 잘못 매핑하면 잘못된 slot에 action을 보낼 수 있음

대응:

- `120 + island_idx`, `140 + city_idx` 매핑을 타입/테스트로 고정한다
- serializer convenience field와 UI mapping 테스트를 같이 둔다

### Risk 3. Upstream `PuCo_RL`만 가져오면 local backend/frontend와 action contract mismatch

대응:

- `git restore --source ... -- PuCo_RL` 직후 바로 backend/frontend patch를 같은 브랜치에서 수행

### Risk 4. Replay/model metadata가 조용히 오래된 semantics를 가리킬 수 있음

대응:

- fingerprint와 logger 문구를 명시적으로 재검토
- slot-direct semantics를 명시적으로 남김

### Risk 5. Upstream Mayor auto-fill이 frontend 기대와 어긋날 수 있음

대응:

- auto-action 조건을 코드와 문서에서 명시
- "valid action이 1개뿐일 때만 자동 실행"으로 축소하는 보정안을 우선 검토

## 10. Final Recommendation

실행 전략은 아래가 가장 안전하다.

- upstream `refactor/mayor-sequential-placement`를 `PuCo_RL`의 기준 구현으로 사용한다.
- Mayor public contract를 `120-131`, `140-151` slot-direct semantics로 단일화한다.
- backend/frontend는 old strategy-first 가정을 걷어내고, board-direct Mayor UX로 맞춘다.
- bot/model 호환성은 short-term heuristic bridge + fingerprint bump로 넘긴다.
- 구현 순서는 engine -> backend -> frontend -> contract -> Docker tests 순으로 진행한다.

이 방향이면 upstream branch와 Castone 제품 계약을 같은 방향으로 정렬할 수 있고, "한번 선택하면 되돌릴 수 없는 순차 Mayor"도 실제 slot-direct action으로 일관되게 구현할 수 있다.
