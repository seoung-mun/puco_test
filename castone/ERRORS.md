# ERRORS.md — Mayor 페이즈 버그 수정 내역

이 파일은 Mayor 페이즈 토글 UI 구현 과정에서 발생한 에러와 그 해결 방법을 기록합니다.

---

## 1. `POST /api/action/mayor-finish-placement` → 400 Bad Request

### 증상
이주민 배치 완료 버튼을 눌러도 400 에러가 반환되며 페이즈가 종료되지 않음.

```
puco_backend | INFO: "POST /api/action/mayor-finish-placement HTTP/1.1" 400 Bad Request
detail: "현재 슬롯에 이주민을 배치해야 합니다. 배치 없이 종료할 수 없습니다."
```

### 원인
`mayor-finish-placement` 루프가 현재 플레이어의 슬롯을 모두 처리한 뒤 다음 플레이어로 차례가 넘어간 상태에서도 루프를 계속 돌았다.
다음 플레이어의 첫 슬롯이 `min_place > 0`인 경우 `mask[69]`가 `False`가 되어 HTTPException이 발생함.

### 수정 (`backend/app/api/legacy/actions.py`)
루프 시작 전 `original_player_idx`를 저장하고, `game.current_player_idx != original_player_idx`이면 즉시 break.

```python
original_player_idx = session.game.env.game.current_player_idx
for _ in range(MAX_ITER):
    ...
    if game.current_player_idx != original_player_idx:
        break  # 다음 플레이어 차례 — 봇이 처리
```

---

## 2. Skip 버튼 클릭 시 게임이 중간에 멈춤

### 증상
"Skip Slot" 버튼 클릭 시 이후 버튼이 비활성화되거나 서버 응답이 400으로 반환되며 진행 불가.

### 원인
`mask[69]` (skip=0명 배치)이 `False`인 슬롯에서도 버튼이 표시되어 클릭 가능한 상태였음.
특정 슬롯은 `min_place > 0`으로 강제 배치가 필요해 skip이 허용되지 않음.

### 수정
1. **Backend** (`state_serializer.py`): `mayor_can_skip` 필드 추가 — 현재 슬롯에서 skip(action 69)이 가능한지 여부.
2. **Frontend** (`App.tsx`): Skip 버튼에 `disabled={!state.meta.mayor_can_skip}` 조건 추가.

---

## 3. ECONNREFUSED 172.18.0.4:8000 (Frontend가 Backend에 연결 불가)

### 증상
백엔드를 재시작한 뒤 프론트엔드가 `ECONNREFUSED` 에러를 반환하며 API 요청 전체가 실패.

### 원인
Docker 네트워크 내부에서 백엔드 컨테이너 재시작 시 IP가 변경(`172.18.0.4` → 새 IP)될 수 있으나,
Vite 개발 서버의 DNS 캐시가 구 IP를 계속 참조함.

### 해결
백엔드 재시작 후 **프론트엔드 컨테이너도 재시작**하여 DNS 캐시를 갱신.

```bash
docker-compose restart backend
docker-compose restart frontend
```

또는 전체 재시작:
```bash
docker-compose down && docker-compose up --build
```

---

## 4. IslandGrid Edit 실패 (old_string not found)

### 증상
`Edit` 도구로 `IslandGrid.tsx`의 colonist 슬롯 렌더링을 수정하려 했으나 `String to replace not found in file` 에러 발생.

### 원인
컨텍스트 요약에서 기억한 파일 내용과 실제 파일의 공백/탭/줄바꿈이 미세하게 달랐음.

### 해결
파일을 `Read` 도구로 다시 읽어 정확한 문자열을 확인한 후 재시도.

---

## 5. 멀티플레이어 세션 생성 불가

### 증상
온라인 멀티플레이어 로비 생성 시 에러 발생 (세션 미생성).

### 상태
미해결. 현재 레거시 API (`/api/legacy/`) 기반 단일 플레이어 개인전 우선 구현 중.
멀티플레이어(`/api/v1/`) 구현은 TODO Phase 2에 예정.

---

## 6. 오프라인 개인 플레이 게임방 에러

### 증상
개인 플레이 게임방 진입 시 초기화 에러 발생.

### 상태
미해결. Mayor 페이즈 토글 구현과 별개 이슈. 별도 디버깅 필요.
