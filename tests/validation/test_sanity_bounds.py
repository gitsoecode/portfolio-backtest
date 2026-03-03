from __future__ import annotations

from tests.helpers import load_price_fixture, pivot_adj_close

from portfolio_bt.engine.backtester import run_backtest

BOUNDS = {
    "cagr": (-0.50, 0.50),
    "total_return": (-0.99, 10.0),
    "annualized_volatility": (0.0, 1.0),
    "sharpe_ratio": (-5.0, 5.0),
    "sortino_ratio": (-5.0, 10.0),
    "max_drawdown": (-1.0, 0.0),
}


def test_sanity_bounds_hold_for_validation_scenarios():
    scenarios = [
        ("spy_2010_2020", {"SPY": 1.0}),
        ("three_fund_2011_2020", {"VTI": 0.60, "VXUS": 0.20, "BND": 0.20}),
        ("bond_2010_2020", {"BND": 1.0}),
    ]
    for fixture_name, weights in scenarios:
        matrix = pivot_adj_close(load_price_fixture(fixture_name))
        result = run_backtest(matrix, weights, rebalance="annual")
        for metric_name, (lower, upper) in BOUNDS.items():
            actual = float(result["metrics"][metric_name])
            assert lower <= actual <= upper, (
                f"{fixture_name} {metric_name} expected between {lower} and {upper}, "
                f"received {actual}"
            )
