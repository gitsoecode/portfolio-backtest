from __future__ import annotations

import math

import numpy as np
import pandas as pd


def build_drawdown_series(growth_series: pd.Series) -> pd.Series:
    growth = pd.Series(growth_series, copy=True).astype(float)
    rolling_max = growth.cummax()
    drawdown = (growth / rolling_max) - 1.0
    drawdown = drawdown.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    drawdown.name = "drawdown_series"
    return drawdown


def annual_returns_series(growth_series: pd.Series) -> pd.Series:
    growth = pd.Series(growth_series, copy=True).astype(float)
    if not isinstance(growth.index, pd.DatetimeIndex):
        annual = pd.Series({0: (float(growth.iloc[-1]) / float(growth.iloc[0])) - 1.0})
        annual = annual.replace([np.inf, -np.inf], 0.0).fillna(0.0)
        annual.name = "annual_returns"
        return annual
    grouped = growth.groupby(growth.index.year)
    annual = grouped.last() / grouped.first() - 1.0
    annual = annual.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    annual.index = annual.index.astype(int)
    annual.name = "annual_returns"
    return annual


def _safe_float(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return float(value)


def _best_and_worst_year(
    annual_returns: pd.Series,
) -> tuple[dict[str, float | int], dict[str, float | int]]:
    if annual_returns.empty:
        zero = {"year": 0, "return": 0.0}
        return zero, zero
    best_year_index = int(annual_returns.idxmax())
    worst_year_index = int(annual_returns.idxmin())
    return (
        {
            "year": best_year_index,
            "return": _safe_float(float(annual_returns.loc[best_year_index])),
        },
        {
            "year": worst_year_index,
            "return": _safe_float(float(annual_returns.loc[worst_year_index])),
        },
    )


def calculate_metrics(
    daily_returns: pd.Series,
    growth_series: pd.Series,
    *,
    risk_free_rate: float = 0.0,
) -> dict[str, float | dict[str, float | int]]:
    returns = (
        pd.Series(daily_returns, copy=True)
        .astype(float)
        .replace([np.inf, -np.inf], 0.0)
        .fillna(0.0)
    )
    growth = (
        pd.Series(growth_series, copy=True)
        .astype(float)
        .replace([np.inf, -np.inf], 0.0)
        .ffill()
        .fillna(0.0)
    )
    if growth.empty:
        zero = {"year": 0, "return": 0.0}
        return {
            "cagr": 0.0,
            "total_return": 0.0,
            "annualized_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown": 0.0,
            "final_value": 0.0,
            "best_year": zero,
            "worst_year": zero,
        }

    total_return = _safe_float((float(growth.iloc[-1]) / float(growth.iloc[0])) - 1.0)
    periods = max(len(returns) - 1, 0)
    if periods == 0:
        cagr = 0.0
    else:
        cagr = _safe_float((1.0 + total_return) ** (252.0 / periods) - 1.0)

    average_daily = float(returns.mean())
    annualized_volatility = _safe_float(float(returns.std(ddof=0)) * math.sqrt(252.0))
    annualized_return = average_daily * 252.0
    sharpe_ratio = 0.0
    if annualized_volatility > 0:
        sharpe_ratio = _safe_float((annualized_return - risk_free_rate) / annualized_volatility)

    downside = returns.where(returns < 0.0, 0.0)
    downside_deviation = _safe_float(float(np.sqrt(downside.pow(2).mean())) * math.sqrt(252.0))
    sortino_ratio = 0.0
    if downside_deviation > 0:
        sortino_ratio = _safe_float((annualized_return - risk_free_rate) / downside_deviation)

    drawdown = build_drawdown_series(growth)
    annual = annual_returns_series(growth)
    best_year, worst_year = _best_and_worst_year(annual)

    return {
        "cagr": _safe_float(cagr),
        "total_return": _safe_float(total_return),
        "annualized_volatility": _safe_float(annualized_volatility),
        "sharpe_ratio": _safe_float(sharpe_ratio),
        "sortino_ratio": _safe_float(sortino_ratio),
        "max_drawdown": min(0.0, _safe_float(float(drawdown.min()))),
        "final_value": _safe_float(float(growth.iloc[-1])),
        "best_year": best_year,
        "worst_year": worst_year,
    }
