from __future__ import annotations

from tests.helpers import load_price_fixture, pivot_adj_close

from portfolio_bt.engine.backtester import run_backtest


def test_known_answers_stay_within_expected_ranges(known_answers):
    fixture_map = {
        "spy_2010_2020": "spy_2010_2020",
        "three_fund_2011_2020": "three_fund_2011_2020",
        "bonds_only_2010_2020": "bond_2010_2020",
    }
    for scenario_name, scenario in known_answers.items():
        matrix = pivot_adj_close(load_price_fixture(fixture_map[scenario_name]))
        result = run_backtest(
            matrix,
            scenario["portfolio"],
            start=scenario["start"],
            end=scenario["end"],
            rebalance=scenario["rebalance"],
            portfolio_name=scenario_name,
        )
        for metric_name, bounds in scenario["expected"].items():
            actual = float(result["metrics"][metric_name])
            assert bounds["min"] <= actual <= bounds["max"], (
                f"{scenario_name} {metric_name} expected between "
                f"{bounds['min']} and {bounds['max']}, "
                f"received {actual}"
            )
