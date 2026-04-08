import os
import sys

import torch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from agents.ppo_agent import Agent
from agents.wrappers import PPOWrapper


def test_serving_ppo_wrapper_adapts_210_checkpoint_to_211_runtime_obs(tmp_path):
    checkpoint_path = tmp_path / "PPO_PR_Server_20260408_120000_step_100.pth"
    agent = Agent(obs_dim=210, action_dim=200)
    torch.save(agent.state_dict(), checkpoint_path)

    wrapper = PPOWrapper(str(checkpoint_path), obs_dim=211)

    obs = torch.zeros(1, 211)
    obs[0, 42] = 999.0
    mask = torch.zeros(1, 200)
    mask[0, 15] = 1.0

    action = wrapper.act(obs, mask)

    assert wrapper._expected_obs_dim == 210
    assert action == 15
