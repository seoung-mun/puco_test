# PuCo_RL/common — Adapter & Bundle 레이어 가이드

이 폴더는 **학습 결과물(.pth)을 web/serving에 공급하는 어댑터 레이어**다.
PuCo_RL은 학습 폴더이면서 동시에 백엔드(`backend/app`)가 inference 시 import해서 쓰는
공유 의존성이기도 하므로, 여기 두는 코드는 **학습 코드와 서빙 코드 양쪽이 동일하게 import**한다.

## 구성

| 파일 | 역할 |
|------|------|
| `base_adapter.py` | `PolicyAdapter` ABC + `DecodeResult`. 모든 adapter는 이 인터페이스를 따른다. |
| `semantic293_adapter.py` | 현재 pr_env.py(293-dim semantic obs / 200-dim action)용 concrete adapter. |
| `bundle.py` | `write_bundle()` — `.pth` + `manifest.json`을 한 디렉터리로 패키징. |
| `adapter.py` | (legacy) 이전 어댑터 — 새 코드에서는 사용 안 함. |

## 1. 학습 → 번들 → 웹 흐름

```
train_ppo_*_server.py
   │
   ├── torch.save(state_dict) → models/ppo_checkpoints/{prefix}/{run}_step_{N}.pth
   └── write_bundle()        → models/ppo_checkpoints/{prefix}/{run}_step_{N}_bundle/
                                  ├── checkpoint.pth     (.pth 사본)
                                  └── manifest.json      (schema_version=model-bundle.v2)

웹 서빙
   PPO_BUNDLE_DIR=ppo_checkpoints/{prefix}/{run}_step_{N}_bundle
   → backend/app/services/agent_registry.py 가 manifest 읽고 AdapterRuntime 구성
   → bot_service.py 가 인퍼런스 시 adapter 경로 사용
```

`PPO_BUNDLE_DIR`는 `PuCo_RL/models/` 기준 상대 경로다.
현재 기본 champion bundle은 `ppo-pr-server-semantic293-20260419` 이고,
backend registry의 `ppo` 엔트리는 이 번들을 기본 adapter 경로로 사용한다.

## 2. 자주 묻는 시나리오

### Q. 이미 학습된 .pth만 있고 번들은 없는데, 잠깐 학습을 돌리면 번들이 생기나?

**예.** 단, 다음 조건을 만족해야 한다.

1. `--load_ckpt /path/to/old.pth` 로 기존 weight를 이어 받고
2. `--write_bundle` 가 켜져 있어야 한다 (default ON)
3. 그 .pth가 **현재 pr_env.py와 같은 obs_dim/action_dim**으로 학습된 것이어야 한다.

`SNAPSHOT_INTERVAL`(기본 25 update)마다 `.pth`와 함께 `_bundle/`이 만들어진다.
빠르게 번들만 뽑고 싶으면 그 한 번만 돌고 Ctrl-C 해도 된다.

만약 obs_dim 불일치로 `load_state_dict`에서 shape mismatch가 나면 그 .pth는 옛날
pr_env로 학습된 것이며, 해당 모델은 **재학습 외에는 살릴 방법이 없다.**

### Q. 체크포인트로 재개해도 번들이 함께 생성되나?

그렇다. 번들 생성은 매 SNAPSHOT 시점에 `.pth`를 쓰는 직후에 동일 디렉터리에서
일어나고, `--load_ckpt` 여부와 무관하게 동작한다.

### Q. 번들을 강제로 만들고 싶지 않다 (디스크 절약)?

`--no-write_bundle` (`argparse.BooleanOptionalAction`) 으로 끈다.

## 3. pr_env.py / ppo_agent.py가 바뀔 때 해야 할 일

### A. obs space가 바뀐 경우 (예: 293 → 305)

기존 `Semantic293TypeMayorAdapter`는 더 이상 통하지 않는다.

1. `semantic293_adapter.py` 를 복제하여 새 dim 기준 어댑터를 만든다.
   파일명은 차원/시맨틱을 반영 (예: `semantic305_adapter.py`).
2. `adapter_id`를 새 버전으로 (예: `puco.semantic305.type_mayor.v1`).
3. `obs_dim` 상수, `encode_obs()` 의 슬라이싱 분량을 바꾼다.
4. `backend/tests/test_bundle_integration.py` 의 obs parity 테스트가
   **새 어댑터로 env flatten == adapter encode_obs** 인지 검증한다.
   이 테스트가 깨지면 학습/서빙 obs가 어긋난 것이므로 절대 머지하면 안 된다.
