from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine_wrapper.wrapper import EngineWrapper


def create_game_engine(*args, **kwargs):
    from app.services.engine_gateway.factory import create_game_engine as _create_game_engine

    return _create_game_engine(*args, **kwargs)


def __getattr__(name: str):
    if name == "EngineWrapper":
        from app.engine_wrapper.wrapper import EngineWrapper as _EngineWrapper

        return _EngineWrapper
    if name == "create_game_engine":
        return create_game_engine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["EngineWrapper", "create_game_engine"]
