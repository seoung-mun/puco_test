from app.services.engine_gateway.constants import Role
from app.services.scenario_regression import (
    ScenarioRegressionHarness,
    high_doubloon_role_priority_scenario,
    mayor_strategy_scenario,
    trader_overselection_scenario,
)


def test_trader_overselection_scenario_rejects_trader_pick():
    harness = ScenarioRegressionHarness()
    result = harness.evaluate(
        trader_overselection_scenario(),
        lambda _engine, _snapshot: Role.TRADER.value,
    )

    assert result.valid is True
    assert result.passed is False
    assert result.selected_action == Role.TRADER.value


def test_trader_overselection_scenario_accepts_builder_pick():
    harness = ScenarioRegressionHarness()
    result = harness.evaluate(
        trader_overselection_scenario(),
        lambda _engine, _snapshot: Role.BUILDER.value,
    )

    assert result.valid is True
    assert result.passed is True


def test_high_doubloon_role_priority_scenario_accepts_bonus_role_pick():
    harness = ScenarioRegressionHarness()
    result = harness.evaluate(
        high_doubloon_role_priority_scenario(),
        lambda _engine, _snapshot: Role.BUILDER.value,
    )

    assert result.valid is True
    assert result.passed is True


def test_mayor_strategy_scenario_exposes_strategy_band_only():
    harness = ScenarioRegressionHarness()
    scenario = mayor_strategy_scenario()
    engine = harness.build_engine()
    scenario.prepare(engine)
    snapshot = engine.get_action_mask()

    assert snapshot[69:72] == [1, 1, 1]
    assert snapshot[72:76] == [0, 0, 0, 0]


def test_mayor_strategy_scenario_accepts_real_bot_service_action():
    harness = ScenarioRegressionHarness()
    result = harness.evaluate_bot_type(
        mayor_strategy_scenario(),
        "factory_rule",
    )

    assert result.valid is True
    assert result.passed is True
    assert result.selected_action in {69, 70, 71}
