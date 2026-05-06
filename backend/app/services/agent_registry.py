"""
AgentRegistry — bot_type 문자열을 실제 serving artifact와 wrapper로 해석한다.

현재 목표:
- 사용자/API는 계속 `ppo` 같은 안정적인 bot_type을 사용
- 내부는 bundle manifest 또는 sidecar metadata 기준으로 실제 artifact를 resolve
- model-file bot은 adapter bundle을 우선 사용하고, rule-based bot은 기존 wrapper 경로를 유지
"""
import functools
import logging
import os
from dataclasses import dataclass
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
    load_bundle_artifact,
    load_bundle_manifest,
    make_static_artifact,
    resolve_bundle_checkpoint,
    resolve_model_artifact_from_path,
)

logger = logging.getLogger(__name__)
_LOGGED_RESOLUTION_WARNINGS: set[str] = set()

_MODELS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../PuCo_RL/models")
)
DEFAULT_BOT_TYPE = "random"
BOT_PLAYER_PREFIX = "BOT_"
PUBLIC_BOT_TYPES: tuple[str, ...] = ("random", "action_value", "shipping_rush", "ppo")


@dataclass(frozen=True)
class ModelArtifactResolution:
    artifact: ModelArtifact | None
    warning: str | None = None
    failure_detail: str | None = None
    used_legacy_override: bool = False

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
        "model_default": "PPO_test.pth",
        "bundle_dir_env_key": "PPO_BUNDLE_DIR",
        "bundle_dir": "ppo-pr-server-semantic293-20260419",
        "use_adapter": True,
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


def _get_env_override(key: str | None) -> str | None:
    if not key:
        return None
    value = os.getenv(key)
    if value is None:
        return None
    value = value.strip()
    return value or None


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

    filename = _get_env_override(cfg["model_env_key"]) or cfg["model_default"]
    if not filename:
        return None

    if os.path.isabs(filename):
        return filename

    candidate = os.path.normpath(os.path.join(_MODELS_DIR, filename))
    if os.path.exists(candidate):
        return candidate

    # When the env override supplies only a basename, resolve a unique match
    # under PuCo_RL/models so local smoke checkpoints can be selected directly.
    if _get_env_override(cfg["model_env_key"]) and os.path.basename(filename) == filename:
        matches = [
            os.path.join(root, filename)
            for root, _dirs, files in os.walk(_MODELS_DIR)
            if filename in files
        ]
        if len(matches) == 1:
            resolved = os.path.normpath(matches[0])
            logger.info(
                "Resolved %s=%s to nested model path %s",
                cfg["model_env_key"],
                filename,
                resolved,
            )
            return resolved
        if len(matches) > 1:
            logger.warning(
                "Multiple model files matched %s=%s under %s: %s",
                cfg["model_env_key"],
                filename,
                _MODELS_DIR,
                matches,
            )

    return candidate


def _resolve_bundle_dir_name(cfg: dict) -> str | None:
    env_override = _get_env_override(cfg.get("bundle_dir_env_key"))
    if env_override:
        return env_override
    return cfg.get("bundle_dir")


def _log_resolution_warning_once(message: str) -> None:
    if message in _LOGGED_RESOLUTION_WARNINGS:
        return
    _LOGGED_RESOLUTION_WARNINGS.add(message)
    logger.warning("%s", message)


def _bundle_failure_detail(bundle_dir: str) -> str | None:
    manifest = load_bundle_manifest(bundle_dir)
    if manifest is None:
        return f"Bundle manifest missing: {os.path.join(bundle_dir, 'manifest.json')}"

    try:
        resolve_bundle_checkpoint(bundle_dir, manifest)
    except FileNotFoundError as exc:
        return str(exc)
    return None


def _resolve_static_or_sidecar_artifact(bot_type: str, cfg: dict) -> ModelArtifact | None:
    if cfg["model_env_key"] is None:
        return None

    model_path = _resolve_model_path(cfg)
    if model_path is None:
        return None

    if bot_type == "hppo":
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
    except ValueError:
        logger.warning(
            "PPO metadata not found for %s. Falling back to static artifact snapshot.",
            model_path,
        )
        return make_static_artifact(
            model_path,
            family=cfg["family"],
            policy_tag=cfg["policy_tag"],
            architecture="ppo_residual",
            metadata_source="static_config",
        )


