"""편의 re-export: common.adapter 경로로 base_adapter 심볼을 노출한다."""
from .base_adapter import DecodeResult, PolicyAdapter

__all__ = ["DecodeResult", "PolicyAdapter"]
