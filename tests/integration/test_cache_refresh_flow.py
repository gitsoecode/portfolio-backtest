from __future__ import annotations

import pandas as pd

from portfolio_bt.data.fetcher import fetch_prices
from portfolio_bt.data.providers import StaticPriceProvider


def test_cache_refresh_flow(cache_store):
    dates = pd.bdate_range("2020-01-01", periods=5)
    initial = pd.DataFrame(
        {
            "date": dates[:3],
            "close": [100.0, 101.0, 102.0],
            "adj_close": [100.0, 101.0, 102.0],
            "volume": [1_000.0, 1_000.0, 1_000.0],
            "source": ["fixture", "fixture", "fixture"],
        }
    )
    full = pd.DataFrame(
        {
            "date": dates,
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "adj_close": [100.0, 101.0, 102.0, 103.0, 104.0],
            "volume": [1_000.0] * 5,
            "source": ["fixture"] * 5,
        }
    )
    fetch_prices("SPY", cache=cache_store, provider=StaticPriceProvider({"SPY": initial}))
    refreshed = fetch_prices(
        "SPY", cache=cache_store, provider=StaticPriceProvider({"SPY": full}), refresh=True
    )
    assert len(refreshed) == 5
    assert float(refreshed.iloc[-1]["adj_close"]) == 104.0
