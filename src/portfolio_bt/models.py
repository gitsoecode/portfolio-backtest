from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_METRIC_KEYS = (
    "cagr",
    "total_return",
    "annualized_volatility",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "best_year",
    "worst_year",
)

REQUIRED_RESULT_KEYS = (
    "portfolio_name",
    "weights",
    "date_range",
    "warnings",
    "daily_returns",
    "growth_series",
    "drawdown_series",
    "metrics",
)


def ensure_datetime_index(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy indexed by a normalized DatetimeIndex."""
    working = frame.copy()
    if not isinstance(working.index, pd.DatetimeIndex):
        if "date" not in working.columns:
            raise ValueError("A 'date' column is required when the DataFrame is not date-indexed.")
        working["date"] = pd.to_datetime(working["date"])
        working = working.set_index("date")
    working.index = pd.to_datetime(working.index).tz_localize(None)
    working = working.sort_index()
    working = working[~working.index.duplicated(keep="last")]
    return working


def slice_frame(
    frame: pd.DataFrame, start: str | None = None, end: str | None = None
) -> pd.DataFrame:
    working = ensure_datetime_index(frame)
    if start is not None:
        working = working.loc[working.index >= pd.Timestamp(start)]
    if end is not None:
        working = working.loc[working.index <= pd.Timestamp(end)]
    return working


def to_python_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return 0.0
    return value


def series_to_records(series: pd.Series) -> list[dict[str, Any]]:
    cleaned = pd.Series(series).copy()
    cleaned.index = pd.to_datetime(cleaned.index)
    records: list[dict[str, Any]] = []
    for idx, value in cleaned.items():
        records.append({"date": idx.date().isoformat(), "value": float(value)})
    return records


def to_jsonable(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {str(key): to_jsonable(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [to_jsonable(value) for value in payload]
    if isinstance(payload, pd.Series):
        return series_to_records(payload)
    if isinstance(payload, pd.DataFrame):
        return to_jsonable(payload.reset_index().to_dict(orient="records"))
    return to_python_scalar(payload)
