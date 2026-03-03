from __future__ import annotations

import pandas as pd
import pytest

from portfolio_bt.data.fetcher import fetch_prices
from portfolio_bt.data.providers import FailingProvider, StaticPriceProvider
from portfolio_bt.errors import ProviderError


def _sample_frame(periods: int = 5) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=periods)
    prices = [100.0 + float(index) for index in range(periods)]
    return pd.DataFrame(
        {
            "date": dates,
            "close": prices,
            "adj_close": prices,
            "volume": [1_000.0] * periods,
            "source": ["fixture"] * periods,
        }
    )


def test_cache_hit_does_not_call_provider(cache_store):
    frame = _sample_frame()
    cache_store.write_prices("SPY", frame)
    result = fetch_prices("SPY", cache=cache_store, provider=FailingProvider("should not be used"))
    assert len(result) == len(frame)


def test_cache_miss_writes_parquet_and_metadata(cache_store):
    frame = _sample_frame()
    provider = StaticPriceProvider({"SPY": frame})
    result = fetch_prices("SPY", cache=cache_store, provider=provider, fallback_provider=None)
    assert len(result) == len(frame)
    assert cache_store.price_path("SPY").exists()
    metadata = cache_store.metadata_for("SPY")
    assert metadata is not None
    assert metadata["row_count"] == len(frame)


def test_refresh_appends_only_new_rows(cache_store):
    initial = _sample_frame(periods=3)
    cache_store.write_prices("SPY", initial)
    provider = StaticPriceProvider({"SPY": _sample_frame(periods=5)})
    result = fetch_prices("SPY", cache=cache_store, provider=provider, refresh=True)
    assert len(result) == 5
    assert provider.calls[0]["start"] == "2020-01-06"


def test_corrupt_parquet_triggers_refetch(cache_store):
    cache_store.price_path("SPY").write_text("not a parquet", encoding="utf-8")
    provider = StaticPriceProvider({"SPY": _sample_frame()})
    result = fetch_prices("SPY", cache=cache_store, provider=provider)
    assert len(result) == 5
    assert provider.calls


def test_provider_failure_raises_typed_exception(cache_store):
    with pytest.raises(ProviderError):
        fetch_prices(
            "SPY",
            cache=cache_store,
            provider=FailingProvider("primary failed"),
            fallback_provider=FailingProvider("fallback failed"),
        )


def test_fallback_provider_is_used_only_after_primary_failure(cache_store):
    fallback = StaticPriceProvider({"SPY": _sample_frame()})
    result = fetch_prices(
        "SPY",
        cache=cache_store,
        provider=FailingProvider("primary failed"),
        fallback_provider=fallback,
    )
    assert len(result) == 5
    assert len(fallback.calls) == 1
