from __future__ import annotations

import pandas as pd

from portfolio_bt.data.cache import CacheStore
from portfolio_bt.data.providers import PriceProvider, TiingoProvider, YahooFinanceProvider
from portfolio_bt.errors import CacheError, ProviderError
from portfolio_bt.models import ensure_datetime_index, slice_frame


def _normalize_provider_frame(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    cleaned = ensure_datetime_index(frame)
    required_columns = ["close", "adj_close", "volume", "source"]
    missing = [column for column in required_columns if column not in cleaned.columns]
    if missing:
        raise ProviderError(
            f"Provider response for {ticker} is missing columns: {', '.join(sorted(missing))}"
        )
    return cleaned.loc[:, required_columns]


def _fetch_from_provider_chain(
    ticker: str,
    start: str | None,
    end: str | None,
    provider: PriceProvider,
    fallback_provider: PriceProvider | None,
) -> pd.DataFrame:
    try:
        return _normalize_provider_frame(
            provider.fetch_price_history(ticker, start=start, end=end), ticker
        )
    except ProviderError:
        if fallback_provider is None:
            raise
    return _normalize_provider_frame(
        fallback_provider.fetch_price_history(ticker, start=start, end=end),
        ticker,
    )


def fetch_prices(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    refresh: bool = False,
    *,
    cache: CacheStore | None = None,
    provider: PriceProvider | None = None,
    fallback_provider: PriceProvider | None = None,
) -> pd.DataFrame:
    """Return cached or freshly fetched prices for one ticker."""
    normalized = ticker.upper().strip()
    if not normalized:
        raise ProviderError("Ticker must be a non-empty string.")

    cache_store = cache or CacheStore()
    primary_provider = provider or TiingoProvider()
    secondary_provider = (
        fallback_provider if fallback_provider is not None else YahooFinanceProvider()
    )

    cached: pd.DataFrame | None
    try:
        cached = cache_store.read_prices(normalized)
    except CacheError:
        cache_store.delete_prices(normalized)
        cached = None

    if cached is not None and not refresh:
        return slice_frame(cached, start=start, end=end)

    if cached is not None and refresh and not cached.empty:
        next_start = (cached.index.max() + pd.offsets.BDay(1)).date().isoformat()
        incremental_start = max(start, next_start) if start is not None else next_start
        fetched = _fetch_from_provider_chain(
            normalized,
            start=incremental_start,
            end=end,
            provider=primary_provider,
            fallback_provider=secondary_provider,
        )
        merged = pd.concat([cached, fetched]).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        cache_store.write_prices(normalized, merged)
        return slice_frame(merged, start=start, end=end)

    fetched = _fetch_from_provider_chain(
        normalized,
        start=start,
        end=end,
        provider=primary_provider,
        fallback_provider=secondary_provider,
    )
    cache_store.write_prices(normalized, fetched)
    return slice_frame(fetched, start=start, end=end)
