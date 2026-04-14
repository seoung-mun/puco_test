# Mayor Large Building Masking Fix

**Date**: 2026-04-14
**Status**: Design approved, pending implementation

## Problem

Mayor 페이즈에서 대형 건물(Guildhall, City Hall, Residence, Fortress, Customs House)에
일꾼을 배치할 때, 다른 대형 건물이 마스킹되어 배치 불가한 버그.

## Root Cause

백엔드 시리얼라이저와 프론트엔드 간 **city_board 인덱스 불일치**.

- `serialize_player`가 `OCCUPIED_SPACE`를 필터링하여 `buildings` 배열 생성
- `_build_mayor_meta`는 엔진의 raw `city_board` 인덱스를 `mayor_legal_city_slots`에 사용
- 프론트엔드 `CityGrid`는 필터링된 배열 인덱스로 legal 체크 → 대형 건물 이후 인덱스 어긋남

### Example

| Engine city_board | Engine idx | Frontend buildings | Frontend idx |
|---|---|---|---|
| Small Indigo | 0 | Small Indigo | 0 |
| Guildhall | 1 | Guildhall | 1 |
| OCCUPIED_SPACE | 2 | *(skipped)* | - |
| City Hall | 3 | City Hall | **2** |
| OCCUPIED_SPACE | 4 | *(skipped)* | - |

`mayor_legal_city_slots = [0, 1, 3]` but frontend checks index `2` for City Hall → mismatch.

## Solution: Dual-Index Approach

### Backend Changes

**1. `state_serializer_support.py` — `serialize_player()`**

Add `engine_slot_idx` to each building entry:

```python
buildings_data = []
for idx, b in enumerate(player.city_board):
    bt = b.building_type
    if bt in (BuildingType.OCCUPIED_SPACE,):
        continue
    ...
    buildings_data.append({
        "name": building_name(bt),
        "engine_slot_idx": idx,  # raw engine index
        ...
    })
```

**2. `state_serializer.py` — `_build_mayor_meta()`**

Convert legal slots to filtered indices:

```python
raw_to_filtered = {}
filtered_idx = 0
for i, b in enumerate(player.city_board):
    if b.building_type in (BuildingType.OCCUPIED_SPACE,):
        continue
    raw_to_filtered[i] = filtered_idx
    filtered_idx += 1

legal_city = []
for i, b in enumerate(player.city_board):
    if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
        cap = BUILDING_DATA[b.building_type][2]
        if b.colonists < cap:
            legal_city.append(raw_to_filtered[i])
```

### Frontend Changes

**3. `types/gameState.ts` — `PlayerBuilding`**

```typescript
export interface PlayerBuilding {
  name: string;
  engine_slot_idx: number;  // added
  max_colonists: number;
  ...
}
```

**4. `CityGrid.tsx` — action callback**

```typescript
// Legal check: unchanged (uses filtered originalIndex)
const isLegal = legalSet != null && entry.building != null && legalSet.has(entry.originalIndex);

// Action dispatch: use engine_slot_idx
onMayorClick={isLegal && onMayorSlotClick
  ? () => onMayorSlotClick(entry.building.engine_slot_idx)
  : undefined}
```

## Constraints

- PuCo_RL folder: read-only, no modifications
- Tests: Docker only, business logic edge cases
- `MayorSequentialPanel.tsx`: uses `action_mask` directly, not affected

## Decision Log

| # | Decision | Alternatives | Rationale |
|---|----------|-------------|-----------|
| 1 | Backend dual-index approach | Frontend mapping, include OCCUPIED_SPACE | Minimal change scope, clear responsibility |
| 2 | Filter legal indices in backend | Let frontend handle mapping | Backend owns data consistency |
| 3 | Add engine_slot_idx to building data | Separate mapping endpoint | Single source of truth per building |
