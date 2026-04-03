# PuCo Change Report

작성일: 2026-04-03  
목적: `PuCo_RL`, `backend`, `frontend`를 기준으로 기능을 전부 매핑하고, `PuCo_RL`의 기능 변화가 backend/frontend 어느 부분에 어떤 방식으로 영향을 주는지 상세하게 정리한다.

## 1. 요약

이 프로젝트의 실제 구조는 다음과 같다.

- `PuCo_RL`은 게임 규칙, 상태 머신, 관측 스키마, 액션 공간, 액션 마스킹, 점수 계산, RL 학습/평가 기준의 원천이다.
- `backend`는 `PuCo_RL`을 직접 서비스 가능한 게임 서버 형태로 감싸는 계층이다.
- `frontend`는 backend가 `PuCo_RL` 상태를 직렬화해서 내보낸 `GameState`를 렌더링하는 계층이다.

즉, `PuCo_RL`의 어떤 변화든 대부분 아래 순서로 파급된다.

1. `PuCo_RL/configs/constants.py`
2. `PuCo_RL/env/engine.py`, `PuCo_RL/env/pr_env.py`
3. `backend/app/engine_wrapper/wrapper.py`
4. `backend/app/services/state_serializer.py`
5. `backend/app/services/action_translator.py`, `game_service.py`, `bot_service.py`
6. `frontend/src/types/gameState.ts`
7. `frontend/src/App.tsx`, `frontend/src/components/*`

가장 중요한 결론은 다음이다.

- `PuCo_RL`의 "규칙 변화"는 거의 항상 backend와 frontend 둘 다 바뀐다.
- `PuCo_RL`의 "관측/액션 스키마 변화"는 backend bot 추론 계층과 frontend 입력/출력 계약 모두를 바꾼다.
- `PuCo_RL`의 "학습/모델 구조 변화"는 frontend보다 backend bot serving에 직접적인 영향을 준다.
- `PuCo_RL`의 "평가/학습 스크립트 변화"는 런타임 서비스에는 직접 영향이 작지만, 모델 추가/교체 정책과 bot_type 운영 정책에는 영향을 준다.

---

## 2. 전체 아키텍처 맵

### 2.1 PuCo_RL 기능 계층

`PuCo_RL`은 크게 6개 기능군으로 나눌 수 있다.

1. 게임 규칙/상수 계층
- `configs/constants.py`

2. 게임 도메인 모델 계층
- `env/components.py`
- `env/player.py`

3. 게임 엔진/상태 머신 계층
- `env/engine.py`

4. RL 환경/관측/액션 마스크 계층
- `env/pr_env.py`
- `utils/env_wrappers.py`

5. 에이전트/모델/추론 계층
- `agents/*.py`
- `models/*`

6. 학습/평가/리플레이 계층
- `train*.py`
- `evaluate*.py`
- `logs/replay/*`

### 2.2 backend 연결 계층

backend는 `PuCo_RL`을 다음 5개 역할로 소비한다.

1. 엔진 생성 및 step 실행
- `backend/app/engine_wrapper/wrapper.py`

2. 상태 직렬화
- `backend/app/services/state_serializer.py`

3. frontend 의미 기반 액션을 PuCo action index로 번역
- `backend/app/services/action_translator.py`

4. 게임 세션/봇/WS/로그 운영
- `backend/app/services/game_service.py`
- `backend/app/services/bot_service.py`
- `backend/app/services/ws_manager.py`

5. HTTP / WebSocket API 노출
- `backend/app/api/channel/*.py`
- `backend/app/api/legacy/*.py`

### 2.3 frontend 연결 계층

frontend는 `PuCo_RL`을 직접 읽지 않고 backend가 변환한 `GameState` 계약으로 소비한다.

핵심 파일:

