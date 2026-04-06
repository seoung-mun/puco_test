import pytest
import numpy as np
import sys
import os

# Ensure PuCo_RL is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from env.pr_env import PuertoRicoEnv
from agents.mcts_agent import MCTSAgent, MCTSConfig
from agents.mcts_agent_spite import MCTSAgentSpite
from agents.factory_heuristic_agent import FactoryAgent
from configs.constants import Good, Role, BuildingType

@pytest.fixture
def env_and_agents():
    env = PuertoRicoEnv(num_players=3)
    env.reset()
    
    config = MCTSConfig(num_simulations=2) # Keep simulation low for tests
    
    agents = {
        'factory': FactoryAgent(env.action_space('player_0'), env.unwrapped),
        'mcts': MCTSAgent(env.action_space('player_1'), env.unwrapped, config=config),
        'spite': MCTSAgentSpite(env.action_space('player_2'), env.unwrapped, config=config, spite_alpha=0.5)
    }
    return env, agents

def test_agent_initialization(env_and_agents):
    """Test if agents initialize correctly with the environment object."""
    env, agents = env_and_agents
    assert agents['factory'] is not None
    assert agents['mcts'] is not None
    assert agents['spite'] is not None
    assert agents['factory'].env == env.unwrapped
    assert getattr(agents['spite'], 'spite_alpha', None) == 0.5

def test_mcts_action_mapping_valid(env_and_agents):
    """Test the translation of internal dict actions to PuCo_RL discrete actions."""
    env, agents = env_and_agents
    agent = agents['mcts']
    
    # Create an all-valid mask for testing mapping pure logic
    valid_mask = np.ones(200, dtype=np.int8)
    
    # Role Selection: SETTLER (0)
    assert agent._map_dict_to_discrete({"type": "role", "role": Role.SETTLER}, valid_mask) == 0
    # Role Selection: CAPTAIN (5)
    assert agent._map_dict_to_discrete({"type": "role", "role": Role.CAPTAIN}, valid_mask) == 5
    
    # Settler: Face up plantation index 2
    assert agent._map_dict_to_discrete({"type": "settler", "choice": 2}, valid_mask) == 10
    # Settler: Quarry (-1)
    assert agent._map_dict_to_discrete({"type": "settler", "choice": -1}, valid_mask) == 14
    # Settler: Pass (-2) -> Discrete Pass is 15
    assert agent._map_dict_to_discrete({"type": "settler", "choice": -2}, valid_mask) == 15
    
    # Builder: BuildingType.FACTORY (index 14) -> 16 + 14 = 30
    assert agent._map_dict_to_discrete({"type": "builder", "choice": BuildingType.FACTORY}, valid_mask) == 30
    # Builder: Pass
    assert agent._map_dict_to_discrete({"type": "builder", "choice": None}, valid_mask) == 15
    
    # Captain Load: Ship 1, Good.CORN (2) -> 44 + (1*5) + 2 = 51
    assert agent._map_dict_to_discrete({"type": "captain_load", "ship": 1, "good": Good.CORN}, valid_mask) == 51
    # Captain Load Wharf: Ship -1, Good.TOBACCO (1) -> 59 + 1 = 60
    assert agent._map_dict_to_discrete({"type": "captain_load", "ship": -1, "good": Good.TOBACCO}, valid_mask) == 60

def test_invalid_masked_action_fallback(env_and_agents):
    """
    Test that if an agent's intended action is masked out,
    it falls back to a valid action instead of throwing or returning an invalid one.
    """
    env, agents = env_and_agents
    agent = agents['mcts']
    
    # Create a mask where ONLY action 15 (Pass) is valid
    valid_mask = np.zeros(200, dtype=np.int8)
    valid_mask[15] = 1
    
    # Intend to pick Role Settler (0), but it's masked out. Should fallback to random valid (which is 15 here)
    fallback_action = agent._map_dict_to_discrete({"type": "role", "role": Role.SETTLER}, valid_mask)
    assert fallback_action == 15
    
    # Create a mask where ONLY action 10 is valid
    valid_mask_2 = np.zeros(200, dtype=np.int8)
    valid_mask_2[10] = 1
    fallback_action_2 = agent._map_dict_to_discrete({"type": "builder", "choice": BuildingType.FACTORY}, valid_mask_2)
    assert fallback_action_2 == 10

def test_factory_internal_evaluation_runs(env_and_agents):
    """Test that the factory heuristic agent can evaluate actions without crashing."""
    env, agents = env_and_agents
    agent = agents['factory']
    
    obs, _, _, _, _ = env.last()
    valid_mask = obs["action_mask"]
    
    # This just ensures select_action runs through the evaluate loops without Exceptions
    action = agent.select_action(obs, valid_mask)
    assert 0 <= action < 200
    assert valid_mask[action] == 1 # Must pick a valid action

def test_mcts_progressive_widening(env_and_agents):
    """Test that MCTS runs successfully with progressive widening enabled."""
    env, agents = env_and_agents
    
    # Configure an agent with progressive widening specifically
    config = MCTSConfig(num_simulations=10, use_progressive_widening=True, pw_c=1.0, pw_alpha=0.5)
    agent = MCTSAgent(env.action_space('player_1'), env.unwrapped, config=config)
    
    obs, _, _, _, _ = env.last()
    valid_mask = obs["action_mask"]
    
    # Run a selection to ensure the widening logic doesn't crash
    action = agent.select_action(obs, valid_mask)
    assert 0 <= action < 200
    assert valid_mask[action] == 1
