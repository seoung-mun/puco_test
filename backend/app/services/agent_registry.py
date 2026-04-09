"""
AgentRegistry — bot_type 문자열을 실제 serving artifact와 wrapper로 해석한다.

현재 목표:
- 사용자/API는 계속 `ppo` 같은 안정적인 bot_type을 사용
- 내부는 `family + policy_tag(champion)` 기준으로 실제 checkpoint를 resolve
- `PPO_PR_Server_~.pth` 는 bootstrap metadata로 허용
- 다음 모델부터는 sidecar JSON을 우선 해석
"""
import functools
import logging
import os
from app.services.engine_gateway.agents import (
    ActionValueWrapper,
    AgentWrapper,
    FactoryRuleBasedWrapper,
    HPPOWrapper,
    PPOWrapper,
    RandomWrapper,
    RuleBasedWrapper,
    AdvancedRuleBasedWrapper,
    ShippingRushWrapper,
)
from app.services.model_registry import (
    ModelArtifact,
    make_static_artifact,
    resolve_model_artifact_from_path,
)

logger = logging.getLogger(__name__)

_MODELS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../PuCo_RL/models")
)
DEFAULT_BOT_TYPE = "random"
BOT_PLAYER_PREFIX = "BOT_"

# ──────────────────────────────────────────────────────────────────────────
# 에이전트 등록 테이블 — 새 알고리즘은 이 dict 한 곳만 수정
# ──────────────────────────────────────────────────────────────────────────
AGENT_REGISTRY: dict[str, dict] = {
    "ppo": {
        "name": "PPO Bot",
        "family": "ppo",
        "policy_tag": "champion",
        "wrapper_cls": PPOWrapper,
        "model_env_key": "PPO_MODEL_FILENAME",
        "model_default": "PPO_PR_Server_순수자기대결_20260406_135525_step_99942400.pth",
    },
    "hppo": {
        "name": "HPPO Bot",
        "family": "hppo",
        "policy_tag": "champion",
        "wrapper_cls": HPPOWrapper,
        "model_env_key": "HPPO_MODEL_FILENAME",
        "model_default": "HPPO_PR_Server_1774241514_step_14745600.pth",
    },
    "random": {
        "name": "Random Bot",
        "family": "random",
        "policy_tag": "champion",
        "wrapper_cls": RandomWrapper,
        "model_env_key": None,   # 가중치 불필요
        "model_default": None,
    },
    "rule_based": {
        "name": "Rule-Based Bot",
        "family": "rule_based",
        "policy_tag": "champion",
        "wrapper_cls": RuleBasedWrapper,
        "model_env_key": None,
        "model_default": None,
    },
    "advanced_rule": {
        "name": "Advanced Rule-Based Bot",
        "family": "advanced_rule",
        "policy_tag": "champion",
        "wrapper_cls": AdvancedRuleBasedWrapper,
        "model_env_key": None,
        "model_default": None,
    },
    "shipping_rush": {
        "name": "Shipping Rush Bot",
        "family": "shipping_rush",
        "policy_tag": "champion",
        "wrapper_cls": ShippingRushWrapper,
        "model_env_key": None,
        "model_default": None,
    },
    "factory_rule": {
        "name": "Factory Rule-Based Bot",
        "family": "factory_rule",
        "policy_tag": "champion",
        "wrapper_cls": FactoryRuleBasedWrapper,
        "model_env_key": None,
        "model_default": None,
    },
    "action_value": {
        "name": "Action Value Bot",
        "family": "action_value",
        "policy_tag": "champion",
        "wrapper_cls": ActionValueWrapper,
        "model_env_key": None,
        "model_default": None,
    },
}


def normalize_bot_type(bot_type: str | None) -> str:
    normalized = (bot_type or DEFAULT_BOT_TYPE).strip().lower()
    return normalized or DEFAULT_BOT_TYPE


def require_valid_bot_type(bot_type: str | None) -> str:
    normalized = normalize_bot_type(bot_type)
    if normalized not in AGENT_REGISTRY:
        raise ValueError(
            f"Unknown bot type '{normalized}'. Valid: {sorted(AGENT_REGISTRY)}"
        )
    return normalized


def resolve_bot_type_from_actor_id(actor_id: str | None) -> str:
    actor = str(actor_id or "")
    if not actor.startswith(BOT_PLAYER_PREFIX):
        return DEFAULT_BOT_TYPE

    suffix = actor[len(BOT_PLAYER_PREFIX):]
    normalized = normalize_bot_type(suffix)
    if normalized in AGENT_REGISTRY:
        return normalized

    base_type = normalize_bot_type(suffix.split("_", 1)[0])
    if base_type in AGENT_REGISTRY:
        return base_type

    return normalized


def make_bot_player_id(bot_type: str | None) -> str:
    return f"{BOT_PLAYER_PREFIX}{require_valid_bot_type(bot_type)}"