- 타입 계약: `frontend/src/types/gameState.ts`
- 화면 라우팅/액션 전송/Mayor 로컬 상태: `frontend/src/App.tsx`
- 공용 보드 렌더: `frontend/src/components/CommonBoardPanel.tsx`
- 플레이어 패널 렌더: `frontend/src/components/PlayerPanel.tsx`
- 세부 시각화 컴포넌트: `ColonistShip.tsx`, `CargoShips.tsx`, `TradingHouse.tsx`, `IslandGrid.tsx`, `CityGrid.tsx`, `SanJuan.tsx`
- 상태 수신 계약: `frontend/src/hooks/useGameWebSocket.ts`

---

## 3. PuCo_RL 기능 전수 매핑

## 3.1 `configs/constants.py`

기능:
- `Phase`, `Role`, `Good`, `TileType`, `BuildingType` enum 정의
- 플레이어 수별 초기 세팅 정의
- 건물 메타(`BUILDING_DATA`) 정의
- 판매 가격(`GOOD_PRICES`) 정의

backend 연결:
- `state_serializer.py`가 enum과 `BUILDING_DATA`를 사용해 frontend용 문자열/수치 메타를 만든다.
- `action_translator.py`가 enum 순서를 action index와 연결한다.
- `bot_service.py`, `agents/factory.py`, `agent_registry.py`가 model/phase/good 해석에 간접 의존한다.

frontend 연결:
- 직접 enum을 읽지는 않지만, backend가 enum을 문자열로 변환한 결과를 렌더링한다.
- `GameState` 타입의 `phase`, `roles`, `goods`, `available_buildings`, `available_plantations`는 모두 이 상수 집합에 의해 의미가 결정된다.

변화 시 영향:

### Phase enum이 바뀌면

예:
- `CAPTAIN_STORE` 이름 변경
- 새 phase 추가
- phase ordinal 재배열

backend 영향:
- `state_serializer.PHASE_TO_STR` 수정 필요
- `bot_service._extract_phase_id()` 및 phase 클램핑 로직 영향
- `pr_env`의 observation `current_phase`와 action mask 분기 영향
- `EngineWrapper.last_info["current_phase_id"]` 의미 변화

frontend 영향:
- `types/gameState.ts`의 `PhaseType` 수정 필요
- `App.tsx`의 phase별 버튼 표시, focus 이동, Mayor/Captain/Trader 분기 로직 수정 필요
- 번역 파일 `locales/*.json`의 `phases.*`, `decision.*` 갱신 필요

### Role enum이 바뀌면

예:
- 역할 추가/삭제
- Prospector 구성 변경

backend 영향:
- `state_serializer`의 role serialization 영향
- `action_translator.select_role()` 영향
- `pr_env` action space role index 영향

frontend 영향:
- `RoleName` 타입 수정
- `CommonBoardPanel`의 역할 렌더 순서 수정
- `App.tsx`에서 role privilege/class 매핑 수정

### Good enum 순서가 바뀌면

backend 영향:
- `action_translator.sell/load_ship/load_wharf/store_*` 전부 영향
- `pr_env` goods index 기반 mask/action mapping 영향
- `state_serializer`의 goods_supply, cargo_ships, trading_house serialization 영향

frontend 영향:
- `GOOD_VALUE` 매핑 수정
- `GoodsType` 관련 모든 UI와 action index helper 수정
- `TradingHouse`, `CargoShips`, `PlayerPanel`, `CommonBoardPanel` 렌더 기준 영향

이 항목은 파급도가 매우 크다.

### BuildingType / BUILDING_DATA가 바뀌면

예:
- 건물 추가
- 건물 cost/vp/capacity 수정
- 건물 능력 변경

backend 영향:
- `state_serializer._serialize_common_board()`의 available_buildings 변경
- `_serialize_player()`의 city/building state 변화
- `action_translator.build()` index mapping 영향
- `engine.py`의 Builder, Craftsman, Captain, 종료 보너스 계산 영향
- `pr_env.valid_action_mask()`의 builder/mayor/captain/store 규칙 영향

frontend 영향:
- `SanJuan.tsx` 렌더 데이터와 아이콘/tooltip 갱신 필요
- `App.tsx`의 건물 advantage meta 수정 필요
- `PlayerPanel`, `CityGrid`의 max_colonists, empty_slots, active 상태 렌더 영향

---

