from __future__ import annotations

import pandas as pd

from portfolio_bt.metrics.calculator import build_drawdown_series, calculate_metrics


def test_constant_positive_returns_yield_positive_cagr():
    returns = pd.Series([0.0] + [0.001] * 251)
    growth = 10_000 * (1.0 + returns).cumprod()
    metrics = calculate_metrics(returns, growth)
    assert metrics["cagr"] > 0.0


def test_zero_return_series_yields_zero_cagr_and_zero_volatility():
    returns = pd.Series([0.0] * 252)
    growth = pd.Series([10_000.0] * 252)
    metrics = calculate_metrics(returns, growth)
    assert metrics["cagr"] == 0.0
    assert metrics["annualized_volatility"] == 0.0


def test_drawdown_matches_known_path():
    growth = pd.Series([100.0, 110.0, 90.0, 120.0])
    drawdown = build_drawdown_series(growth)
    assert round(float(drawdown.min()), 4) == -0.1818


def test_metrics_never_emit_nan_or_inf():
    returns = pd.Series([0.0] * 10)
    growth = pd.Series([10_000.0] * 10)
    metrics = calculate_metrics(returns, growth)
    for _key, value in metrics.items():
        if isinstance(value, dict):
            continue
        assert value == value
        assert value not in (float("inf"), float("-inf"))
