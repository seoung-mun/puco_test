"""
AgentRegistry — bot_type 문자열 → AgentWrapper 싱글턴 매핑.

새 알고리즘 추가 방법:
1. PuCo_RL/agents/wrappers.py 에 XxxWrapper(AgentWrapper) 구현
2. 아래 AGENT_REGISTRY 에 한 줄 추가
3. .env 에 XXX_MODEL_FILENAME=<파일명> 추가 (가중치 있을 경우)
→ BotService / legacy.py 수정 불필요
"""
import functools
import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../PuCo_RL")))

from agents.base import AgentWrapper
from agents.wrappers import HPPOWrapper, PPOWrapper, RandomWrapper

logger = logging.getLogger(__name__)

_MODELS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../PuCo_RL/models")
)

# ──────────────────────────────────────────────────────────────────────────
# 에이전트 등록 테이블 — 새 알고리즘은 이 dict 한 곳만 수정
# ──────────────────────────────────────────────────────────────────────────
AGENT_REGISTRY: dict[str, dict] = {
    "ppo": {
        "name": "PPO Bot",
        "wrapper_cls": PPOWrapper,
        "model_env_key": "PPO_MODEL_FILENAME",
        "model_default": "ppo_agent_update_100.pth",
    },
    "hppo": {
        "name": "HPPO Bot",
        "wrapper_cls": HPPOWrapper,
        "model_env_key": "HPPO_MODEL_FILENAME",
        "model_default": "HPPO_PR_Server_1774241514_step_14745600.pth",
    },
    "random": {
        "name": "Random Bot",
        "wrapper_cls": RandomWrapper,
        "model_env_key": None,   # 가중치 불필요
        "model_default": None,
    },
}


def _resolve_model_path(cfg: dict) -> str | None:
    """env var → 기본값 순서로 모델 경로를 결정한다."""
    if cfg["model_env_key"] is None:
        return None
    filename = os.getenv(cfg["model_env_key"], cfg["model_default"])
    return os.path.join(_MODELS_DIR, filename) if filename else None


@functools.lru_cache(maxsize=None)
def get_wrapper(bot_type: str, obs_dim: int) -> AgentWrapper:
    """bot_type 별 AgentWrapper 싱글턴을 반환한다 (LRU 캐시로 1회만 생성)."""
    cfg = AGENT_REGISTRY.get(bot_type)
    if cfg is None:
        logger.warning("알 수 없는 bot_type '%s' — random으로 폴백", bot_type)
        cfg = AGENT_REGISTRY["random"]

    model_path = _resolve_model_path(cfg)
    logger.info("AgentWrapper 생성: type=%s, model=%s", bot_type, model_path)
    return cfg["wrapper_cls"](model_path=model_path, obs_dim=obs_dim)


def bot_agents_list() -> list[dict]:
    """프론트엔드 /api/bot-types 응답용 [{type, name}, ...] 리스트."""
    return [{"type": k, "name": v["name"]} for k, v in AGENT_REGISTRY.items()]


def valid_bot_types() -> set[str]:
    """유효한 bot_type 집합."""
    return set(AGENT_REGISTRY.keys())
