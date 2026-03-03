from __future__ import annotations

import json

from portfolio_bt.api import compare_portfolios
from portfolio_bt.engine.backtester import run_backtest
from portfolio_bt.models import REQUIRED_METRIC_KEYS, REQUIRED_RESULT_KEYS, to_jsonable
from portfolio_bt.viz.charts import render_chart


def test_result_objects_are_json_serializable(compare_price_matrix):
    result = run_backtest(
        compare_price_matrix, {"SPY": 1.0}, portfolio_name="SPY", rebalance="none"
    )
    serialized = to_jsonable(result)
    json.dumps(serialized)
    assert tuple(result.keys()) == REQUIRED_RESULT_KEYS
    assert tuple(result["metrics"].keys()) == REQUIRED_METRIC_KEYS


def test_comparison_table_contains_one_row_per_named_portfolio(compare_price_matrix):
    result = compare_portfolios(
        compare_price_matrix,
        [
            {"name": "Growth", "weights": {"VTI": 0.70, "VXUS": 0.20, "BND": 0.10}},
            {"name": "Balanced", "weights": {"VTI": 0.50, "VXUS": 0.20, "BND": 0.30}},
        ],
    )
    assert len(result["comparison_table"]) == 2
    assert [row["portfolio_name"] for row in result["comparison_table"]] == ["Growth", "Balanced"]


def test_warnings_are_always_a_list(compare_price_matrix):
    result = run_backtest(
        compare_price_matrix, {"SPY": 1.0}, portfolio_name="SPY", rebalance="none"
    )
    assert isinstance(result["warnings"], list)


def test_charts_have_titles_and_axis_labels(compare_price_matrix):
    result = run_backtest(
        compare_price_matrix, {"SPY": 1.0}, portfolio_name="SPY", rebalance="none"
    )
    for chart_type in ("growth", "drawdown", "annual_returns"):
        figure = render_chart(chart_type, result)
        assert figure.layout.title.text
        assert figure.layout.xaxis.title.text
        assert figure.layout.yaxis.title.text
