import os
import json
import torch
import logging
import sys
from dataclasses import dataclass
from typing import Dict, Optional

from .legacy_models import LegacyPPOAgent
from .wrappers import (
    AgentWrapper, 
    LegacyPPOAgentWrapper, 
    PPOAgentWrapper, 
    RandomAgentWrapper
)

# PuCo_RL 모델 임포트
PUCO_RL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../PuCo_RL"))
if PUCO_RL_PATH not in sys.path:
    sys.path.append(PUCO_RL_PATH)

try:
    from agents.ppo_agent import Agent as ResidualAgent, PhasePPOAgent
except ImportError:
    ResidualAgent = None
    PhasePPOAgent = None

logger = logging.getLogger(__name__)

@dataclass
class AgentMetadata:
    """모델 명세를 정의하는 경량 메타데이터 모델."""
    name: str
    architecture: str  # "legacy_ppo", "ppo", "ppo_residual", "phase_ppo"
    obs_dim: int = 210
    action_dim: int = 200
    hidden_dim: int = 256
    num_res_blocks: int = 3
    version: Optional[str] = "1.0.0"

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMetadata":
        if data.get("schema_version") == "model-metadata.v1":
            network = data.get("network") or {}
            return cls(
                name=data["artifact_name"],
                architecture=data["architecture"],
                obs_dim=int(data.get("obs_dim", 210)),
                action_dim=int(data.get("action_dim", 200)),
                hidden_dim=int(network.get("hidden_dim", 256)),
                num_res_blocks=int(network.get("num_res_blocks", 3)),
                version=data.get("version", "1.0.0"),
            )
        return cls(
            name=data.get("name") or data.get("artifact_name"),
            architecture=data["architecture"],
            obs_dim=int(data.get("obs_dim", 210)),
            action_dim=int(data.get("action_dim", 200)),
            hidden_dim=int(data.get("hidden_dim", 256)),
            num_res_blocks=int(data.get("num_res_blocks", 3)),
            version=data.get("version", "1.0.0"),
        )

class AgentFactory:
    """에이전트 인스턴스 생성을 관리하는 싱글톤 팩토리"""
    _instances: Dict[str, AgentWrapper] = {}
    _device: Optional[torch.device] = None

    @classmethod
    def get_device(cls) -> torch.device:
        """최적의 하드웨어 가속 디바이스 감지"""
        if cls._device is None:
            if torch.cuda.is_available():
                cls._device = torch.device("cuda")
            elif torch.backends.mps.is_available():
                cls._device = torch.device("mps")
            else:
                cls._device = torch.device("cpu")
            logger.info(f"AgentFactory using device: {cls._device}")
        return cls._device

    @classmethod
    def get_agent(cls, model_path: str) -> AgentWrapper:
        """
        모델 경로를 받아 적절한 에이전트 래퍼를 반환 (캐싱 포함).
        실패 시 RandomAgentWrapper로 안전하게 폴백.
        """
        if model_path in cls._instances:
            return cls._instances[model_path]

        try:
            wrapper = cls._create_agent(model_path)
            cls._instances[model_path] = wrapper
            return wrapper
        except Exception as e:
            logger.error(f"Failed to create agent from {model_path}: {e}", exc_info=True)
            logger.warning("Falling back to RandomAgentWrapper for safety.")
            return RandomAgentWrapper()

    @classmethod
    def _create_agent(cls, model_path: str) -> AgentWrapper:
        """실제 모델 객체 생성 및 가중치 로드 로직"""
        device = cls.get_device()
        
        # 1. 메타데이터 로드 (.json)
        metadata_path = os.path.splitext(model_path)[0] + ".json"
        if os.path.exists(metadata_path):
            with open(metadata_path, "r") as f:
                data = json.load(f)
                metadata = AgentMetadata.from_dict(data)
            logger.info(f"Loaded metadata for {metadata.name}: {metadata.architecture}")
        else:
            # 메타데이터 부재 시 하위 호환을 위해 legacy_ppo로 가정
            logger.warning(f"Metadata not found for {model_path}. Assuming legacy_ppo.")
            metadata = AgentMetadata(
                name=os.path.basename(model_path),
                architecture="legacy_ppo"
            )

        # 2. 아키텍처에 따른 모델 초기화
        if metadata.architecture == "legacy_ppo":
            model = LegacyPPOAgent(
                obs_dim=metadata.obs_dim, 
                action_dim=metadata.action_dim, 
                hidden_dim=metadata.hidden_dim
            )
            wrapper_cls = LegacyPPOAgentWrapper
            
        elif metadata.architecture in {"ppo", "ppo_residual"}:
            if ResidualAgent is None:
                raise ImportError("ResidualAgent class not found in PuCo_RL")
            model = ResidualAgent(
                obs_dim=metadata.obs_dim, 
                action_dim=metadata.action_dim,
                hidden_dim=metadata.hidden_dim,
                num_res_blocks=metadata.num_res_blocks,
            )
            wrapper_cls = PPOAgentWrapper
            
        elif metadata.architecture == "phase_ppo":
            if PhasePPOAgent is None:
                raise ImportError("PhasePPOAgent class not found in PuCo_RL")
            model = PhasePPOAgent(
                obs_dim=metadata.obs_dim, 
                action_dim=metadata.action_dim
            )
            wrapper_cls = PPOAgentWrapper
        else:
            raise ValueError(f"Unsupported architecture: {metadata.architecture}")

        # 3. 가중치 로드
        checkpoint = torch.load(model_path, map_location=device)
        state_dict = checkpoint.get("model_state_dict", checkpoint)

        # Common alias cleanup for checkpoints saved through wrappers / DataParallel.
        normalized_state_dict = {}
        for key, value in state_dict.items():
            normalized_key = key
            for prefix in ("module.", "model_state_dict.", "model."):
                if normalized_key.startswith(prefix):
                    normalized_key = normalized_key[len(prefix):]
            normalized_state_dict[normalized_key] = value

        # 차원 검증 결과와 실제 가중치 shape 일치 여부를 strict load로 보장한다.
        model.load_state_dict(normalized_state_dict, strict=True)
        model.to(device)
        
        return wrapper_cls(model, device)

    @classmethod
    def clear_cache(cls):
        """캐시된 인스턴스 비우기 (테스트용)"""
        cls._instances.clear()
