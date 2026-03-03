from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from portfolio_bt.engine.allocations import validate_weights
from portfolio_bt.engine.rebalance import build_rebalance_schedule
from portfolio_bt.errors import NoOverlapError, ValidationError
from portfolio_bt.metrics.calculator import build_drawdown_series, calculate_metrics
from portfolio_bt.models import ensure_datetime_index, slice_frame


def _extract_adj_close_matrix(prices: pd.DataFrame, tickers: Iterable[str]) -> pd.DataFrame:
    ticker_list = list(tickers)
    if prices.empty:
        raise ValidationError("Prices DataFrame cannot be empty.")

    if isinstance(prices.columns, pd.MultiIndex):
        if "adj_close" not in prices.columns.get_level_values(-1):
            raise ValidationError("MultiIndex prices must include an 'adj_close' column level.")
        matrix = prices.loc[:, pd.IndexSlice[ticker_list, "adj_close"]].copy()
        matrix.columns = matrix.columns.get_level_values(0)
        matrix.index = pd.to_datetime(matrix.index)
        return matrix.sort_index()

    if {"ticker", "adj_close"}.issubset(prices.columns):
        working = prices.copy()
        if not isinstance(working.index, pd.DatetimeIndex):
            if "date" not in working.columns:
                raise ValidationError("Long-form price data must include a 'date' column.")
            working["date"] = pd.to_datetime(working["date"])
            working = working.set_index("date")
        working.index = pd.to_datetime(working.index).tz_localize(None)
        working = working.sort_index()
        if "ticker" not in working.columns:
            raise ValidationError("Long-form price data must include a 'ticker' column.")
        matrix = working.pivot_table(
            index=working.index, columns="ticker", values="adj_close", aggfunc="last"
        )
        return matrix.sort_index()

    if len(ticker_list) == 1 and "adj_close" in prices.columns:
        working = ensure_datetime_index(prices)
        return pd.DataFrame({ticker_list[0]: working["adj_close"]}, index=working.index)

    if set(ticker_list).issubset(prices.columns):
        working = prices.copy()
        working.index = pd.to_datetime(working.index)
        return working.loc[:, ticker_list].sort_index()

    missing = sorted(set(ticker_list) - set(map(str, prices.columns)))
    raise ValidationError(f"Missing required price columns for tickers: {', '.join(missing)}.")


def run_backtest(
    prices: pd.DataFrame,
    weights: dict[str, float],
    *,
    start: str | None = None,
    end: str | None = None,
    rebalance: str = "quarterly",
    initial_capital: float = 10_000.0,
    fee_bps: float = 0.0,
    portfolio_name: str = "Portfolio",
) -> dict:
    """Run a long-only backtest over the shared date range."""
    normalized_weights = validate_weights(weights)
    tickers = list(normalized_weights)
    price_matrix = _extract_adj_close_matrix(prices, tickers)
    requested_slice = slice_frame(price_matrix, start=start, end=end)
    if requested_slice.empty:
        raise NoOverlapError("No price data exists in the requested date range.")

    aligned = requested_slice.dropna(how="any")
    if aligned.empty:
        raise NoOverlapError(
            "No overlapping date range remains after aligning all selected series."
        )

    warnings: list[str] = []
    actual_start = aligned.index.min().date().isoformat()
    actual_end = aligned.index.max().date().isoformat()
    if start is not None or end is not None:
        requested_start = start or requested_slice.index.min().date().isoformat()
        requested_end = end or requested_slice.index.max().date().isoformat()
        if requested_start != actual_start or requested_end != actual_end:
            warnings.append(
                f"Requested range trimmed to common overlap: {actual_start} through {actual_end}."
            )
    if len(requested_slice) - len(aligned) > 20:
        warnings.append(
            "Usable range was trimmed by more than 20 trading days to align all symbols."
        )

    schedule = build_rebalance_schedule(aligned.index, rebalance)
    rebalance_days = set(schedule[1:]) if len(schedule) > 1 else set()

    first_prices = aligned.iloc[0]
    holdings = {
        ticker: (float(initial_capital) * weight) / float(first_prices[ticker])
        for ticker, weight in normalized_weights.items()
    }

    values: list[float] = []
    for row_number, (date, row) in enumerate(aligned.iterrows()):
        portfolio_value = sum(float(holdings[ticker]) * float(row[ticker]) for ticker in tickers)
        if row_number > 0 and date in rebalance_days:
            current_weights = {
                ticker: (float(holdings[ticker]) * float(row[ticker])) / portfolio_value
                for ticker in tickers
            }
            turnover = (
                sum(abs(normalized_weights[ticker] - current_weights[ticker]) for ticker in tickers)
                / 2.0
            )
            if turnover > 0 and fee_bps > 0:
                portfolio_value = max(
                    portfolio_value - (portfolio_value * turnover * fee_bps / 10_000.0), 0.0
                )
            holdings = {
                ticker: (portfolio_value * normalized_weights[ticker]) / float(row[ticker])
                for ticker in tickers
            }
            portfolio_value = sum(
                float(holdings[ticker]) * float(row[ticker]) for ticker in tickers
            )
        values.append(float(portfolio_value))

    growth_series = pd.Series(values, index=aligned.index, name="growth_series")
    daily_returns = growth_series.pct_change().replace([pd.NA, pd.NaT], 0.0).fillna(0.0)
    daily_returns.name = "daily_returns"
    drawdown_series = build_drawdown_series(growth_series)
    metrics = calculate_metrics(daily_returns, growth_series)

    return {
        "portfolio_name": portfolio_name,
        "weights": dict(normalized_weights),
        "date_range": {
            "requested_start": start,
            "requested_end": end,
            "actual_start": actual_start,
            "actual_end": actual_end,
        },
        "warnings": warnings,
        "daily_returns": daily_returns,
        "growth_series": growth_series,
        "drawdown_series": drawdown_series,
        "metrics": metrics,
    }