## 3.2 `env/components.py`

기능:
- `IslandTile`, `CityBuilding`, `CargoShip` 데이터 구조 정의

backend 연결:
- `state_serializer`가 이 객체의 속성명(`tile_type`, `is_occupied`, `colonists`, `good_type`, `current_load`)에 강하게 의존
- `_safe_get()`로 일부 drift를 방어하지만, 구조 변경은 여전히 serializer 전반에 영향

frontend 연결:
- 직접 읽지 않음
- serializer가 만든 `plantations`, `buildings`, `cargo_ships` shape를 통해 간접 소비

변화 시 영향:
- `is_occupied` -> 다른 이름으로 바뀌면 island/production/hospice/quarry UI가 전부 깨질 수 있음
- `CargoShip`의 필드명이 바뀌면 `CargoShips.tsx`가 렌더링하는 적재량/남은 공간 계산이 깨짐

---

## 3.3 `env/player.py`

기능:
- 플레이어 자원/보드 상태 관리
- plantation 배치, 건물 건설, goods 관리
- `total_colonists_owned`, `recall_all_colonists()` 등 규칙 보조 로직 제공

backend 연결:
- `state_serializer._serialize_player()`가 player의 island/city/goods/doubloons/vp를 그대로 읽음
- Mayor 관련 규칙은 `unplaced_colonists`와 `recall_all_colonists()` 의미에 크게 의존
- 최종 점수 breakdown과 production 계산에도 player 구조가 직접 사용됨

frontend 연결:
- `Player` 타입 대부분이 여기서 유래한 상태를 serializer가 풀어쓴 결과
- `PlayerPanel`, `IslandGrid`, `CityGrid`가 direct consumer

변화 시 영향:

### `unplaced_colonists` 의미가 바뀌면

backend 영향:
- serializer의 `city.colonists_unplaced`
- Mayor meta 계산
- bot input phase reasoning

frontend 영향:
- Mayor pending 계산
- 플레이어 패널 colonist badge
- Mayor confirm/finish 조건

### `recall_all_colonists()` 의미가 바뀌면

backend 영향:
- Mayor 관련 serializer와 bot phase expectation 변화

frontend 영향:
- Mayor UI가 전체 재배치형인지 부분 재배치형인지 다시 설계 필요

---

## 3.4 `env/engine.py`

기능:
- 게임 규칙의 핵심 상태 머신
- 역할 선택
- phase별 action 처리
- 생산/판매/선적/저장/점수/종료 조건 처리

이 파일은 `PuCo_RL` 전체 중 파급력이 가장 큰 파일이다.

backend 연결:
- `EngineWrapper`가 직접 감싼다
- `state_serializer`가 거의 모든 표시 데이터를 여기서 뽑는다
- `game_service.process_action()` validation과 logging이 여기의 step 결과를 기준으로 작동한다
- `bot_service`는 여기에서 나온 mask/obs 위에서 의사결정을 한다

frontend 연결:
- phase 전이, 공용 보드 상태, 플레이어 상태, 생산량, Mayor/Captain/Trader 행동 가능 여부 전부 간접적으로 이 파일에 의존

`engine.py`의 기능 변화는 다음 유형으로 나눠서 봐야 한다.

### A. 규칙 로직 변화

예:
- Mayor 배치 규칙 변경
- Captain 적재 강제 규칙 수정
- Trader 중복 판매 규칙 수정
- 종료 조건 수정

backend 영향:
- 거의 항상 `pr_env.valid_action_mask()`도 같이 바뀌어야 함
- `state_serializer`의 파생 필드 의미 재검토 필요
- `action_translator`가 semantic input을 같은 action index로 계속 보낼 수 있는지 검토 필요
- `bot_service`의 phase별 정상 행동 기준과 fallback 로직 재검토 필요

frontend 영향:
- 버튼 노출/비활성화 조건 수정 필요
- 상태 표시 문구와 툴팁 수정 필요
- Mayor/Captain/Trader 전용 UI 흐름 수정 필요

### B. 상태 필드 변화

