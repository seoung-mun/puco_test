from __future__ import annotations

from app.services.agents import (
    AgentWrapper,
    ActionValueWrapper,
    AdvancedRuleBasedWrapper,
    FactoryRuleBasedWrapper,
    HPPOWrapper,
    PPOWrapper,
    RandomWrapper,
    RuleBasedWrapper,
    ShippingRushWrapper,
)
from app.services.engine_gateway.bootstrap import ensure_puco_rl_path

ensure_puco_rl_path()

from agents.ppo_agent import Agent as ResidualAgent  # noqa: E402

__all__ = [
    "ActionValueWrapper",
    "AdvancedRuleBasedWrapper",
    "AgentWrapper",
    "FactoryRuleBasedWrapper",
    "HPPOWrapper",
    "PPOWrapper",
    "RandomWrapper",
    "ResidualAgent",
    "RuleBasedWrapper",
    "ShippingRushWrapper",
]
