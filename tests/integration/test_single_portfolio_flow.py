from __future__ import annotations

from portfolio_bt.engine.backtester import run_backtest
from portfolio_bt.models import REQUIRED_METRIC_KEYS, REQUIRED_RESULT_KEYS


def test_single_portfolio_flow_matches_result_contract(three_fund_matrix):
    result = run_backtest(
        three_fund_matrix,
        {"VTI": 0.60, "VXUS": 0.20, "BND": 0.20},
        start="2011-02-01",
        end="2020-12-31",
        rebalance="annual",
        portfolio_name="Three Fund",
    )
    assert tuple(result.keys()) == REQUIRED_RESULT_KEYS
    assert tuple(result["metrics"].keys()) == REQUIRED_METRIC_KEYS
    assert result["date_range"]["actual_start"] == "2011-02-01"
    assert result["portfolio_name"] == "Three Fund"
