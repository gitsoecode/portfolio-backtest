from __future__ import annotations

import pandas as pd
import pytest
from tests.helpers import pivot_adj_close

from portfolio_bt.engine.backtester import run_backtest
from portfolio_bt.errors import ValidationError


def test_shared_date_range_uses_intersection_and_warns():
    dates_a = pd.bdate_range("2020-01-01", periods=40)
    dates_b = pd.bdate_range("2020-02-03", periods=30)
    frame = pd.concat(
        [
            pd.DataFrame(
                {
                    "date": dates_a,
                    "ticker": "AAA",
                    "adj_close": [100.0 + index for index in range(len(dates_a))],
                }
            ),
            pd.DataFrame(
                {
                    "date": dates_b,
                    "ticker": "BBB",
                    "adj_close": [90.0 + index for index in range(len(dates_b))],
                }
            ),
        ],
        ignore_index=True,
    )
    result = run_backtest(frame, {"AAA": 0.5, "BBB": 0.5}, start="2020-01-01", end="2020-03-31")
    assert result["date_range"]["actual_start"] == "2020-02-03"
    assert result["warnings"]


def test_run_backtest_rejects_invalid_weights(compare_price_matrix):
    with pytest.raises(ValidationError):
        run_backtest(compare_price_matrix, {"VTI": 0.7, "BND": 0.2})


def test_different_rebalance_schedules_can_produce_different_outputs(compare_prices):
    matrix = pivot_adj_close(compare_prices)
    monthly = run_backtest(matrix, {"VTI": 0.5, "VXUS": 0.5}, rebalance="monthly")
    none = run_backtest(matrix, {"VTI": 0.5, "VXUS": 0.5}, rebalance="none")
    assert monthly["metrics"]["total_return"] != none["metrics"]["total_return"]


def test_fees_reduce_returns_when_turnover_occurs(compare_price_matrix):
    without_fees = run_backtest(
        compare_price_matrix, {"VTI": 0.5, "VXUS": 0.5}, rebalance="monthly"
    )
    with_fees = run_backtest(
        compare_price_matrix,
        {"VTI": 0.5, "VXUS": 0.5},
        rebalance="monthly",
        fee_bps=25.0,
    )
    assert with_fees["growth_series"].iloc[-1] < without_fees["growth_series"].iloc[-1]