예:
- `mayor_placement_idx` 제거/변경
- `_captain_passed_players` 의미 변경
- `trading_house`, `cargo_ships` 내부 구조 변경

backend 영향:
- serializer의 메타 필드와 derived field 전부 점검 필요
- `compute_score_breakdown()` 같은 보조 함수 영향
- logging payload shape 변경 가능

frontend 영향:
- `meta.mayor_slot_idx`, `captain_consecutive_passes` 등 타입 및 렌더 수정 필요

### C. 점수 계산 변화

예:
- 대형 건물 종료 보너스 규칙 변경

backend 영향:
- `compute_score_breakdown()`와 `final-score` API 영향
- 종료 로그/결과 화면 데이터 영향

frontend 영향:
- 최종 결과 화면, score summary UI 영향

### D. 종료 조건 변화

예:
- colonist ship underfilled 판정 방식 변경
- VP 소진 시점 변경

backend 영향:
- `GameService.process_action()`에서 `room.status = FINISHED` 전이 시점 영향
- Redis `finished=True` TTL 처리 영향
- `final-score` 호출 타이밍 영향

frontend 영향:
- 종료 화면 노출 시점
- game_over transition
- "파란 화면"류 버그 재현 조건 변경

---

## 3.5 `env/pr_env.py`

기능:
- `engine.py`를 RL 환경으로 감싸는 계층
- observation schema 정의
- action space 정의
- valid action mask 생성
- PettingZoo/AEC step/observe/reset 계약 제공
- reward shaping, terminal reward 계산

backend 연결:
- `EngineWrapper`가 `observe()`, `step()`, `valid_action_mask()`를 간접 소비
- `bot_service`가 `last_obs`, `action_mask`, `phase_id`를 여기서 가져감
- `state_serializer`는 engine game 상태를 읽지만, phase/mask와의 계약은 사실상 `pr_env.py`가 결정

frontend 연결:
- 직접 연결되지는 않지만, backend가 내려주는 `action_index`, `mayor_can_skip`, `available_buildings`, `available_plantations`는 모두 여기에 의존

변화 시 영향:

### Observation schema 변화

예:
- `global_state` 필드 추가/삭제
- player 관측 차원 변화

backend 영향:
- `bot_service` flatten 경로 영향
- `agents/factory.py`, `services/agents/wrappers.py`의 모델 차원 검증 영향
- model compatibility 붕괴 가능

frontend 영향:
- 직접 영향은 작지만, serializer가 새 필드를 활용해 UI를 풍부하게 만들 수 있음
- serializer가 기존 의미를 유지하는지 확인 필요

### Action space / action index 변화

예:
- action index 재배열
- Mayor 액션 범위 변경
- reserved action 사용 시작

backend 영향:
- `action_translator.py` 거의 전면 수정 필요
- `state_serializer`의 `action_index` 삽입 로직 수정 필요
- `frontend` action helper와 semantic action 전송 로직 수정 필요

frontend 영향:
- `channelActionIndex` helper 수정
- pass/sell/load/mayor/store action 전송 로직 수정
- UI 버튼이 잘못된 action index를 보내면 바로 깨짐

이 항목은 backend와 frontend를 동시에 건드리는 대표 사례다.

### Action masking 변화

예:
- Captain pass 허용 조건 수정
- Trader sell 후보 계산 수정
- Mayor min/max placement 계산 수정

backend 영향:
- `game_service.process_action()`에서 invalid action rejection 빈도 변화
- `bot_service` selected_action 분포 변화
- 회귀 로그와 테스트 모두 업데이트 필요

frontend 영향:
- 버튼 disable/enable 정책과 backend 진실이 어긋날 수 있음
- `mayor_can_skip`, discard sequence, load button 활성 상태의 UX가 달라질 수 있음

### Reward shaping 변화

backend 영향:
- 런타임 게임 서비스에는 직접 영향 작음
- bot serving model의 행동 특성은 크게 바뀔 수 있음

frontend 영향:
- 직접 영향 없음
- 다만 모델 행동이 변하면서 역할 선택/게임 스타일이 변해 체감 UX에 영향을 줄 수 있음

