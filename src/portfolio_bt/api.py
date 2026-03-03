from __future__ import annotations

import copy

import pandas as pd

from portfolio_bt.data.fetcher import fetch_prices
from portfolio_bt.engine.backtester import run_backtest
from portfolio_bt.errors import ValidationError
from portfolio_bt.viz.charts import render_chart

__all__ = ["compare_portfolios", "fetch_prices", "render_chart", "run_backtest"]


def compare_portfolios(
    prices: pd.DataFrame,
    portfolios: list[dict],
    *,
    start: str | None = None,
    end: str | None = None,
    rebalance: str = "quarterly",
    initial_capital: float = 10_000.0,
    benchmark: dict[str, float] | None = None,
) -> dict:
    """Run multiple named portfolio backtests and return a comparison bundle."""
    if not portfolios:
        raise ValidationError("At least one portfolio definition is required.")
    if len(portfolios) > 5:
        raise ValidationError("Phase 1 supports comparing up to 5 portfolios.")

    results: list[dict] = []
    comparison_table: list[dict] = []
    for definition in portfolios:
        name = str(definition.get("name", "")).strip()
        if not name:
            raise ValidationError("Each portfolio must provide a non-empty 'name'.")
        weights = definition.get("weights")
        if not isinstance(weights, dict):
            raise ValidationError("Each portfolio must provide a weights dictionary.")
        result = run_backtest(
            prices,
            weights,
            start=start,
            end=end,
            rebalance=rebalance,
            initial_capital=initial_capital,
            portfolio_name=name,
        )
        results.append(result)
        row = {"portfolio_name": name, **copy.deepcopy(result["metrics"])}
        comparison_table.append(row)

    benchmark_result = None
    if benchmark is not None:
        benchmark_result = run_backtest(
            prices,
            benchmark,
            start=start,
            end=end,
            rebalance=rebalance,
            initial_capital=initial_capital,
            portfolio_name="Benchmark",
        )

    return {
        "portfolios": results,
        "benchmark": benchmark_result,
        "comparison_table": comparison_table,
    }
