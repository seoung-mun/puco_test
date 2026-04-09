# backend/app/services/agents

이 디렉터리는 현재 사실상 비활성/레거시 자리입니다.

## 현재 상태

- canonical agent 접근은 [../engine_gateway/README.md](../engine_gateway/README.md)와 [../../../PuCo_RL/agents/README.md](../../../PuCo_RL/agents/README.md)를 통해 이뤄집니다.
- 과거 backend-local wrapper/registry 흔적이 남아 있을 수 있지만, 새 기능의 기본 추가 위치는 아닙니다.

## 권장 방향

- backend가 특정 agent 구현 세부사항을 다시 소유하지 않도록 유지합니다.
