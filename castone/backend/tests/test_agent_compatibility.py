import os
import sys
import torch
import pytest

# Project root for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from app.services.agents.legacy_models import LegacyPPOAgent
from app.services.agents.factory import AgentFactory
from app.services.agents.wrappers import LegacyPPOAgentWrapper, RandomAgentWrapper

def test_legacy_ppo_strict_load():
    """
    ppo_agent_update_100.pth 체크포인트가 LegacyPPOAgent에 
    strict=True로 완벽하게 로드되는지 검증한다. (Phase 1 Red-Green)
    """
    obs_dim = 210
    action_dim = 200
    hidden_dim = 256
    agent = LegacyPPOAgent(obs_dim=obs_dim, action_dim=action_dim, hidden_dim=hidden_dim)
    
    ckpt_path = os.path.join(os.path.dirname(__file__), "../../PuCo_RL/models/ppo_agent_update_100.pth")
    assert os.path.exists(ckpt_path), f"Checkpoint not found at {ckpt_path}"
    
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    state_dict = checkpoint.get("model_state_dict", checkpoint)
    
    try:
        agent.load_state_dict(state_dict, strict=True)
    except Exception as e:
        pytest.fail(f"Failed to load checkpoint with strict=True: {e}")

def test_factory_returns_legacy_wrapper_for_correct_model():
    """정상적인 레거시 모델 경로를 주었을 때 LegacyPPOAgentWrapper를 반환해야 한다."""
    AgentFactory.clear_cache()
    ckpt_path = os.path.join(os.path.dirname(__file__), "../../PuCo_RL/models/ppo_agent_update_100.pth")
    
    wrapper = AgentFactory.get_agent(ckpt_path)
    assert isinstance(wrapper, LegacyPPOAgentWrapper)
    assert wrapper.model is not None

def test_factory_returns_random_on_invalid_path():
    """존재하지 않는 모델 경로 입력 시 RandomAgentWrapper를 반환해야 한다. (Edge Case)"""
    AgentFactory.clear_cache()
    wrapper = AgentFactory.get_agent("invalid/path/to/model.pth")
    
    assert isinstance(wrapper, RandomAgentWrapper)
    # RandomAgent는 어떤 입력에도 유효한 액션을 반환해야 함
    obs = torch.zeros(1, 210)
    mask = torch.zeros(1, 200)
    mask[0, 15] = 1.0 # 인덱스 15만 유효
    
    action = wrapper.act(obs, mask)
    assert action == 15

def test_factory_caching():
    """동일한 모델 경로에 대해 캐싱된 인스턴스를 반환해야 한다."""
    AgentFactory.clear_cache()
    ckpt_path = os.path.join(os.path.dirname(__file__), "../../PuCo_RL/models/ppo_agent_update_100.pth")
    
    wrapper1 = AgentFactory.get_agent(ckpt_path)
    wrapper2 = AgentFactory.get_agent(ckpt_path)
    
    assert wrapper1 is wrapper2

def test_legacy_ppo_output_shape():
    """기본적인 추론 출력이 올바른지 확인한다."""
    agent = LegacyPPOAgent(obs_dim=210, action_dim=200)
    obs = torch.zeros(1, 210)
    mask = torch.ones(1, 200)
    
    action, log_prob, entropy, value = agent.get_action_and_value(obs, mask)
    
    assert action.shape == (1,)
    assert value.shape == (1, 1)
