#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _returns_pattern(length: int, drift: float, amplitude: float, crash: float) -> np.ndarray:
    positions = np.arange(length, dtype=float)
    oscillation = np.sin(positions / 17.0) + 0.55 * np.cos(positions / 43.0)
    returns = drift + amplitude * oscillation
    crash_window = slice(int(length * 0.92), int(length * 0.93))
    rebound_window = slice(int(length * 0.93), int(length * 0.945))
    returns[crash_window] += crash
    returns[rebound_window] += abs(crash) * 0.55
    return np.clip(returns, -0.20, 0.20)


def _build_ticker_frame(
    ticker: str,
    dates: pd.DatetimeIndex,
    *,
    drift: float,
    amplitude: float,
    crash: float,
    volume_base: int,
) -> pd.DataFrame:
    returns = _returns_pattern(len(dates), drift=drift, amplitude=amplitude, crash=crash)
    growth = np.cumprod(1.0 + returns)
    adj_close = 100.0 * growth
    close = adj_close * (1.0 + 0.0008)
    volume = volume_base + (np.arange(len(dates)) % 23) * 1_000
    return pd.DataFrame(
        {
            "date": dates,
            "ticker": ticker,
            "close": close.round(6),
            "adj_close": adj_close.round(6),
            "volume": volume.astype(float),
            "source": "fixture",
        }
    )


def _write_fixture_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def main() -> int:
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))

    from portfolio_bt.api import compare_portfolios, run_backtest
    from portfolio_bt.models import to_jsonable

    fixtures_root = ROOT / "tests" / "fixtures"
    api_dir = fixtures_root / "api"
    prices_dir = fixtures_root / "prices"
    expected_dir = fixtures_root / "expected"
    for directory in (api_dir, prices_dir, expected_dir):
        directory.mkdir(parents=True, exist_ok=True)

    all_dates = pd.bdate_range("2010-01-01", "2020-12-31")
    frames = {
        "SPY": _build_ticker_frame(
            "SPY",
            all_dates,
            drift=0.00045,
            amplitude=0.0055,
            crash=-0.0055,
            volume_base=4_500_000,
        ),
        "VTI": _build_ticker_frame(
            "VTI",
            all_dates,
            drift=0.00033,
            amplitude=0.0033,
            crash=-0.0100,
            volume_base=3_000_000,
        ),
        "VXUS": _build_ticker_frame(
            "VXUS",
            all_dates[all_dates >= pd.Timestamp("2011-02-01")],
            drift=0.00017,
            amplitude=0.0039,
            crash=-0.0088,
            volume_base=2_200_000,
        ),
        "BND": _build_ticker_frame(
            "BND",
            all_dates,
            drift=0.00010,
            amplitude=0.0010,
            crash=-0.0025,
            volume_base=1_100_000,
        ),
    }

    _write_fixture_frame(prices_dir / "spy_2010_2020.parquet", frames["SPY"])
    _write_fixture_frame(prices_dir / "bond_2010_2020.parquet", frames["BND"])

    three_fund = pd.concat([frames["VTI"], frames["VXUS"], frames["BND"]], ignore_index=True)
    three_fund = three_fund.loc[
        (three_fund["date"] >= "2011-02-01") & (three_fund["date"] <= "2020-12-31")
    ].copy()
    _write_fixture_frame(prices_dir / "three_fund_2011_2020.parquet", three_fund)

    compare_frame = pd.concat(
        [
            frames["SPY"].loc[frames["SPY"]["date"] >= "2011-02-01"],
            frames["VTI"].loc[frames["VTI"]["date"] >= "2011-02-01"],
            frames["VXUS"],
            frames["BND"].loc[frames["BND"]["date"] >= "2011-02-01"],
        ],
        ignore_index=True,
    )
    _write_fixture_frame(prices_dir / "compare_2011_2020.parquet", compare_frame)

    for ticker, frame in frames.items():
        sample = frame.head(5).copy()
        payload = []
        for row in sample.to_dict(orient="records"):
            payload.append(
                {
                    "date": pd.Timestamp(row["date"]).isoformat(),
                    "close": row["close"],
                    "adjClose": row["adj_close"],
                    "volume": row["volume"],
                }
            )
        with (api_dir / f"tiingo_{ticker.lower()}.json").open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    known_answers = {
        "spy_2010_2020": {
            "portfolio": {"SPY": 1.0},
            "start": "2010-01-01",
            "end": "2020-12-31",
            "rebalance": "none",
            "expected": {
                "cagr": {"min": 0.10, "max": 0.16},
                "max_drawdown": {"min": -0.40, "max": -0.25},
                "sharpe_ratio": {"min": 0.50, "max": 1.50},
                "total_return": {"min": 2.00, "max": 4.00},
            },
        },
        "three_fund_2011_2020": {
            "portfolio": {"VTI": 0.60, "VXUS": 0.20, "BND": 0.20},
            "start": "2011-02-01",
            "end": "2020-12-31",
            "rebalance": "annual",
            "expected": {
                "cagr": {"min": 0.05, "max": 0.11},
                "max_drawdown": {"min": -0.35, "max": -0.15},
                "sharpe_ratio": {"min": 0.30, "max": 1.80},
            },
        },
        "bonds_only_2010_2020": {
            "portfolio": {"BND": 1.0},
            "start": "2010-01-01",
            "end": "2020-12-31",
            "rebalance": "none",
            "expected": {
                "cagr": {"min": 0.02, "max": 0.06},
                "max_drawdown": {"min": -0.15, "max": -0.02},
                "sharpe_ratio": {"min": 0.10, "max": 1.80},
            },
        },
    }
    with (expected_dir / "known_answers.json").open("w", encoding="utf-8") as handle:
        json.dump(known_answers, handle, indent=2)

    compare_prices = compare_frame.pivot_table(
        index="date", columns="ticker", values="adj_close", aggfunc="last"
    )
    sample_result = run_backtest(
        compare_prices,
        {"VTI": 0.60, "VXUS": 0.20, "BND": 0.20},
        start="2011-02-01",
        end="2020-12-31",
        rebalance="annual",
        portfolio_name="Three Fund",
    )
    sample_comparison = compare_portfolios(
        compare_prices,
        [
            {"name": "Three Fund", "weights": {"VTI": 0.60, "VXUS": 0.20, "BND": 0.20}},
            {"name": "US Only", "weights": {"VTI": 1.0}},
        ],
        start="2011-02-01",
        end="2020-12-31",
        rebalance="annual",
        benchmark={"SPY": 1.0},
    )
    sample_output = {
        "backtest_result": to_jsonable(sample_result),
        "comparison_result": to_jsonable(sample_comparison),
    }
    with (expected_dir / "sample_output.json").open("w", encoding="utf-8") as handle:
        json.dump(sample_output, handle, indent=2)

    print("Generated deterministic fixtures under tests/fixtures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
