from typing import Any, Optional

from app.engine_wrapper.wrapper import EngineWrapper, create_game_engine as _create_game_engine


def create_game_engine(
    num_players: int = 3,
    game_seed: Optional[int] = None,
    governor_idx: Optional[int] = None,
    **env_kwargs: Any,
) -> EngineWrapper:
    """Single backend entrypoint for canonical engine construction."""
    return _create_game_engine(
        num_players=num_players,
        game_seed=game_seed,
        governor_idx=governor_idx,
        **env_kwargs,
    )