5. 새 모델을 학습 → 번들 자동 생성.
6. 번들의 `manifest.json` 에서 `adapter_module` 을 새 어댑터 경로로 명시.
   현재 trainer는 `bundle.py` 의 default(`common.semantic293_adapter:...`) 를 쓰므로,
   `train_ppo_*_server.py` 의 `write_bundle(..., adapter_module=...)` 호출을 같이 바꾼다.

### B. action space가 바뀐 경우 (예: 200 → 220)

1. 어댑터의 `action_dim`, `encode_action_mask()`, `decode_action()` 매핑 갱신.
2. `backend/app/services/canonical_action.py` 가 새 action enum을 반환하도록 갱신.
3. 새 모델 학습 후 번들 생성. 옛 모델은 호환 안 됨.
4. `manifest.json` 의 `canonical_action_version` 을 bumping 하는 것이 안전
   (예: `castone.canonical-action.v2`). 백엔드의
   `model_registry.ACTION_SPACE_FINGERPRINT_*` 도 업데이트.

### C. PPO 네트워크 구조만 바뀐 경우 (예: hidden_dim 512 → 768)

state space는 같으니 어댑터는 그대로 둔다. 단:

1. `bundle.py` default `network={"hidden_dim": 512, "num_res_blocks": 3}` 가
   고정값이라, 새 구조를 쓰면 `write_bundle(..., network={...})` 인자로 정확히 넘긴다.
2. 백엔드 `AdapterRuntime` 가 `Agent(obs_dim, action_dim)` 로 인스턴스화하므로
   `agents/ppo_agent.py` 의 `Agent` 시그니처가 바뀌면 manifest의 `network` 필드를 받아
   생성하도록 backend 쪽 builder도 같이 손봐야 한다.

### D. 어댑터 로직만 바뀐 경우 (시맨틱 동일, 구현 개선)

`adapter_version` 만 올리고(예: 1.0.0 → 1.1.0) 같은 모델 weight로 새 번들을 발행해도 된다.
단, **`encode_obs()` 출력 바이트가 한 비트라도 달라지면** 그건 시맨틱 변경이므로
A 항목으로 처리한다.

## 4. Manifest 스키마 (model-bundle.v2)

```json
{
  "schema_version": "model-bundle.v2",
  "bundle_id": "PPO_PR_Server_..._step_481689600",
  "family": "ppo",
  "policy_tag": "candidate",
  "architecture": "ppo_residual",
  "checkpoint_file": "checkpoint.pth",
  "checkpoint_sha256": "...",
  "adapter_module": "common.semantic293_adapter:Semantic293TypeMayorAdapter",
  "adapter_version": "1.0.0",
  "canonical_state_version": "castone.canonical-state.v1",
  "canonical_action_version": "castone.canonical-action.v1",
  "obs_dim": 293,
  "action_dim": 200,
  "num_players": 3,
  "network": {"hidden_dim": 512, "num_res_blocks": 3},
  "compatibility": {
    "supported_canonical_state_versions": ["castone.canonical-state.v1"],
    "supported_canonical_action_versions": ["castone.canonical-action.v1"]
  }
}
```

`extra_metadata` 로 trainer 이름·`run_name`·`global_step` 등 자유 필드 추가 가능.

## 5. 학습/서빙 obs parity 안전망

학습 obs ≠ 서빙 obs 이면 모델은 의미 없는 입력을 받게 되어 성능이 무너진다.
이 폴더의 어댑터는 `pr_env.py` 의 `flatten_dict_observation()` 결과를 **그대로**
재현하도록 짜여 있고, 그것을 backend test가 검증한다:

- `backend/tests/test_bundle_integration.py::test_adapter_obs_parity_with_env_flatten_initial`
- `..._at_mayor`

pr_env가 dict 키를 추가/삭제하거나 정렬 순서가 달라지면 (sorted alphabetical 가정이 깨지면)
이 테스트가 즉시 깨진다. obs space를 만지는 PR은 항상 이 테스트로 검증할 것.

## 6. 학습 코드에 끼친 영향 요약

이번 어댑터 리팩터가 **학습 로직 자체에 미친 영향은 없다.**
변경된 것은:

- `train_ppo_*_server.py` 가 SNAPSHOT 시점에 `write_bundle()` 을 추가로 호출 (no-op 가능).
- `common/` 폴더가 추가되었지만, trainer는 `from common.bundle import write_bundle` 만 import.

`agents/ppo_agent.py`, `env/pr_env.py`, GAE/loss/PBRS 등 학습 코어는 손대지 않았다.
따라서 기존 학습 스크립트는 동일 hyperparameter로 동일 결과를 낸다.
