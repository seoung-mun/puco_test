# 버그 해결 설계도

**날짜:** 2026-04-01
**대상 에러:** error.md `# 현재 발생중인 에러` 섹션 1, 2

---

## 에러 1 — 봇 모델 아키텍처 불일치 (봇 액션 불가)

### 증상

```
strict=True load failed for ppo_agent_update_100.pth:
  Missing keys: embed.*, shared_trunk.*, actor_head.*, critic_head.*
  Unexpected keys: critic.0~4, actor.0~4
  → retrying strict=False
```

봇이 액션을 하지 않거나 항상 같은 (유효하지 않은) 액션만 선택한다.

- 나중에 더 많은 알고리즘으로 에이전트가 추가될 예정이라 인터페이스 클래스를 만들어야함
- PuCo_RL의 base_agent.py 파일을 읽고 그에 맞춰 아키텍쳐를 설계하고, 환경을 맞출것
- **서빙/훈련 환경을 일치 시켜야함**
- **mlopsp-engineer의 관점에서 실제로 훈련된 모델이 실상황에서 사용될 때도 훈련된 가중치를 정확하게 사용할 수 있어야함**


---

### 근본 원인 분석

체크포인트 파일(`ppo_agent_update_100.pth`)과 현재 코드의 `Agent` 클래스 아키텍처가 **완전히 다르다.**

| 구분 | 체크포인트 (구버전) | 현재 `Agent` 클래스 (신버전) |
|------|-------------------|--------------------------|
| 레이어 구조 | `actor/critic` 각 3-Linear (Tanh 활성화) | `embed → shared_trunk(ResidualBlock×3) → actor_head/critic_head` |
| obs_dim | 210 | 210 (동일) |
| hidden | 256 | 512 |
| actor 출력 키 | `actor.0/2/4.weight/bias` | `actor_head.0~3.*` |
| critic 출력 키 | `critic.0/2/4.weight/bias` | `critic_head.0~3.*` |

`strict=False` 폴백으로 가중치를 로드하지만, **레이어 shape가 전혀 맞지 않아** 실질적으로 무작위 초기화와 동일하게 동작한다.

```
체크포인트 actor.0.weight: (256, 210)  ← 구버전 레이어
현재 embed.0.weight:       (512, 210)  ← 신버전 레이어
→ 어떤 키도 실제로 로드되지 않음
```

---

### 해결 방안

**방안 A (권장): `LegacyPPOAgent` 클래스 추가** — 구버전 체크포인트 호환

구버전 아키텍처 클래스를 `ppo_agent.py`에 추가하고, `MODEL_TYPE=legacy_ppo` 환경변수로 선택 가능하게 한다.

```python
# castone/PuCo_RL/agents/ppo_agent.py 에 추가

class LegacyPPOAgent(nn.Module):
    """
    구버전 CleanRL 스타일 PPO 아키텍처.
    ppo_agent_update_*.pth 체크포인트 호환용.

    구조: Linear(obs→256) → Tanh → Linear(256→256) → Tanh → Linear(256→action)
    """
    def __init__(self, obs_dim: int, action_dim: int = 200):
        super().__init__()
        self.critic = nn.Sequential(
            layer_init(nn.Linear(obs_dim, 256)),
            nn.Tanh(),
            layer_init(nn.Linear(256, 256)),
            nn.Tanh(),
            layer_init(nn.Linear(256, 1), std=1.0),
        )
        self.actor = nn.Sequential(
            layer_init(nn.Linear(obs_dim, 256)),
            nn.Tanh(),
            layer_init(nn.Linear(256, 256)),
            nn.Tanh(),
            layer_init(nn.Linear(256, action_dim), std=0.01),
        )

    def get_value(self, x):
        return self.critic(x)

    def get_action_and_value(self, x, action_mask, action=None):
        logits = self.actor(x)
        huge_negative = torch.tensor(-1e8, dtype=logits.dtype, device=logits.device)
        masked_logits = torch.where(action_mask > 0.5, logits, huge_negative)
        probs = Categorical(logits=masked_logits)
        if action is None:
            action = probs.sample()
        return action, probs.log_prob(action), probs.entropy(), self.critic(x)
```

**`bot_service.py` 변경 포인트:**

```python
# MODEL_TYPE 환경변수에 "legacy_ppo" 추가

if model_type == "hppo":
    ...
elif model_type == "legacy_ppo":
    cls._model_type = "legacy_ppo"
    agent = LegacyPPOAgent(obs_dim=cls._obs_dim, action_dim=200).to(device)
    model_filename = os.getenv("PPO_MODEL_FILENAME", "ppo_agent_update_100.pth")
else:  # 기본값: ppo (신버전)
    ...

# BotService.get_action() 내부 — legacy_ppo는 표준 PPO와 동일하게 처리
if BotService._model_type in ("ppo", "legacy_ppo"):
    action_sample, _, _, _ = agent.get_action_and_value(obs_tensor, mask_tensor)
```

**환경변수 설정 (docker-compose 또는 .env):**
```env
MODEL_TYPE=legacy_ppo
PPO_MODEL_FILENAME=ppo_agent_update_100.pth
```

**방안 B (차선): 신버전 아키텍처로 재학습 후 체크포인트 교체**

학교 GPU 환경에서 현재 `Agent` 클래스(embed + shared_trunk + actor_head/critic_head)로 재학습하여 새 체크포인트를 생성. 단, 재학습 완료 전까지 방안 A를 임시 적용.

