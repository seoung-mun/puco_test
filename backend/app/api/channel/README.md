# backend/app/api/channel

현재 Castone 프론트엔드가 기본으로 사용하는 공개 API 경계입니다.

## 역할

- Google auth, room lifecycle, game action, lobby/game websocket 제공
- slot-direct Mayor를 포함한 현재 channel contract 유지
- spectator/host/bot game 진입 흐름 지원

## 주요 파일

- [auth.py](auth.py): 로그인, 토큰 기반 사용자 정보
- [room.py](room.py): 방 생성/조회/입장/봇전 생성
- [game.py](game.py): 게임 시작, 액션 제출, 최종 점수 조회
- [playback.py](playback.py): 봇 전용 게임 배속/일시정지 컨트롤
- [replay.py](replay.py): 종료 게임 리플레이 목록/상세 조회
- [ws.py](ws.py): 게임 상태 WebSocket
- [lobby_ws.py](lobby_ws.py): 로비 상태 WebSocket

## 의존성

- outbound: [../../services/README.md](../../services/README.md), [../../schemas/README.md](../../schemas/README.md), [../../core/security.py](../../core/security.py)
- sibling fallback: [../legacy/README.md](../legacy/README.md)

## 계약 메모

- Mayor는 `POST /action`에 `120 + TileType.value` (island, 범위 120-125) / `140 + BuildingType.value` (city, 범위 140-162) 의미 인덱스를 보냅니다.
- `POST /action`은 optional `payload.canonical_id`를 받으며, 디코드 결과와 다르면 422 (`canonical_id_mismatch`)를 돌려줍니다.
- legacy `POST /mayor-distribute`는 `410 Gone`으로 막혀 있습니다.
- 실시간 상태 전달의 기준은 WebSocket `STATE_UPDATE`입니다.
- 봇 전용 게임만 `playback` 컨트롤 호출이 가능합니다 (기타는 403).
- 새 프론트 기능은 가능하면 이 폴더에만 API를 추가합니다.