---

## 3.6 `agents/*`, `models/*`

기능:
- Random / PPO / HPPO / heuristic / MCTS 계열 에이전트
- wrapper를 통한 공통 act 인터페이스
- 모델 파일과 메타데이터

backend 연결:
- `backend/app/services/agents/factory.py`
- `backend/app/services/agents/wrappers.py`
- `backend/app/services/agent_registry.py`
- `backend/app/services/bot_service.py`

frontend 연결:
- 직접 연결 없음
- 단, bot_type 표시 아이콘/라벨(`random`, `gemini`, `scoring`)은 frontend에 존재

변화 시 영향:

### 새 bot_type 추가

backend 영향:
- `agent_registry.py` 또는 `services/agents/*` 등록 필요
- `bot_service`가 bot_type 라우팅을 실제로 사용하도록 유지 필요
- `/api/bot-types` 응답 변경

frontend 영향:
- `LobbyScreen` bot type 목록 표시
- `PlayerPanel` botType 아이콘/라벨 추가 가능

### 모델 입력 차원 변화

backend 영향:
- `bot_service` flatten/obs dim
- `services/agents/wrappers.py` expected_dim
- fallback/random policy 경로 영향

frontend 영향:
- 직접 영향 없음

### phase-aware model 추가

backend 영향:
- `phase_id` 추출/클램핑 로직 영향
- wrapper selection 영향

frontend 영향:
- 없음

---

## 3.7 `train*.py`, `evaluate*.py`, `logs/replay/*`

기능:
- self-play 학습
- league 학습
- 평가/토너먼트
- replay 생성 및 분석

backend 연결:
- 모델 산출물 추가/교체 정책
- bot_type별 model path 운영
- 로그 저장 포맷 설계 참고 자료

frontend 연결:
- 직접 영향 없음
- 다만 replay 형식이 서비스 로그/결과 화면 설계에 참고될 수 있음

변화 시 영향:

### replay schema가 유용하게 정리되면

backend 영향:
- game log export 기능 설계 시 reference schema로 활용 가능

frontend 영향:
- 결과 화면/리플레이 뷰어 구축 시 reference로 활용 가능

### 학습 결과 모델이 자주 추가되면

backend 영향:
- model registry, metadata, compatibility check 필요

frontend 영향:
- bot selection UI에 모델 설명/버전 표시가 필요해질 수 있음

---

## 4. backend 기능 전수 매핑

## 4.1 `engine_wrapper/wrapper.py`

역할:
- `PuertoRicoEnv` 생성
- observe 결과에서 state/mask 추출
- numpy -> JSON 직렬화 가능한 값으로 변환
- round/step 로그 메타 생성

PuCo_RL 변화에 민감한 부분:
- `observe()` payload shape
- action_mask 위치
- current player/governor 의미
- reward/done/truncation semantics

PuCo_RL가 바뀌면 이 파일을 먼저 봐야 하는 경우:
- observation schema 변경
- PettingZoo 계약 변경
- governor/random start 정책 변경

## 4.2 `services/state_serializer.py`

역할:
- `PuCo_RL`의 내부 상태를 frontend `GameState`로 번역하는 가장 중요한 계층

PuCo_RL 변화에 민감한 부분:
- role/phase/good/building enum
- building capacity/vp/count
- island/city occupancy 표현
- cargo ship/trading house 구조
- Mayor/Captain/Trader phase 메타
- 생산량 계산 로직
- 최종 점수 breakdown 로직

이 파일은 사실상 `PuCo_RL` 변경의 1차 충격 흡수층이다.

## 4.3 `services/action_translator.py`

역할:
- frontend semantic action을 `PuCo_RL` 정수 action으로 매핑

PuCo_RL 변화에 민감한 부분:
- action index 재배열
- role/good/building/tile enum 순서
- Mayor/Captain store action range 변경

이 파일은 action space 변경 시 거의 반드시 수정된다.

## 4.4 `services/game_service.py`

역할:
- 게임 시작/액션 처리
- turn validation
- action mask validation
- 로그 저장
- Redis/WS state broadcast
- bot scheduling

