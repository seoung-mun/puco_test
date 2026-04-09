# vis/

`vis/` 폴더는 Castone의 실제 게임 데이터를 사람이 직접 따라가며 확인할 수 있게 만든 시각화/감사 도구 모음이다.

핵심 아이디어는 간단하다.

- DB `game_logs`
- 로컬 `data/logs/games/<game_id>.jsonl`
- 로컬 `data/logs/replay/<game_id>.json`
- 런타임 코드가 만드는 `model_versions`, `model_info`, `state_summary`

이 세 축을 읽어서 Markdown + Mermaid 리포트로 뽑는다.

## 들어 있는 파일

- `render_lineage_report.py`
  - 엔진 -> 서비스 -> DB/JSONL -> WS 흐름을 한 게임 기준으로 시각화
- `render_storage_report.py`
  - DB, JSONL, replay가 얼마나 맞는지, 체인 무결성과 replay 포맷이 기대와 맞는지 확인
- `render_behavior_report.py`
  - bot_type, phase, action, model provenance 기준으로 행동을 읽기 쉽게 정리
- `render_audit_requirements.py`
  - `audit.md` 요구사항별로 현재 어떤 증거가 있고 무엇이 비어 있는지 요약
- `db/README.md`
  - DB/로컬 로그를 사람이 수동으로 확인하는 방법

## 빠른 사용 예시

JSONL만 있는 경우:

```bash
python vis/render_lineage_report.py \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --lang ko \
  --output vis/output/lineage.md
```

PostgreSQL 또는 SQLite까지 같이 읽는 경우:

```bash
DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/castone" \
python vis/render_storage_report.py \
  --game-id YOUR_GAME_ID \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --lang ko \
  --output vis/output/storage.md
```

행동 추적 리포트:

```bash
python vis/render_behavior_report.py \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --lang ko \
  --output vis/output/behavior.md
```

`audit.md` 요구사항 매핑:

```bash
python vis/render_audit_requirements.py \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --lang ko \
  --output vis/output/audit.md
```

## 출력 형식

모든 스크립트는 Markdown을 생성한다.

- 표: 실제 row count, 필드 커버리지, 불일치 목록
- Mermaid: 흐름도, 시퀀스 다이어그램

`--output`으로 넘긴 경로의 부모 디렉터리는 자동으로 생성된다. 즉 `vis/output/` 폴더는 미리 만들어 두지 않아도 된다.

그래서 아래 어디에서든 바로 읽을 수 있다.

- VS Code Markdown Preview
- GitHub/Gitea 류 Markdown 뷰어
- Codex/Chat 앱에서 파일 열기

## 현재 도구의 솔직한 한계

현재 기본 전이 저장 형식은 game 당 하나의 JSONL 파일이다.

- 새 형식: `data/logs/games/<game_id>.jsonl`
- 예전 일간 형식: `data/logs/transitions_YYYY-MM-DD.jsonl`

`vis/` 도구는 두 형식을 함께 읽고, 같은 `game_id`의 행을 합쳐서 본다.

기존 일간 로그를 game 당 파일로 쪼개려면:

```bash
python backend/scripts/migrate_transition_logs_to_per_game.py
```

현재 코드베이스에는 아직 아래 필드가 없다.

- `step_id`
- `state_hash`
- `state_revision`
- action probability / logits
- inference latency

그래서 `vis/` 도구는 이 값들을 "있는 척" 하지 않는다.
대신 현재 실제로 남는 증거와 아직 비어 있는 지점을 같이 보여준다.

추가로 현재 `replay JSON`은 자동 검증 대상에 포함되지만, 모든 리포트가 replay를 주 데이터 소스로 삼는 것은 아니다.  
행동 분포 분석의 1차 입력은 여전히 JSONL 전이 로그다.
