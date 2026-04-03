import pytest
from app.engine_wrapper.wrapper import EngineWrapper

def test_governor_is_always_player_0():
    """EngineWrapper 생성 시 주지사가 항상 player_0이어야 한다."""
    for _ in range(10): # 여러 번 반복하여 랜덤 배정 여부 확인
        engine = EngineWrapper(num_players=3)
        assert engine.env.game.governor_idx == 0
        assert engine.env.game.current_player_idx == 0

def test_initial_plantation_consistent_with_governor_0():
    """governor가 0일 때 player_0이 인디고(3인 기준)를 받아야 한다."""
    # 3인 게임 규칙: 주지사(0)와 다음(1)은 인디고, 마지막(2)은 옥수수
    engine = EngineWrapper(num_players=3)
    game = engine.env.game
    p0 = game.players[0]

    # TileType 확인 (PuCo_RL 환경 의존성)
    from configs.constants import TileType
    
    # player_0의 이사회에 인디고가 있는지 확인
    has_indigo = any(t.tile_type == TileType.INDIGO_PLANTATION for t in p0.island_board)
    assert has_indigo, "Governor should start with Indigo in a 3-player game"
