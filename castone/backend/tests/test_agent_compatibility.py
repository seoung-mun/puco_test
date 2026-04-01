import os
import sys
import torch
import pytest

# Project root for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from app.services.agents.legacy_models import LegacyPPOAgent

def test_legacy_ppo_strict_load():
    """
    ppo_agent_update_100.pth 체크포인트가 LegacyPPOAgent에 
    strict=True로 완벽하게 로드되는지 검증한다. (Phase 1 Red-Green)
    """
    # 1. 아키텍처 정의 (design.md 기준)
    obs_dim = 210
    action_dim = 200
    hidden_dim = 256
    agent = LegacyPPOAgent(obs_dim=obs_dim, action_dim=action_dim, hidden_dim=hidden_dim)
    
    # 2. 체크포인트 경로 (PuCo_RL/models/ 내에 있는 것을 확인)
    ckpt_path = os.path.join(os.path.dirname(__file__), "../../PuCo_RL/models/ppo_agent_update_100.pth")
    assert os.path.exists(ckpt_path), f"Checkpoint not found at {ckpt_path}"
    
    # 3. 로드 수행
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    # CleanRL 체크포인트는 보통 'model_state_dict' 키 아래에 있거나 전체가 state_dict일 수 있음
    state_dict = checkpoint.get("model_state_dict", checkpoint)
    
    # strict=True로 로드 시도 (이것이 성공해야 Green)
    try:
        agent.load_state_dict(state_dict, strict=True)
    except Exception as e:
        pytest.fail(f"Failed to load checkpoint with strict=True: {e}")

def test_legacy_ppo_output_shape():
    """기본적인 추론 출력이 올바른지 확인한다."""
    agent = LegacyPPOAgent(obs_dim=210, action_dim=200)
    obs = torch.zeros(1, 210)
    mask = torch.ones(1, 200)
    
    action, log_prob, entropy, value = agent.get_action_and_value(obs, mask)
    
    assert action.shape == (1,)
    assert value.shape == (1, 1)
