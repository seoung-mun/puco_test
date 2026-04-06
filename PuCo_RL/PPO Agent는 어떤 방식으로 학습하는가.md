# 1. Policy Network, Critic Network 초기화 
    - Actor : Policy를 학습한다. 즉, 어떤 state에서 어떤 action을 할 지 학습하는 것이다.
    - Critic : Value를 학습한다. 즉, 어떤 state에서 cumulative reward가 얼마일지 예측하는 것이다.

action을 결정하는 Policy(Actor) Network뿐만 아니라, 현재 상태가 얼마나 좋은지를 예측하는 Value Function(Critic) 네트워크도 무작위로 초기화한다.

# 2. 데이터 수집(Rollout) 및 PBRS 보상 체계
에이전트가 현재 policy 기반으로 푸에르토 리코를 플레이한다. 잠재 함수($Phi$)값 그 자체는 에이전트에게 reward로 주어지지 않는다.
에이전트가 행동 $a_t$를 취해 다음 state $S_{t+1}$로 전이하면, envrionment는 **이전 state와 다음 state의 잠재값 차이**를 계산하여 agent에게 전달한다.

* **수식** : $R_{step} = \gamma \cdot \Phi(S_{t+1}) - \Phi(S_t)$
즉, **과거 state보다 지금 state가 얼마나 더 좋아졌는지**에 대한 매 스텝의 즉각적인 reward를 제공한다.
에이전트는 이 reward를 state, action, log-prob과 함께 rollout buffer에 차곡차곡 저장한다.

# 3. Advantage 계산
rollout buffer에 데이터가 꽉 차면, 에이전트는 buffer에 보인 step 단위 reward + terminal reward를 모아 $A_t$를 계산한다.
* $A_t$ : "내가 $t$ 시점에 선택한 행동이, Critic이 예측했던 평균적인 기대치보다 얼마나 더 좋았는가?"
    * $A_t > 0$ : 실제 결과가 예측보다 좋았다 -> 그 action을 할 확률을 높인다.
    * $A_t < 0$ : 실제 결과가 예측보다 나빴다 -> 그 action을 할 확률을 낮춘다.

# 4. 최적화 루프(확률적 경사 상승법)
1. **Clipping** : 과거의 policy를 한 번의 업데이트로 망가뜨리지 않기 위해, 구 policy와 신 policy의 행동 확률 비율($r_{\theta}(a|s)$)을 특정 범위로 제한한다.
    * $r_{\theta}(a|s) = \frac{\pi_{\theta}(a|s)}{\pi_{\theta_{old}}(a|s)}$
    * $L^{CLIP}(\theta) = \mathbb{\hat E}_t[\min(r_{\theta}(a_t|s_t)A_t, \text{clip}(r_{\theta}(a_t|s_t), 1-\epsilon, 1+\epsilon)A_t)]$
    * 이 값이 커지도록 학습한다.
2. **Value Loss** : Critic이 예측한 기대값과 실제 누적 보상의 차이를 줄인다.
    * $L^{VF}(\theta) = \mathbb{\hat E}_t[(V_{\theta}(s_t) - V_t^{target})^2]$
    * 이 값이 작아지도록 학습한다.
3. **Entropy Bonus** : policy가 너무 한쪽으로 치우치는 것을 막고 탐험을 장려하기 위해, policy의 엔트로피를 보너스로 더해준다.
    * $L^{ENT}(\theta) = \mathbb{\hat E}_t[H(\pi_{\theta}(s_t))]$
    * 이 값이 커지도록 학습한다.
4. **최종 objective function (Maximization Goal)** : $J(\theta) = L^{CLIP}(\theta) - c_1 L^{VF}(\theta) + c_2 L^{ENT}(\theta)$