PuCo_RL 변화에 민감한 부분:
- step 결과 구조
- terminated/truncated 의미
- current_player_idx / governor_idx semantics
- room.players와 env player index alignment

## 4.5 `services/bot_service.py`

역할:
- backend 런타임 봇 추론
- action mask 기반 행동 선택
- phase_id 추출
- fallback/random retry

PuCo_RL 변화에 민감한 부분:
- observation schema
- action mask shape
- current_phase encoding
- model input dim

## 4.6 `api/channel/*`

역할:
- room/game/ws/auth API
- 최종적으로 frontend가 쓰는 서비스 표면

PuCo_RL 변화에 민감한 부분:
- `final-score` shape
- `action_index` 계약
- bot room 생성 방식

---

## 5. frontend 기능 전수 매핑

## 5.1 `types/gameState.ts`

역할:
- frontend가 기대하는 전체 게임 상태 계약

이 파일은 backend serializer와 거의 1:1 계약이다.

PuCo_RL 변화 시 가장 먼저 깨지는 frontend 파일:
- phase 이름
- role 이름
- goods/buildings/colonists/common board shape
- mayor/captain/trader 메타 필드

## 5.2 `App.tsx`

역할:
- 화면 라우팅
- action 전송
- Mayor 로컬 상태 관리
- Trader/Captain/Builder/Craftsman 인터랙션 처리
- 종료 결과 fetch 및 전환

이 파일은 `PuCo_RL` 규칙 변화의 frontend 측 중심 허브다.

특히 민감한 변화:
- Mayor 규칙
- action index 변경
- final-score 정책
- phase/decision semantics 변화

## 5.3 `CommonBoardPanel.tsx`

역할:
- 역할, colonist ship, trading house, goods supply, cargo ships, available plantations 표시

민감한 변화:
- roles 구조
- colonists ship/supply
- trading house capacity
- goods supply
- cargo ships
- face-up plantations/quarry

## 5.4 `PlayerPanel.tsx`, `IslandGrid.tsx`, `CityGrid.tsx`

역할:
- 플레이어 자원, 생산, 섬, 도시, Mayor 입력 표시

민감한 변화:
- player goods/production
- building capacities
- Mayor slot progression and cursor
- unplaced colonists semantics

## 5.5 `useGameWebSocket.ts`

역할:
- backend가 보내는 `STATE_UPDATE`, `GAME_ENDED`, `PLAYER_DISCONNECTED` 소비

민감한 변화:
- state payload shape
- game end signaling policy
- action_mask embedding 위치

---

## 6. 변화 유형별 상세 파급 매트릭스

## 6.1 규칙 변화

대표 예:
- Mayor 재배치 구조 변경
- Captain 강제 적재 규칙 수정
- Trader 판매 규칙 수정
- 종료 조건 수정

반드시 확인할 backend:
- `engine.py`
- `pr_env.py`
- `state_serializer.py`
- `game_service.py`
- `bot_service.py`

반드시 확인할 frontend:
- `types/gameState.ts`
- `App.tsx`
- 관련 컴포넌트 (`CommonBoardPanel`, `PlayerPanel`, `CityGrid`, `IslandGrid`)

테스트 우선순위:
- engine unit test
- env mask test
- serializer contract test
- frontend interaction/integration test

## 6.2 액션 공간 변화

대표 예:
- Mayor action index 조정
- store action 추가
- role/action 범위 재배열

backend 영향:
- `action_translator.py` 최우선 수정
- `state_serializer`의 `action_index` 필드 갱신
- `game_service.process_action` 회귀 테스트

frontend 영향:
- `channelActionIndex` helper 수정
- 버튼 click handler 전부 재검토

## 6.3 관측 스키마 변화

대표 예:
- player/global observation 필드 추가/삭제
- phase id encoding 변경

backend 영향:
- `bot_service`
- `services/agents/wrappers.py`
- model compatibility

frontend 영향:
- 직접 영향은 작지만, serializer가 새 필드를 어떻게 쓰는지에 따라 간접 영향

