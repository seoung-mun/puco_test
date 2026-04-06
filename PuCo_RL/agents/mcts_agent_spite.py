import random
from typing import List

from agents.mcts_agent import MCTSAgent, MCTSNode, get_relative_indices, apply_action, MCTSConfig
from env.engine import PuertoRicoGame

class MCTSAgentSpite(MCTSAgent):
    def __init__(self, action_space, env, config: MCTSConfig = None, spite_alpha: float = 0.4):
        """
        선두 견제(Leader-bashing) 로직이 추가된 MCTS 에이전트입니다.
        
        기존 MCTS를 상속받으며, spite_alpha 파라미터를 추가로 받습니다.
        spite_alpha: 내가 얻는 점수 대비 "상대방 중 1등의 점수를 깎아내리는 것"에 가중치를 얼마나 둘 가를 결정합니다.
        (0.0 이면 기존 MCTS와 완벽히 동일하며, 1.0에 가까워질수록 내 점수를 포기하더라도 상대방을 망치는 것을 선호합니다.)
        """
        super().__init__(action_space=action_space, env=env, config=config)
        self.spite_alpha = spite_alpha

    def _default_policy(self, state: PuertoRicoGame) -> List[float]:
        """
        [Simulation / Rollout 단계 오버라이딩]
        이 Spite 에이전트는 게임 종료 후 얻어진 점수를 바탕으로
        "내 점수 - (spite_alpha * 상대방들 중 최고 점수)"라는 상대적 가치를 계산합니다.
        플레이어들의 Shaped Score를 0.0 ~ 1.0 사이로 Min-Max 정규화(Normalization)하여 반환합니다.
        """
        sim_state = state.fast_clone()
        safety_net = 2000
        
        while not sim_state.check_game_end() and safety_net > 0:
            untried = MCTSNode(sim_state).get_untried_actions()
            if not untried:
                break
            action = random.choice(untried)
            apply_action(sim_state, action)
            safety_net -= 1
            
        scores = sim_state.get_scores()
        
        # 1. 원시 점수 계산 (동점 처리를 위한 미세 보정치 포함)
        raw_scores = [sc[0] + sc[1] * 0.001 for sc in scores]
        
        # 2. 견제(Spite) 수식이 반영된 상대적 점수(Shaped Score) 계산
        shaped_scores = []
        for i in range(sim_state.num_players):
            opponents_scores = [raw_scores[j] for j in range(sim_state.num_players) if j != i]
            max_opponent_score = max(opponents_scores) if opponents_scores else 0
            
            shaped_val = raw_scores[i] - self.spite_alpha * max_opponent_score
            shaped_scores.append(shaped_val)
            
        # 3. Min-Max 정규화
        min_s = min(shaped_scores)
        max_s = max(shaped_scores)
        
        abs_rewards = [0.0] * sim_state.num_players
        
        if max_s - min_s < 1e-6:
            abs_rewards = [0.5] * sim_state.num_players
        else:
            for i in range(sim_state.num_players):
                abs_rewards[i] = (shaped_scores[i] - min_s) / (max_s - min_s)
                
        # 4. 상대 인덱스로 변환
        root_p_idx = self.env.game.current_player_idx
        relative_map = get_relative_indices(root_p_idx, sim_state.num_players)
        
        rel_rewards = [0.0] * sim_state.num_players
        for abs_idx, reward in enumerate(abs_rewards):
            rel_idx = relative_map[abs_idx]
            rel_rewards[rel_idx] = reward
            
        return rel_rewards
