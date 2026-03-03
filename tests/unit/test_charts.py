from __future__ import annotations

from portfolio_bt.api import compare_portfolios
from portfolio_bt.engine.backtester import run_backtest
from portfolio_bt.viz.charts import render_chart


def test_chart_rendering_returns_figure_object(compare_price_matrix):
    result = run_backtest(
        compare_price_matrix, {"SPY": 1.0}, rebalance="none", portfolio_name="SPY"
    )
    figure = render_chart("growth", result)
    assert figure.data


def test_png_export_creates_non_trivial_file(tmp_path, compare_price_matrix):
    result = run_backtest(
        compare_price_matrix, {"SPY": 1.0}, rebalance="none", portfolio_name="SPY"
    )
    output_path = tmp_path / "growth.png"
    render_chart("growth", result, output_path=str(output_path))
    assert output_path.exists()
    assert output_path.stat().st_size > 1_000


def test_titles_and_axis_labels_are_present(compare_price_matrix):
    single = run_backtest(
        compare_price_matrix, {"SPY": 1.0}, rebalance="none", portfolio_name="SPY"
    )
    comparison = compare_portfolios(
        compare_price_matrix,
        [
            {"name": "SPY", "weights": {"SPY": 1.0}},
            {"name": "Balanced", "weights": {"VTI": 0.6, "BND": 0.4}},
        ],
        benchmark={"SPY": 1.0},
    )
    for chart_type, payload in (
        ("growth", single),
        ("drawdown", single),
        ("annual_returns", single),
        ("comparison", comparison),
    ):
        figure = render_chart(chart_type, payload)
        assert figure.layout.title.text
        assert figure.layout.xaxis.title.text
        assert figure.layout.yaxis.title.text
