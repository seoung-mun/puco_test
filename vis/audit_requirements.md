# audit.md -> vis/ 매핑

이 문서는 루트의 `audit.md` 요구사항을 `vis/` 도구와 연결해 놓은 인덱스다.

## 1. Data Lineage & Step Alignment

목표:
- 엔진 상태
- bot input
- serializer state
- DB/JSONL 로그

이 네 축이 같은 step을 가리키는지 확인

도구:

- `vis/render_lineage_report.py`
- `vis/render_storage_report.py`

핵심 출력:

- step alignment table
- runtime flow Mermaid
- DB/JSONL/replay reconciliation gap

## 2. Determinism & Reproducibility

목표:
- 같은 seed면 같은 초기 상태/결과가 재현되는지 확인

현재 가능한 것:

- 코드상 seed/governor 테스트 존재 여부 확인
- room/model provenance snapshot 확인

현재 부족한 것:

- runtime game log에 `game_seed` 없음
- replay 재현용 `step_id`/`state_hash` 없음

도구:

- `vis/render_audit_requirements.py`

## 3. Behavioral Traceability

목표:
- 모델이 어떤 phase에서 어떤 mask를 보고 어떤 action을 냈는지 추적

도구:

- `vis/render_behavior_report.py`

핵심 출력:

- bot_type별 액션 수
- phase별 행동 분포
- trader/captain pass/load 집계
- artifact provenance

주의:

- 현재는 action probability / logits가 없어서 heatmap은 부분적으로만 가능

## 4. Storage Integrity

목표:
- PostgreSQL
- JSONL
- replay JSON
- Redis 역할 분리
- 저장소 간 불일치 탐지

도구:

- `vis/render_storage_report.py`

핵심 출력:

- DB row count
- JSONL row count
- replay entry count / format
- state chain break count
- missing DB / missing JSONL / missing replay rows

## 5. Online Monitoring

목표:
- 실시간 추론/상태 전달 문제를 운영 관점에서 추적

현재 가능한 것:

- WS 이벤트 존재 여부
- GAME_ENDED / PLAYER_DISCONNECTED 이벤트 코드 존재

현재 부족한 것:

- `state_revision`
- terminal delivery latency
- inference latency

도구:

- `vis/render_audit_requirements.py`
- `vis/render_lineage_report.py`

## 권장 실행 순서

1. `render_lineage_report.py`
2. `render_storage_report.py`
3. `render_behavior_report.py`
4. `render_audit_requirements.py`