def normalize_bot_types(bot_types: list[str] | None, max_players: int = 3) -> list[str]:
    normalized = [require_valid_bot_type(bot_type) for bot_type in (bot_types or [])[:max_players]]
    while len(normalized) < max_players:
        normalized.append(DEFAULT_BOT_TYPE)
    return normalized


def _resolve_model_path(cfg: dict) -> str | None:
    """env var → 기본값 순서로 모델 경로를 결정한다."""
    if cfg["model_env_key"] is None:
        return None
    filename = os.getenv(cfg["model_env_key"], cfg["model_default"])
    return os.path.join(_MODELS_DIR, filename) if filename else None


def resolve_model_artifact(bot_type: str) -> ModelArtifact | None:
    normalized = require_valid_bot_type(bot_type)
    cfg = AGENT_REGISTRY[normalized]
    if cfg["model_env_key"] is None:
        return None

    model_path = _resolve_model_path(cfg)
    if model_path is None:
        return None

    if normalized == "hppo":
        try:
            return resolve_model_artifact_from_path(
                model_path,
                family=cfg["family"],
                policy_tag=cfg["policy_tag"],
            )
        except FileNotFoundError as exc:
            raise ValueError(str(exc)) from exc
        except ValueError:
            logger.warning(
                "HPPO metadata not found for %s. Falling back to static artifact snapshot.",
                model_path,
            )
            return make_static_artifact(
                model_path,
                family=cfg["family"],
                policy_tag=cfg["policy_tag"],
                architecture="phase_ppo",
                metadata_source="static_config",
            )

    try:
        return resolve_model_artifact_from_path(
            model_path,
            family=cfg["family"],
            policy_tag=cfg["policy_tag"],
        )
    except FileNotFoundError as exc:
        raise ValueError(str(exc)) from exc


def _validate_artifact_for_wrapper(
    *,
    bot_type: str,
    artifact: ModelArtifact,
    obs_dim: int,
) -> None:
    if bot_type == "ppo" and artifact.architecture not in {"ppo", "ppo_residual"}:
        raise ValueError(
            f"PPO bot requires residual PPO checkpoint, got architecture={artifact.architecture!r}"
        )
    if bot_type == "hppo" and artifact.architecture not in {None, "phase_ppo", "hppo"}:
        raise ValueError(
            f"HPPO bot requires phase PPO checkpoint, got architecture={artifact.architecture!r}"
        )
    if artifact.obs_dim is not None and artifact.obs_dim != obs_dim:
        if {artifact.obs_dim, obs_dim} == {210, 211} and bot_type in {"ppo", "hppo"}:
            pass
        else:
            raise ValueError(
                f"Checkpoint obs_dim mismatch for {artifact.checkpoint_filename}: "
                f"expected {obs_dim}, metadata has {artifact.obs_dim}"
            )
    if artifact.action_dim is not None and artifact.action_dim != 200:
        raise ValueError(
            f"Checkpoint action_dim mismatch for {artifact.checkpoint_filename}: "
            f"expected 200, metadata has {artifact.action_dim}"
        )


@functools.lru_cache(maxsize=None)
def _get_wrapper_cached(bot_type: str, obs_dim: int, artifact_cache_key: str) -> AgentWrapper:
    normalized = require_valid_bot_type(bot_type)
    cfg = AGENT_REGISTRY[normalized]
    artifact = resolve_model_artifact(normalized)
    model_path = artifact.checkpoint_path if artifact else None
    logger.info(
        "AgentWrapper 생성: type=%s, model=%s, cache_key=%s",
        normalized,
        model_path,
        artifact_cache_key,
    )
    return cfg["wrapper_cls"](model_path=model_path, obs_dim=obs_dim)


def get_wrapper(bot_type: str, obs_dim: int) -> AgentWrapper:
    """bot_type 별 AgentWrapper 싱글턴을 반환한다."""
    normalized = require_valid_bot_type(bot_type)
    artifact = resolve_model_artifact(normalized)
    if artifact is not None:
        _validate_artifact_for_wrapper(
            bot_type=normalized,
            artifact=artifact,
            obs_dim=obs_dim,
        )
        return _get_wrapper_cached(normalized, obs_dim, artifact.cache_key)
    return _get_wrapper_cached(normalized, obs_dim, f"{normalized}:builtin")


def clear_wrapper_cache() -> None:
    _get_wrapper_cached.cache_clear()


def bot_agents_list() -> list[dict]:
    """프론트엔드 /api/bot-types 응답용 [{type, name}, ...] 리스트."""
    return [{"type": k, "name": v["name"]} for k, v in AGENT_REGISTRY.items()]


def valid_bot_types() -> set[str]:
    """유효한 bot_type 집합."""
    return set(AGENT_REGISTRY.keys())
