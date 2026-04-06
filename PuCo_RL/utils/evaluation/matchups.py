import itertools

def get_mixed_matchups(agent1, agent2, agent3):
    """
    Returns 6 permutations of the three distinct agents.
    Ex: agent1 = "PhasePPO", agent2 = "PPO", agent3 = "Random"
    """
    return list(itertools.permutations([agent1, agent2, agent3]))

def get_asymmetric_matchups(solo_agent, duo_agent_type, suffix1="_1", suffix2="_2"):
    """
    Returns 3 permutations for 1v2 environments.
    Returns format: [(solo, duo1, duo2), (duo1, solo, duo2), (duo1, duo2, solo)]
    """
    duo1 = f"{duo_agent_type}{suffix1}"
    duo2 = f"{duo_agent_type}{suffix2}"
    
    return [
        (solo_agent, duo1, duo2),
        (duo1, solo_agent, duo2),
        (duo1, duo2, solo_agent)
    ]
