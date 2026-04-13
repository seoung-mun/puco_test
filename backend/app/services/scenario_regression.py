from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.services.bot_service import BotInputSnapshot, BotService
from app.services.engine_gateway import EngineWrapper, create_game_engine
from app.services.engine_gateway.constants import BUILDING_DATA, BuildingType, Phase, Role, TileType


ScenarioPrepare = Callable[[EngineWrapper], None]
ScenarioProvider = Callable[[EngineWrapper, BotInputSnapshot], int]


@dataclass(frozen=True)
class ScenarioSpec:
    name: str
    description: str
    actor_id: str
    expected_actions: frozenset[int]
    forbidden_actions: frozenset[int]
    prepare: ScenarioPrepare


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    selected_action: int
    valid: bool
    passed: bool
    reason: str
    expected_actions: tuple[int, ...]
    forbidden_actions: tuple[int, ...]


def _reset_to_role_selection(engine: EngineWrapper) -> None:
    game = engine.env.game
    game.current_phase = Phase.END_ROUND
    game.current_player_idx = 0
    game.active_role_player = None
    game.players_taken_action = 0
    engine.env.agent_selection = "player_0"
    engine._refresh_cached_view()


def prepare_trader_overselection_scenario(engine: EngineWrapper) -> None:
    _reset_to_role_selection(engine)
    game = engine.env.game
    player = game.players[0]
    player.island_board = []
    player.city_board = []
    player.doubloons = BUILDING_DATA[BuildingType.WHARF][0]
    player.place_plantation(TileType.CORN_PLANTATION)
    player.place_plantation(TileType.INDIGO_PLANTATION)
    game.role_doubloons = {role: 0 for role in Role}
    engine._refresh_cached_view()


def prepare_high_doubloon_role_priority_scenario(engine: EngineWrapper) -> None:
    _reset_to_role_selection(engine)
    game = engine.env.game
    player = game.players[0]
    player.island_board = []
    player.city_board = []
    player.doubloons = BUILDING_DATA[BuildingType.SMALL_MARKET][0]
    game.role_doubloons = {role: 0 for role in Role}
    game.role_doubloons[Role.BUILDER] = 5
    engine._refresh_cached_view()


def prepare_mayor_strategy_scenario(engine: EngineWrapper) -> None:
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

    engine.env.agent_selection = "player_0"
    engine._refresh_cached_view()


def trader_overselection_scenario() -> ScenarioSpec:
    return ScenarioSpec(
        name="trader-overselection",
        description="Trader should not be chosen when there are no goods to sell and a strong builder spike exists.",
        actor_id="BOT_shipping_rush",
        expected_actions=frozenset({Role.BUILDER.value}),
        forbidden_actions=frozenset({Role.TRADER.value}),
        prepare=prepare_trader_overselection_scenario,
    )


def high_doubloon_role_priority_scenario() -> ScenarioSpec:
    return ScenarioSpec(
        name="high-doubloon-role-priority",
        description="A role carrying 5 doubloons should be treated as the immediate high-priority pickup when it is already actionable.",
        actor_id="BOT_action_value",
        expected_actions=frozenset({Role.BUILDER.value}),
        forbidden_actions=frozenset(),
        prepare=prepare_high_doubloon_role_priority_scenario,
    )


def mayor_strategy_scenario() -> ScenarioSpec:
    return ScenarioSpec(
        name="mayor-slot-direct-band",
        description="Mayor decisions must use slot-direct actions (120-131 island, 140-151 city).",
        actor_id="BOT_factory_rule",
        expected_actions=frozenset(range(120, 132)) | frozenset(range(140, 152)),
        forbidden_actions=frozenset({69, 70, 71, 72, 73, 74, 75}),
        prepare=prepare_mayor_strategy_scenario,
    )


class ScenarioRegressionHarness:
    def build_engine(self) -> EngineWrapper:
        return create_game_engine(num_players=3, governor_idx=0)

    def evaluate(
        self,
        scenario: ScenarioSpec,
        provider: ScenarioProvider,
    ) -> ScenarioResult:
        engine = self.build_engine()
        scenario.prepare(engine)
        snapshot = BotService.build_input_snapshot(engine, scenario.actor_id)
        selected_action = int(provider(engine, snapshot))
        valid = bool(
            0 <= selected_action < len(snapshot.action_mask)
            and snapshot.action_mask[selected_action]
        )

        if not valid:
            return ScenarioResult(
                name=scenario.name,
                selected_action=selected_action,
                valid=False,
                passed=False,
                reason="selected action is not valid in the prepared scenario mask",
                expected_actions=tuple(sorted(scenario.expected_actions)),
                forbidden_actions=tuple(sorted(scenario.forbidden_actions)),
            )

        if scenario.expected_actions and selected_action not in scenario.expected_actions:
            return ScenarioResult(
                name=scenario.name,
                selected_action=selected_action,
                valid=True,
                passed=False,
                reason=f"expected one of {sorted(scenario.expected_actions)}",
                expected_actions=tuple(sorted(scenario.expected_actions)),
                forbidden_actions=tuple(sorted(scenario.forbidden_actions)),
            )

        if selected_action in scenario.forbidden_actions:
            return ScenarioResult(
                name=scenario.name,
                selected_action=selected_action,
                valid=True,
                passed=False,
                reason=f"forbidden action selected: {selected_action}",
                expected_actions=tuple(sorted(scenario.expected_actions)),
                forbidden_actions=tuple(sorted(scenario.forbidden_actions)),
            )

        return ScenarioResult(
            name=scenario.name,
            selected_action=selected_action,
            valid=True,
            passed=True,
            reason="scenario passed",
            expected_actions=tuple(sorted(scenario.expected_actions)),
            forbidden_actions=tuple(sorted(scenario.forbidden_actions)),
        )

    def evaluate_bot_type(self, scenario: ScenarioSpec, bot_type: str) -> ScenarioResult:
        return self.evaluate(
            scenario,
            lambda engine, snapshot: BotService.get_action(
                bot_type,
                {
                    "vector_obs": snapshot.obs,
                    "action_mask": snapshot.action_mask,
                    "phase_id": snapshot.phase_id,
                    "current_player_idx": snapshot.current_player_idx,
                    "env": engine.env,
                },
            ),
        )


__all__ = [
    "ScenarioRegressionHarness",
    "ScenarioResult",
    "ScenarioSpec",
    "high_doubloon_role_priority_scenario",
    "mayor_strategy_scenario",
    "prepare_high_doubloon_role_priority_scenario",
    "prepare_mayor_strategy_scenario",
    "prepare_trader_overselection_scenario",
    "trader_overselection_scenario",
]
