# 구현 플랜 (2026-03-31)

스펙 문서: `docs/superpowers/specs/2026-03-31-host-leave-and-test-room-cleanup-design.md`

---

## Action Items

```text
[ ] 1. DB 정리 스크립트 작성 및 실행
        파일: castone/backend/scripts/cleanup_all_waiting_rooms.py
        - --dry-run(기본) / --execute 플래그
        - GameLog FK 먼저 삭제 → GameSession 삭제
        - dry-run 결과 확인 후 --execute 실행

[ ] 2. 버그 3 수정: start API 방장 검증 추가
        파일: castone/backend/app/api/channel/game.py
        - str(current_user.id) != str(room.host_id) → 403 반환

[ ] 3. 버그 1 수정: 대기방 "나가기" 버튼 수정
        파일: castone/frontend/src/App.tsx
        - onLogout 핸들러를 onBack과 동일하게: /leave 호출 → closeLobbyWs() → setScreen('rooms')

[ ] 4. lobby_manager.py에 broadcast_game_started() 추가
        파일: castone/backend/app/services/lobby_manager.py
        - 메시지: { type: "GAME_STARTED", state: game_state }
        - 연결된 클라이언트 없으면 no-op

[ ] 5. 버그 2 수정: 게임 시작 시 GAME_STARTED 브로드캐스트
        파일: castone/backend/app/api/channel/game.py
        - start_game() 성공 후 await broadcast_game_started(room_id, rich_state) 호출

[ ] 6. 프론트엔드: GAME_STARTED 메시지 처리 추가
        파일: castone/frontend/src/App.tsx (connectLobbyWs 함수)
        - ws.onmessage에 GAME_STARTED 케이스 추가
        - state 받아서 setState(), setMyPlayerId() → setScreen('game')

[ ] 7. 기존 테스트 실행 및 확인
        명령어: docker exec -it puco_backend pytest /app/tests -v --asyncio-mode=auto

[ ] 8. 신규 테스트 추가
        파일: castone/backend/tests/test_lobby_manager.py
        - broadcast_game_started가 모든 클라이언트에 GAME_STARTED 전송하는지
        - host가 아닌 유저가 start 호출 시 403 반환하는지
```

---

## 발견된 버그 요약

| 번호 | 증상 | 원인 파일 | 수정 항목 |
| --- | --- | --- | --- |
| 버그 1 | 대기방 "나가기" 누르면 "세션 키를 입력하세요:" 화면 뜸 | `App.tsx:851` `onLogout → logout()` | Action Item 3 |
| 버그 2 | 방장만 게임 화면으로 이동, 다른 유저는 대기방에 갇힘 | `game.py` + `lobby_manager.py` GAME_STARTED 브로드캐스트 없음 | Action Item 4, 5, 6 |
| 버그 3 | 방 참가자 누구나 start API 호출 가능 | `game.py` host_id 검증 없음 | Action Item 2 |

---

## 레거시 정리 후보 (이번 범위 밖 — 추후 별도 작업)

| 항목 | 이유 |
| --- | --- |
| `castone/backend/app/api/legacy/` 패키지 전체 | 21개 엔드포인트 중 20개 미사용. `/api/bot-types`만 채널 API로 이전 필요 |
| `castone/frontend/src/components/JoinScreen.tsx` | 버그 1의 원인, `RoomListScreen`으로 대체 완료 |
| `castone/frontend/src/hooks/useGameSSE.ts` | `sessionKey: null`로 비활성화됨, `useGameWebSocket`으로 대체 |
| `castone/backend/app/services/session_manager.py` | 레거시 전용, 채널과 무관 |
| `castone/backend/app/services/event_bus.py` | SSE 전용, 채널에서 WS로 대체 |

---

## Docker 운영 명령어

```bash
# 테스트 실행
docker exec -it puco_backend pytest /app/tests -v --asyncio-mode=auto

# DB 확인
docker exec -it puco_db psql -U puco_user -d puco_rl
# → SELECT * FROM games WHERE status = 'WAITING';

# Redis 확인
docker exec -it puco_redis redis-cli
# → KEYS *, HGETALL game:<game_id>:meta

# 로그 확인
docker logs -f puco_backend
```