---

### TDD 구현 순서

```
RED:    test_legacy_ppo_loads_checkpoint() — strict=True로 로드 성공 테스트
RED:    test_legacy_ppo_outputs_valid_action() — 유효한 액션 범위(0~199) 출력 테스트
GREEN:  LegacyPPOAgent 클래스 구현
GREEN:  bot_service.py에 MODEL_TYPE=legacy_ppo 분기 추가
REFACTOR: LegacyPPOAgent 네이밍 및 docstring 정리
```

**테스트 파일 위치:** `castone/PuCo_RL/tests/test_legacy_ppo.py`

```python
def test_legacy_ppo_loads_ppo_update_100_checkpoint():
    """ppo_agent_update_100.pth가 strict=True로 로드되어야 한다."""
    agent = LegacyPPOAgent(obs_dim=210, action_dim=200)
    ckpt = torch.load("models/ppo_agent_update_100.pth", map_location="cpu", weights_only=True)
    state = ckpt.get("model_state_dict", ckpt)
    agent.load_state_dict(state, strict=True)  # 예외 없어야 함

def test_legacy_ppo_produces_valid_action():
    """유효한 액션을 선택해야 한다 (0~199 범위, 마스크 내)."""
    agent = LegacyPPOAgent(obs_dim=210)
    obs = torch.zeros(1, 210)
    mask = torch.zeros(1, 200)
    mask[0, 15] = 1.0  # pass 액션만 유효
    action, *_ = agent.get_action_and_value(obs, mask)
    assert action.item() == 15
```

---

## 에러 2 — 봇 액션 속도 (사람이 볼 수 있게 딜레이 조절)

### 현황 분석

`bot_service.py:186-188`에 딜레이가 **이미 구현되어 있다:**

```python
delay = 2.0 if is_role_selection else 1.0
await asyncio.sleep(delay)
```

그러나 봇이 액션을 하지 않는 이유(에러 1)로 인해 딜레이 효과를 체감하지 못하는 상황이다.

에러 1을 해결한 후, 딜레이를 사용자 요구에 맞게 조정한다.

---

### 설계

**딜레이 설정 (에러 1 해결 후 적용):**

```python
# bot_service.py run_bot_turn()

# 역할 선택 페이즈: 사용자가 봇의 전략적 선택을 볼 수 있도록 길게
delay = 3.0 if is_role_selection else 2.0
```

| 상황 | 현재 | 변경 후 |
|------|------|---------|
| 역할 선택 (Role Selection) | 2.0s | 3.0s |
| 일반 액션 | 1.0s | 2.0s |

**프론트엔드 "봇 생각 중" 인디케이터 추가 (선택사항):**

현재 프론트엔드에 봇이 액션 중임을 표시하는 UI가 없다. 게임 상태에서 현재 플레이어가 봇인 경우 "🤖 생각 중..." 표시를 추가하면 UX가 개선된다.

```tsx
// GameScreen 내부 (해당 컴포넌트 확인 후 정확한 위치 결정)
const currentPlayer = state.players[state.current_player_id];
const isBotTurn = currentPlayer?.is_bot === true;

{isBotTurn && (
  <div style={{ color: '#aaf', textAlign: 'center', padding: 8 }}>
    🤖 {currentPlayer.display_name} 생각 중...
  </div>
)}
```

---

### TDD 구현 순서 (에러 2)

```
RED:    test_bot_delay_role_selection() — 역할 선택 시 delay >= 3.0 검증
RED:    test_bot_delay_normal_action()  — 일반 액션 시 delay >= 2.0 검증
GREEN:  bot_service.py 딜레이 값 수정
```

---

## 전체 구현 우선순위

| 순서 | 작업 | 파일 | 중요도 |
|------|------|------|--------|
| 1 | `LegacyPPOAgent` 클래스 추가 | `PuCo_RL/agents/ppo_agent.py` | **필수** |
| 2 | `bot_service.py` `MODEL_TYPE=legacy_ppo` 분기 추가 | `backend/app/services/bot_service.py` | **필수** |
| 3 | 환경변수 설정 `MODEL_TYPE=legacy_ppo` | `docker-compose.yml` 또는 `.env` | **필수** |
| 4 | 봇 딜레이 조정 (1.0→2.0, 2.0→3.0) | `backend/app/services/bot_service.py` | 권장 |
| 5 | 프론트엔드 "봇 생각 중" 인디케이터 | `frontend/src/` (게임 화면 컴포넌트) | 선택 |

---

## 요약

**에러 1의 핵심:**
`ppo_agent_update_100.pth`는 **구버전 CleanRL 아키텍처** (actor/critic 각 3-Linear)로 학습된 모델이고, 현재 서빙 코드의 `Agent` 클래스는 **신버전 ResidualMLP 아키텍처**다. `strict=False` 폴백이 있지만 레이어 shape가 달라 실질적으로 가중치가 전혀 로드되지 않으므로 봇이 무작위(또는 고장 상태)로 동작한다.

**해결의 핵심:**
`LegacyPPOAgent` 추가 + `MODEL_TYPE=legacy_ppo` 환경변수 설정으로 **구버전 체크포인트를 올바르게 로드**하면 봇이 정상 작동하고, 에러 2(딜레이)는 그 이후에 확인 및 조정하면 된다.
