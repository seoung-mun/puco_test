import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_mayor_orchestrator.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

import pytest

from app.engine_wrapper.wrapper import create_game_engine
from app.services.mayor_orchestrator import (
    MayorPlacement,
    build_slot_catalog,
    translate_plan_to_actions,
)
from configs.constants import BuildingType, Phase, TileType


def _prepare_engine():
    engine = create_game_engine(num_players=3)
    game = engine.env.game
    game.current_phase = Phase.MAYOR
    game.current_player_idx = 0
    game.active_role_player = 0
    game.players_taken_action = 0

    player = game.players[0]
    player.unplaced_colonists = 3
    player.island_board = []
    player.city_board = []
    player.place_plantation(TileType.CORN_PLANTATION)
    player.place_plantation(TileType.INDIGO_PLANTATION)
    player.build_building(BuildingType.SMALL_INDIGO_PLANT)
    player.build_building(BuildingType.SMALL_MARKET)

    game._init_mayor_placement(0)
    engine._refresh_cached_view()
    return engine


def test_build_slot_catalog_matches_engine_order():
    engine = _prepare_engine()
    catalog = build_slot_catalog(engine.env.game, 0)

    assert [slot["slot_id"] for slot in catalog] == [
        "island:corn_plantation:0",
        "island:indigo_plantation:1",
        "city:small_indigo_plant:0",
        "city:small_market:1",
    ]


def test_translate_plan_to_actions_maps_missing_slots_to_zero():
    engine = _prepare_engine()
    actions = translate_plan_to_actions(
        engine.env.game,
        0,
        [MayorPlacement(slot_id="island:indigo_plantation:1", count=1)],
    )

    assert actions == [69, 70, 69, 69]


def test_translate_plan_rejects_unknown_slot():
    engine = _prepare_engine()
    with pytest.raises(ValueError, match="Unknown Mayor slot_id"):
        translate_plan_to_actions(
            engine.env.game,
            0,
            [MayorPlacement(slot_id="city:unknown:99", count=1)],
        )
