# frontend/src/types

frontend가 소비하는 canonical type 정의 폴더입니다.

## 현재 파일

- [gameState.ts](gameState.ts): backend serializer rich state, lobby player, final score 타입

## 의존성

- inbound: [../App.tsx](../App.tsx), [../components/README.md](../components/README.md), [../hooks/README.md](../hooks/README.md)
- outbound source: [../../../backend/app/services/state_serializer.py](../../../backend/app/services/state_serializer.py), [../../../contract.md](../../../contract.md)

## 메모

- 타입이 backend보다 더 강한 가정을 가지지 않도록 주의합니다.