## 6.4 enum/메타데이터 변화

대표 예:
- Good/Role/Building/Tile 이름 또는 순서 변경

backend 영향:
- serializer, translator, bot registry, tests

frontend 영향:
- type, translation, icon map, role order, action helper

## 6.5 점수/종료 변화

backend 영향:
- `compute_score_breakdown`
- `final-score` API
- game finish transition

frontend 영향:
- 결과 화면
- 종료 후 screen transition

---

## 7. 실무용 체크리스트: PuCo_RL의 무엇이 바뀌면 어디를 먼저 볼 것인가

### 체크리스트 A. 규칙 로직이 바뀌었다

먼저 볼 파일:
- `PuCo_RL/env/engine.py`
- `PuCo_RL/env/pr_env.py`
- `backend/app/services/state_serializer.py`
- `frontend/src/App.tsx`

바로 확인할 항목:
- phase 전이
- valid_action_mask
- derived UI field
- button enable/disable
- bot behavior regression

### 체크리스트 B. action index가 바뀌었다

먼저 볼 파일:
- `PuCo_RL/env/pr_env.py`
- `backend/app/services/action_translator.py`
- `backend/app/services/state_serializer.py`
- `frontend/src/App.tsx`

### 체크리스트 C. 건물/상품/역할 메타가 바뀌었다

먼저 볼 파일:
- `PuCo_RL/configs/constants.py`
- `backend/app/services/state_serializer.py`
- `frontend/src/types/gameState.ts`
- `frontend/src/components/CommonBoardPanel.tsx`
- `frontend/src/components/PlayerPanel.tsx`
- `frontend/src/components/SanJuan.tsx`

### 체크리스트 D. observation schema / 모델 구조가 바뀌었다

먼저 볼 파일:
- `PuCo_RL/env/pr_env.py`
- `PuCo_RL/utils/env_wrappers.py`
- `backend/app/services/bot_service.py`
- `backend/app/services/agents/*`

### 체크리스트 E. 종료/점수 규칙이 바뀌었다

먼저 볼 파일:
- `PuCo_RL/env/engine.py`
- `backend/app/services/state_serializer.py`
- `backend/app/api/channel/game.py`
- `frontend/src/App.tsx`

---

## 8. 최종 결론

이 코드베이스에서 `PuCo_RL`은 단순한 라이브러리가 아니라 서비스의 규칙 원천이다.  
따라서 `PuCo_RL` 변화는 아래처럼 생각해야 한다.

- `constants.py` 변화: backend/frontend 계약 변화
- `engine.py` 변화: 규칙, 상태, 점수, 종료, UI, bot 전부 변화
- `pr_env.py` 변화: action space/mask/bot 추론/backend translation 변화
- `agents/models` 변화: backend bot serving 변화
- `train/evaluate/replay` 변화: 운영 정책, 모델 선택, 로그 설계 변화

특히 실무적으로는 다음 3개가 가장 중요하다.

1. `PuCo_RL/env/engine.py`
- 규칙과 상태의 실제 진실 소스

2. `backend/app/services/state_serializer.py`
- `PuCo_RL`을 frontend 계약으로 바꾸는 핵심 완충층

3. `frontend/src/App.tsx`
- phase/action/mayor/captain/trader/final-score 흐름의 실제 소비자

즉, `PuCo_RL`의 기능 변화는 단순히 backend만, 또는 frontend만 보는 식으로 대응하면 안 된다.  
변화가 생기면 최소한 다음 세 층을 같이 봐야 한다.

- 규칙층: `engine.py`, `pr_env.py`
- 서비스층: `state_serializer.py`, `action_translator.py`, `game_service.py`, `bot_service.py`
- 화면층: `types/gameState.ts`, `App.tsx`, 관련 컴포넌트

이 문서를 기준으로 앞으로는 `PuCo_RL` 변경 제안이 나올 때,

1. 변화 유형 분류
2. 영향받는 backend 파일 식별
3. 영향받는 frontend 계약 식별
4. 테스트 범위 정의

순으로 진행하는 것이 가장 안전하다.
