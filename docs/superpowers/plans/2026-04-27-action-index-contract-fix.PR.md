# PR: action_index 계약 수정 — settler/mayor 의미↔위치 mismatch fix

## Summary

- **버그**: serializer가 `face_up_plantations`에 위치 인덱스(`8 + i`)를 실어 보냈으나 엔진은 의미 인덱스(`8 + tile.value`)로 디코드. corn 클릭 → coffee 적용 등 mismatch.
- **해결**: outbound state는 `engine_action_index` (semantic) + `display_position` + `canonical_id` 3-필드로 명시. ingress는 `canonical_id` 옵셔널 수신, 디코드 결과와 다르면 422 fail-closed.
- **MLOps**: transition envelope에 `submitted_canonical_id`, `decoded_canonical_id`, `canonical_id_match` 추가.
- **Backwards compat**: `action_index` 필드 유지 (값은 semantic으로 정정), `canonical_id`는 옵셔널.
- **Quarry**: 의미 인덱스 13 단독. 기존 14 호출 제거.

## Spec & Plan

- spec: `docs/superpowers/specs/2026-04-27-action-index-contract-fix-design.md`
- plan: `docs/superpowers/plans/2026-04-27-action-index-contract-fix.md`

## 변경 영역

### Backend
- `backend/app/services/state_serializer_support.py` — face_up: `8 + tile.value`, quarry → 13, `canonical_id="settler:tile_type:{name}"` / `"settler:quarry"`.
- `backend/app/services/state_serializer.py` — `_build_mayor_meta`에 `mayor_island_actions` (base 120 + tile_type.value) / `mayor_city_actions` (base 140 + engine_slot_idx) 추가, 각 entry에 `display_position` + `engine_action_index` + `canonical_id`.
- `backend/app/schemas/game.py` — `ActionRequestPayload.canonical_id: Optional[str] = None`.
- `backend/app/api/channel/game.py` — `_describe_action`로 디코드 후 mismatch 시 422 + structured detail. match/missing/mismatch 로깅.
- `backend/app/services/ml_logger.py` — envelope에 canonical 필드 4개 추가, 일치 여부 자동 계산.

### Frontend
- `frontend/src/types/gameState.ts` — `MayorActionEntry` 신설, `Meta.mayor_island_actions/mayor_city_actions` 옵셔널, `FaceUpPlantation`에 `engine_action_index/display_position/canonical_id` 옵셔널.
- `frontend/src/App.tsx` — `channelAction(actionIndex, canonicalId?)` 시그니처 확장. settler/quarry/mayor 호출부에서 entry의 semantic index + canonical_id 전달.
- `frontend/src/components/MayorSequentialPanel.tsx` — `meta.mayor_*_actions` 우선 소비, 부재 시 legacy 위치 fallback.

## Test plan

- [x] `tests/test_action_index_contract.py` (4) — face_up corn/coffee 의미 인덱스, quarry=13, mayor island/city actions
- [x] `tests/test_action_request_canonical_guard.py` (3) — mismatch 422 / match 통과 / omitted 통과
- [x] `tests/test_state_serializer_action_index.py` — quarry=13 / face_up semantic
- [x] `tests/test_ml_logger.py` — envelope canonical decoded + match flag
- [x] `tests/test_game_action.py`, `tests/test_game_service_side_effect_fail_open.py`, `tests/test_replay_logger.py` — 회귀 통과
- [x] frontend `App.action-index-contract.test.tsx` — corn 클릭 시 `action_index=10` + `canonical_id="settler:tile_type:corn"`
- [x] **Step 1 contract**: `48 PASS`
- [x] **Step 2 인접**: `44 PASS / 4 skip / 1 pre-existing fail` (`test_missing_action_index_returns_400` — Pydantic 422 vs expected 400, 베이스라인 동일)
- [x] **Step 3 frontend**: `83 PASS (22 files)`

## Commits (refactor/adapter)

```
041936c docs(spec): action_index contract fix design
2b1d5aa docs(plan): action_index 계약 수정 구현 플랜 추가
2ae493f test(action-contract): RED face_up engine_action_index uses tile_type.value
d6faaeb test(action-contract): RED mayor island/city actions use semantic indices
6726041 도커 임시 커밋
415f5a5 test(action-contract): RED transition envelope carries canonical decoded fields
db1bbb0 test(action-contract): RED frontend sends engine_action_index + canonical_id
154bf04 feat(serializer): face_up uses semantic engine_action_index + canonical_id
87ec930 feat(serializer): emit mayor_island/city_actions with semantic engine_action_index
b29f74a feat(schema): add optional canonical_id to ActionRequestPayload
c0c38ab feat(ingress): canonical_id mismatch returns 422 with structured detail
202b1c0 feat(ml-logger): transition envelope carries canonical decoded fields
6eeacfb feat(types): add engine_action_index/canonical_id to face_up + mayor actions
f1b7e88 feat(frontend): channelAction sends canonical_id; quarry uses semantic 13
d949fb4 feat(mayor-panel): use mayor_island/city_actions with engine_action_index + canonical_id
```

## 비파괴 원칙 확인

- 기존 정상 경로(턴 검증, legal action, websocket 전달, serializer 출력) 유지.
- `action_index` outbound 필드 보존(값만 semantic으로 정정), `canonical_id` 옵셔널 → 기존 클라이언트/테스트 호환.
- `replay`, `ml_logger` fail-open 정책 유지.
- 04-21/04-23 회귀 묶음 통과 보존(인접 테스트의 1건 실패는 본 PR 이전부터 존재).

## 범위 외 (별도 추적)

- Mayor 페이즈에서 같은 tile_type 슬롯이 둘 이상일 때 슬롯-단위 disambiguation — 엔진 한계, 차후 별도 design.
- WS reconnect loop, COOP/`/auth/me` 401 — 별도 triage.
