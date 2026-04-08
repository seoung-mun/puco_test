import uuid
from unittest.mock import patch

import pytest

from app.services.engine_gateway import create_game_engine
from app.services.bot_service import BotService
from app.services.state_serializer import serialize_game_state_from_engine
from configs.constants import BuildingType, Phase, TileType


def _prepare_strategy_mayor_engine(current_player_idx: int = 0):
    engine = create_game_engine(num_players=3, governor_idx=0)
    game = engine.env.game

    game.current_phase = Phase.MAYOR
    game.current_player_idx = current_player_idx
    game.active_role_player = 0
    game.players_taken_action = 0

    for player in game.players:
        player.unplaced_colonists = 3
        player.island_board = []
        player.city_board = []
        player.place_plantation(TileType.CORN_PLANTATION)
        player.place_plantation(TileType.INDIGO_PLANTATION)
        player.build_building(BuildingType.SMALL_INDIGO_PLANT)
        player.build_building(BuildingType.SMALL_MARKET)

    engine.env.agent_selection = f"player_{current_player_idx}"
    engine._refresh_cached_view()
    return engine


def _serialize_state(engine):
    return serialize_game_state_from_engine(
        engine=engine,
        player_names=["Alice", "Bob", "Cara"],
        game_id="mayor-strategy-contract",
    )


def test_human_mayor_state_exposes_strategy_actions_without_sequential_meta():
    engine = _prepare_strategy_mayor_engine(current_player_idx=0)

    state = _serialize_state(engine)
    strategy_mask = [bool(state["action_mask"][idx]) for idx in range(69, 72)]
    legacy_mask = [bool(state["action_mask"][idx]) for idx in range(72, 76)]

    assert state["meta"]["phase"] == "mayor_action"
    assert "mayor_slot_idx" not in state["meta"]
    assert "mayor_can_skip" not in state["meta"]
    assert strategy_mask == [True, True, True]
    assert legacy_mask == [False, False, False, False]


def test_human_mayor_strategy_action_advances_with_single_action():
    engine = _prepare_strategy_mayor_engine(current_player_idx=0)

    result = engine.step(69)
    state = _serialize_state(engine)

    assert result["done"] is False
    assert state["meta"]["phase"] == "mayor_action"
    assert state["meta"]["active_player"] == "player_1"
    assert [bool(state["action_mask"][idx]) for idx in range(69, 72)] == [True, True, True]


@pytest.mark.asyncio
async def test_bot_mayor_turn_dispatches_single_strategy_action():
    engine = _prepare_strategy_mayor_engine(current_player_idx=1)
    captured_actions = []

    async def _callback(game_id, actor_id, action):
        captured_actions.append((game_id, actor_id, action))

    async def _no_sleep(_seconds):
        return None

    with patch.object(BotService, "get_action", return_value=70):
        with patch("app.services.bot_service.asyncio.sleep", _no_sleep):
            await BotService.run_bot_turn(
                game_id=uuid.uuid4(),
                engine=engine,
                actor_id="BOT_ppo",
                process_action_callback=_callback,
            )

    assert len(captured_actions) == 1
    assert captured_actions[0][2] == 70


@pytest.mark.asyncio
async def test_bot_mayor_turn_normalizes_invalid_action_to_strategy_band():
    engine = _prepare_strategy_mayor_engine(current_player_idx=1)
    captured_actions = []

    async def _callback(game_id, actor_id, action):
        captured_actions.append((game_id, actor_id, action))

    async def _no_sleep(_seconds):
        return None

    with patch.object(BotService, "get_action", return_value=15):
        with patch("app.services.bot_service.asyncio.sleep", _no_sleep):
            await BotService.run_bot_turn(
                game_id=uuid.uuid4(),
                engine=engine,
                actor_id="BOT_factory_rule",
                process_action_callback=_callback,
            )

    assert len(captured_actions) == 1
    assert 69 <= captured_actions[0][2] <= 71


def test_channel_api_no_longer_exposes_mayor_distribute_endpoint(client):
    response = client.post(
        f"/api/puco/game/{uuid.uuid4()}/mayor-distribute",
        json={"placements": []},
    )

    assert response.status_code == 404
