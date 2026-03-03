from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def load_price_fixture(name: str) -> pd.DataFrame:
    return pd.read_parquet(FIXTURES / "prices" / f"{name}.parquet")


def load_expected_json(name: str) -> Any:
    with (FIXTURES / "expected" / f"{name}.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_api_fixture(name: str) -> list[dict[str, Any]]:
    with (FIXTURES / "api" / f"{name}.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def pivot_adj_close(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"])
    return working.pivot_table(
        index="date", columns="ticker", values="adj_close", aggfunc="last"
    ).sort_index()