def describe_model_artifact_resolution(bot_type: str) -> ModelArtifactResolution:
    normalized = require_valid_bot_type(bot_type)
    cfg = AGENT_REGISTRY[normalized]
    bundle_name = _resolve_bundle_dir_name(cfg)
    bundle_dir = os.path.join(_MODELS_DIR, bundle_name) if bundle_name else None
    model_override = _get_env_override(cfg.get("model_env_key"))
    warning: str | None = None
    failure_detail: str | None = None

    bundle_artifact = _load_bundle_artifact_for_bot(normalized)
    if bundle_artifact is not None:
        if model_override:
            warning = (
                f"Both {cfg['bundle_dir_env_key']} and {cfg['model_env_key']} are set; "
                f"using bundle precedence and ignoring legacy override {model_override!r}."
            )
            _log_resolution_warning_once(warning)
        return ModelArtifactResolution(
            artifact=bundle_artifact,
            warning=warning,
        )

    if bundle_dir:
        failure_detail = _bundle_failure_detail(bundle_dir)

    try:
        artifact = _resolve_static_or_sidecar_artifact(normalized, cfg)
    except ValueError as exc:
        return ModelArtifactResolution(
            artifact=None,
            failure_detail=str(exc),
        )

    used_legacy_override = model_override is not None and artifact is not None
    if used_legacy_override:
        warning = f"Running on legacy override via {cfg['model_env_key']}={model_override!r}."
        _log_resolution_warning_once(warning)

    return ModelArtifactResolution(
        artifact=artifact,
        warning=warning,
        failure_detail=failure_detail,
        used_legacy_override=used_legacy_override,
    )


def _load_bundle_artifact_for_bot(bot_type: str) -> ModelArtifact | None:
    cfg = AGENT_REGISTRY.get(bot_type, {})
    bundle_name = _resolve_bundle_dir_name(cfg)
    if not bundle_name:
        return None

    bundle_dir = os.path.join(_MODELS_DIR, bundle_name)
    try:
        artifact = load_bundle_artifact(bundle_dir)
    except FileNotFoundError:
        logger.warning(
            "Bundle checkpoint missing for %s at %s — ignoring bundle artifact.",
            bot_type,
            bundle_dir,
        )
        return None
    if artifact is None:
        return None

    logger.info(
        "Bundle artifact resolved for bot_type=%s bundle=%s checkpoint=%s",
        bot_type,
        artifact.artifact_name,
        artifact.checkpoint_filename,
    )
    return artifact


@functools.lru_cache(maxsize=None)
def _resolve_bundle_artifact(bot_type: str) -> ModelArtifact | None:
    return _load_bundle_artifact_for_bot(bot_type)


def resolve_model_artifact(bot_type: str) -> ModelArtifact | None:
    normalized = require_valid_bot_type(bot_type)
    cfg = AGENT_REGISTRY[normalized]
    bundle_artifact = _resolve_bundle_artifact(normalized)
    if bundle_artifact is not None:
        return bundle_artifact
    return _resolve_static_or_sidecar_artifact(normalized, cfg)


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
    _resolve_bundle_artifact.cache_clear()
    _resolve_adapter_runtime.cache_clear()
    _LOGGED_RESOLUTION_WARNINGS.clear()


@functools.lru_cache(maxsize=None)
def _resolve_adapter_runtime(bot_type: str):
    """bundle 설정이 있는 bot_type에 대해 AdapterRuntime을 반환한다.

    use_adapter=False 이거나 bundle_dir이 비어있으면 None.
    lru_cache로 wrapper와 동일한 싱글턴 패턴을 따른다.
    """
    cfg = AGENT_REGISTRY.get(bot_type, {})
    if not cfg.get("use_adapter"):
        return None

    bundle_name = _resolve_bundle_dir_name(cfg)
    if not bundle_name:
        return None

    bundle_dir = os.path.join(_MODELS_DIR, bundle_name)
    manifest = load_bundle_manifest(bundle_dir)
    if manifest is None:
        logger.warning(
            "Bundle manifest missing for %s at %s — falling back to legacy wrapper.",
            bot_type, bundle_dir,
        )
        return None

    checkpoint_path = resolve_bundle_checkpoint(bundle_dir, manifest)
    from app.services.adapter_runtime import AdapterRuntime
    runtime = AdapterRuntime(manifest, checkpoint_path)
    logger.info(
        "AdapterRuntime ready for bot_type=%s bundle=%s adapter=%s",
        bot_type, manifest.get("bundle_id"), runtime.adapter.adapter_id,
    )
    return runtime


def get_adapter_runtime(bot_type: str):
    """외부에서 호출 가능한 adapter runtime getter."""
    normalized = require_valid_bot_type(bot_type)
    return _resolve_adapter_runtime(normalized)


def bot_agents_list() -> list[dict]:
    """프론트엔드 /api/bot-types 응답용 [{type, name}, ...] 리스트."""
    return [
        {"type": bot_type, "name": AGENT_REGISTRY[bot_type]["name"]}
        for bot_type in PUBLIC_BOT_TYPES
        if bot_type in AGENT_REGISTRY
    ]


def public_valid_bot_types() -> set[str]:
    """사용자에게 공개되는 bot_type 집합."""
    return {bot_type for bot_type in PUBLIC_BOT_TYPES if bot_type in AGENT_REGISTRY}


def valid_bot_types() -> set[str]:
    """유효한 bot_type 집합."""
    return set(AGENT_REGISTRY.keys())
