# PuCo_RL/models

서버에서 실제로 사용하는 체크포인트와 sidecar 메타데이터를 함께 보관합니다.

- `*.pth`: 서빙 체크포인트
- `*.json`: 체크포인트 sidecar 메타데이터

현재 기본 서빙 파일:

- `PPO_PR_Server_순수자기대결_20260406_135525_step_99942400.pth`
- `HPPO_PR_Server_1774241514_step_14745600.pth`

운영 규칙:

- `.env`의 `PPO_MODEL_FILENAME`, `HPPO_MODEL_FILENAME`는 이 디렉터리의 실제 파일명과 일치해야 합니다.
- 새 체크포인트를 추가할 때는 같은 basename의 `.json` sidecar를 반드시 같이 커밋합니다.
- replay / ML 로그의 `model_versions`, `parity` 필드는 이 sidecar 메타데이터를 기준으로 채워집니다.
