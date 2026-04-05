from app.engine_wrapper.wrapper import EngineWrapper


def _plantation_types(game):
    return [
        [getattr(tile.tile_type, "name", str(tile.tile_type)) for tile in player.island_board]
        for player in game.players
    ]


def test_game_seed_produces_reproducible_governor_and_setup():
    engine_a = EngineWrapper(num_players=3, game_seed=20260405)
    engine_b = EngineWrapper(num_players=3, game_seed=20260405)

    assert engine_a.env.game.governor_idx == engine_b.env.game.governor_idx
    assert engine_a.env.game.current_player_idx == engine_b.env.game.current_player_idx
    assert _plantation_types(engine_a.env.game) == _plantation_types(engine_b.env.game)


def test_random_governor_varies_across_seeds():
    governors = {
        EngineWrapper(num_players=3, game_seed=seed).env.game.governor_idx
        for seed in range(12)
    }

    assert governors <= {0, 1, 2}
    assert len(governors) >= 2


def test_governor_player_receives_indigo_in_three_player_game():
    engine = EngineWrapper(num_players=3, game_seed=20260405)
    game = engine.env.game
    governor_player = game.players[game.governor_idx]

    plantation_names = [getattr(tile.tile_type, "name", str(tile.tile_type)) for tile in governor_player.island_board]
    assert "INDIGO_PLANTATION" in plantation_names


def test_explicit_governor_override_uses_requested_player():
    engine = EngineWrapper(num_players=3, governor_idx=2)
    game = engine.env.game

    assert game.governor_idx == 2
    assert game.current_player_idx == 2

    plantation_names = [getattr(tile.tile_type, "name", str(tile.tile_type)) for tile in game.players[2].island_board]
    assert "INDIGO_PLANTATION" in plantation_names
