# Action Value Heuristic Agent - 수식 정리 문서 (v2.1)

> Puerto Rico 보드게임을 위한 휴리스틱 기반 에이전트의 상태 평가 함수 및 액션 보너스 함수 수식 정리

---

## 📋 목차

1. [핵심 상수](#1-핵심-상수)
2. [메인 휴리스틱 함수](#2-메인-휴리스틱-함수-h-s)
3. [V_realized (확정 가치)](#3-v_realized-확정-가치)
4. [V_potential (잠재 가치)](#4-v_potential-잠재-가치)
5. [액션 보너스 함수](#5-액션-보너스-함수)
6. [헬퍼 함수](#6-헬퍼-함수)

---

## 1. 핵심 상수

### 1.1 환산 상수

| 상수명 | 값 | 설명 |
|--------|-----|------|
| `_DOUBLOON_TO_VP` | **0.25** | 더블론 → VP 환산 (4더블론 = 1VP) |
| `_SHIPPING_SUCCESS_PROB` | **0.7** | 선적 성공 확률 |
| `_TOTAL_ROLE_SELECTIONS` | **51.0** | 총 역할 선택 횟수 (3인, 17라운드) |
| `_NUM_ROLES` | **6.0** | 역할 종류 수 |
| `_EXPECTED_ROLE_USES_BASE` | **8.5** | 51/6, 균등 분포 가정 |
| `COLONIST_DISCOUNT` | **0.5** | colonist 배치 불확실성 |

### 1.2 상품 가격표

| 상품 | `_GOOD_TRADE_PRICES` | `_GOOD_UNIT_VALUES` | `_GOOD_TRADE_BONUS` |
|------|---------------------|---------------------|---------------------|
| Coffee | 4 | 1.0 | 0.5 |
| Tobacco | 3 | 1.0 | 0.4 |
| Sugar | 2 | 1.0 | 0.2 |
| Indigo | 1 | 1.0 | 0.1 |
| Corn | 0 | 1.0 | 0.0 |

### 1.3 상업 건물 능력 가치 (`_COMMERCIAL_ABILITY_VALUES`)

| 건물 | ability_vp | 비고 |
|------|------------|------|
| Small Market | 0.25 | 1 doubloon |
| Large Market | 0.50 | 2 doubloons |
| Office | 0.20 | 중복 판매 |
| Harbor | 1.0 | 추가 VP/선적 |
| Wharf | 1.5 | 자유 선적 |
| Small Warehouse | 0.3 | 상품 보존 |
| Large Warehouse | 0.5 | 상품 보존 |
| Factory | **동적** | `_factory_bonus_value()` |
| Hacienda | 0.15 | 무료 농장 |
| Construction Hut | 0.15 | 채석장 접근 |
| Hospice | 0.20 | 무료 colonist |
| University | 0.20 | 건물에 colonist |

---

## 2. 메인 휴리스틱 함수: H(s)

```
H(s) = V_realized + V_potential
```

여기서:
- **V_realized**: 게임 종료 시 **확실히 얻는** VP (decay 미적용)
- **V_potential**: 미래 행동으로 VP로 **전환 가능한** 자원 (decay 적용)

### Game Progress (진행도)

$$\text{progress} = \max(\text{vp\_progress}, \text{city\_progress}, \text{colonist\_progress})$$

| 진행도 지표 | 수식 |
|-------------|------|
| vp_progress | $1 - \frac{\text{remaining\_vp}}{\text{initial\_vp}}$ |
| city_progress | $\frac{\max(\text{player\_city\_fill})}{12}$ |
| colonist_progress | $1 - \frac{\text{remaining\_colonists}}{\text{initial\_colonists}}$ |

$$\text{decay} = \max(0, 1 - \text{progress})$$

---

## 3. V_realized (확정 가치)

$$V_{realized} = \text{VP}_{chips} + \sum_{b \in Buildings} \text{VP}_b + V_{large\_active}$$

### 3.1 VP 칩
$$\text{VP}_{chips} = p.\text{vp\_chips}$$

### 3.2 건물 기본 VP
$$\sum_{b \in Buildings} \text{VP}_b = \sum_{b \in \text{city\_board}} \text{BUILDING\_DATA}[b][1]$$

### 3.3 활성화된 대형 건물 동적 보너스

> 조건: `colonists > 0` AND `is_large == True`

| 건물 | 수식 |
|------|------|
| **City Hall** | $N_{violet}$ (보라색 건물 수) |
| **Customs House** | $\lfloor \text{VP}_{chips} / 4 \rfloor$ |
| **Fortress** | $\lfloor N_{colonists} / 3 \rfloor$ |
| **Residence** | `_residence_bonus(island_tiles)` |
| **Guildhall** | $2 \times N_{large\_prod} + 1 \times N_{small\_prod}$ |

#### Residence 보너스 함수

```python
def _residence_bonus(island_tiles):
    if island_tiles <= 9:  return 4
    elif island_tiles == 10: return 5
    elif island_tiles == 11: return 6
    else: return 7
```

---

## 4. V_potential (잠재 가치)

$$V_{potential} = V_{goods} + V_{doubloons} + V_{production} + V_{commercial} + V_{infrastructure}$$

---

### 4.1 V_goods (보유 상품 가치)

$$V_{goods} = \left[ \sum_{g \in Goods} \left( \text{qty}(g) \times 1.0 \times P_{ship} + \text{qty}(g) \times \text{trade\_bonus}(g) \times \text{decay} \right) \right] \times \text{weak\_decay}$$

여기서:
- $P_{ship} = 0.7$ (선적 성공 확률)
- $\text{weak\_decay} = 0.5 + 0.5 \times \text{decay}$
- $\text{trade\_bonus}(g)$: 상품별 판매 옵션 가치

| 상품 | trade_bonus | 근거 |
|------|-------------|------|
| Coffee | 0.5 | 4더블론 | 
| Tobacco | 0.4 | 3더블론 |
| Sugar | 0.2 | 2더블론 |
| Indigo | 0.1 | 1더블론 |
| Corn | 0.0 | 0더블론 |

---

### 4.2 V_doubloons (더블론 가치)

$$V_{doubloons} = \text{doubloons} \times 0.25 \times \text{decay}$$

---

### 4.3 V_production (생산력 가치)

$$V_{production} = \sum_{g \in Goods} \text{capacity}(g) \times 1.0 \times E[role] \times P_{ship}$$

여기서:
- $E[role] = 8.5 \times \text{decay}$
- $P_{ship} = 0.7$

#### capacity(g) 계산

```python
def _production_capacity(good):
    occupied_plantations = count_occupied_plantations(good)
    
    if good == CORN:
        return occupied_plantations  # 건물 불필요
    
    building_slots = count_building_colonists(good)
    return min(occupied_plantations, building_slots)
```

---

### 4.4 V_commercial (활성 상업 건물 가치)

$$V_{commercial} = \sum_{b \in \text{Active\_Commercial}} \text{ability\_vp}(b) \times E[role]$$

조건: `colonists > 0`

#### Factory 동적 가치

```python
def _factory_bonus_value():
    num_types = count_producible_good_types()
    
    # Factory: 생산 종류에 따라 0/1/2/3/5 더블론
    doubloon_bonus = {
        0: 0, 1: 0, 2: 1, 3: 2, 4: 3, 5: 5
    }.get(num_types, 5)
    
    return doubloon_bonus * 0.25  # VP 환산
```

---

### 4.5 V_infrastructure (인프라 잠재 가치)

$$V_{infrastructure} = V_{empty\_plantations} + V_{inactive\_buildings} + V_{inactive\_large}$$

#### (a) 빈 농장의 잠재 생산 가치

$$V_{empty\_plantations} = \sum_{g \in Goods} \text{additional\_capacity}(g) \times 1.0 \times E[role] \times P_{ship} \times \text{COLONIST\_DISCOUNT}$$

```python
def additional_capacity(good):
    occupied = count_occupied_plantations(good)
    unoccupied = count_unoccupied_plantations(good)
    
    if good == CORN:
        return unoccupied  # 건물 제한 없음
    
    building_slots = count_building_slots(good)
    current_capacity = min(occupied, building_slots)
    headroom = max(0, building_slots - current_capacity)
    
    return min(unoccupied, headroom)
```

#### (b) 빈 건물 슬롯의 잠재 가치

**생산 건물:**
$$V = \text{effective\_empty} \times 1.0 \times E[role] \times P_{ship} \times \text{COLONIST\_DISCOUNT}$$

```python
effective_empty = min(
    empty_slots,
    max(0, occupied_plantations - current_building_colonists)
)
```

**상업 건물 (colonists=0):**
$$V = \text{ability\_vp}(b) \times E[role] \times \text{COLONIST\_DISCOUNT}$$

#### (c) 비활성 대형 건물

$$V_{inactive\_large} = \text{estimated\_bonus} \times \text{COLONIST\_DISCOUNT}$$

| 건물 | estimated_bonus |
|------|-----------------|
| City Hall | $N_{violet} + 2$ |
| Customs House | $\lfloor \text{VP}_{chips} / 4 \rfloor + 2$ |
| Fortress | $\lfloor N_{colonists} / 3 \rfloor + 1$ |
| Residence | `_residence_bonus(island_tiles)` |
| Guildhall | $2 \times N_{large} + 1 \times N_{small} + 2$ |
| 기타 | 5.0 |

---

## 5. 액션 보너스 함수

전체 액션 가치:
$$\text{action\_value} = H(s) + \text{bonus}(a)$$

### 5.1 역할 선택 보너스 (action 0-7)

| 역할 | 보너스 수식 |
|------|-------------|
| **Settler** | $0.3 \times \text{decay}$ (if island_space > 0) |
| **Mayor** | $\min(\text{empty\_slots}, \text{colonist\_supply}) \times 0.15 \times \text{decay}$ |
| **Builder** | $0.5 \times \text{decay}$ (if doubloons ≥ 1) |
| **Craftsman** | $\sum_g \text{capacity}(g) \times 0.3 \times \text{decay}$ |
| **Trader** | $\sum_g P_{trade}(g) \times \text{price}(g) \times 0.25$ |
| **Captain** | $\sum_g \text{goods}(g) \times 0.4 \times \text{decay}$ |
| **Prospector** | $0.25 \times \text{decay}$ |

**공통:** $+\ \text{role\_doubloons} \times 0.25 \times \text{decay}$

---

### 5.2 농장 선택 보너스 (action 8-14)

| 타입 | 보너스 수식 |
|------|-------------|
| **Quarry** | $0.8 \times \text{decay}$ |
| **Corn** | $(0.3 + 0 \times 0.1) \times \text{decay}$ |
| **기타 (건물 있음)** | $(0.4 + \text{price} \times 0.15) \times \text{decay}$ |
| **기타 (건물 없음)** | $(0.2 + \text{price} \times 0.05) \times \text{decay}$ |

---

### 5.3 건물 구매 보너스 (action 16-38)

$$\text{bonus} = \text{VP}_b + \text{large\_bonus} + \text{production\_bonus} + \text{commercial\_bonus}$$

| 컴포넌트 | 수식 |
|----------|------|
| VP_b | `BUILDING_DATA[b][1]` |
| large_bonus | $+2.0$ (if is_large) |
| production_bonus | $\text{price}(g) \times 0.25 \times \text{decay}$ |
| commercial_bonus | $\text{ability\_vp}(b) \times E[role]$ |

> **Factory 특수 처리:** `_factory_bonus_value()` 동적 호출

---

### 5.4 선적 보너스 (action 44-63)

$$\text{bonus} = \text{qty} \times 1.0 + \text{harbor\_bonus}$$

```python
qty = min(goods[good], ship_capacity - ship_load)
harbor_bonus = qty * 1.0  # if Harbor active
```

---

### 5.5 저장 보너스 (action 64-68)

$$\text{bonus} = \text{qty} \times \max(0.3, \text{price} \times 0.25 \times 0.6) \times \text{decay}$$

---

### 5.6 판매 보너스 (action 69-73)

$$\text{bonus} = \text{total\_price} \times 0.25 \times \text{decay}$$

```python
total_price = base_price
if small_market_active: total_price += 1
if large_market_active: total_price += 2
```

---

### 5.7 Wharf 선적 보너스 (action 74-78)

$$\text{bonus} = \text{qty}(g) \times 1.0$$

---

## 6. 헬퍼 함수

### 6.1 `_trade_probability(good)`

판매 성공 확률 추정

$$P_{trade}(g) = \frac{1}{1 + 0.3 \times N_{ahead}}$$

```python
def _trade_probability(good):
    # Office가 있으면 trading_house 중복 무시
    if good in trading_house and not has_office:
        return 0.0
    
    # 나보다 앞선 턴에서 해당 상품을 *보유한* 경쟁자 수
    ahead_competitors = count_players_with_good_ahead_in_turn(good)
    
    return 1.0 / (1.0 + ahead_competitors * 0.3)
```

---

### 6.2 `_count_empty_slots()`

빈 colonist 슬롯 수

$$N_{empty} = N_{empty\_plantation} + N_{empty\_building}$$

---

### 6.3 `_expected_role_uses(decay)`

남은 게임 기간 역할 기대 사용 횟수

$$E[role] = \frac{51}{6} \times \text{decay} \approx 8.5 \times \text{decay}$$

---

## 📊 요약 테이블

### 잠재 가치 구성요소

| 구성요소 | 핵심 수식 | decay 적용 |
|----------|----------|-----------|
| V_goods | $\sum qty \times (P_{ship} + \text{trade\_bonus} \times \text{decay}) \times \text{weak\_decay}$ | weak_decay |
| V_doubloons | $\text{doubloons} \times 0.25 \times \text{decay}$ | ✅ |
| V_production | $\sum \text{capacity} \times E[role] \times P_{ship}$ | E[role]에 포함 |
| V_commercial | $\sum \text{ability\_vp} \times E[role]$ | E[role]에 포함 |
| V_infrastructure | 빈 슬롯 × E[role] × P_{ship} × 0.5 | E[role]에 포함 |

### 핵심 파라미터 영향

| 파라미터 | 영향 범위 | 민감도 |
|----------|----------|--------|
| P_ship (0.7) | V_goods, V_production, V_infrastructure | High |
| E[role] (8.5) | V_production, V_commercial, V_infrastructure | High |
| COLONIST_DISCOUNT (0.5) | V_infrastructure | Medium |
| DOUBLOON_TO_VP (0.25) | 전체 더블론 관련 | Medium |

---

*문서 버전: v2.1 (2026-04-07)*
