from __future__ import annotations

import os
from typing import Protocol

import pandas as pd
import requests  # type: ignore[import-untyped]

from portfolio_bt.errors import ProviderError
from portfolio_bt.models import ensure_datetime_index, slice_frame

REQUIRED_PROVIDER_COLUMNS = ("close", "adj_close", "volume", "source")


class PriceProvider(Protocol):
    def fetch_price_history(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """Return daily prices for one ticker."""


class TiingoProvider:
    """Primary live provider adapter."""

    def __init__(self, api_key: str | None = None, session: requests.Session | None = None) -> None:
        self.api_key = api_key or os.getenv("TIINGO_API_KEY")
        self.session = session or requests.Session()

    def fetch_price_history(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        if not self.api_key:
            raise ProviderError("TIINGO_API_KEY is not configured for live fetches.")
        url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
        params = {
            "startDate": start,
            "endDate": end,
            "resampleFreq": "daily",
            "token": self.api_key,
        }
        response = self.session.get(url, params={k: v for k, v in params.items() if v}, timeout=30)
        if response.status_code >= 400:
            raise ProviderError(f"Tiingo request failed with status {response.status_code}.")
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise ProviderError(f"Tiingo returned no data for {ticker}.")
        rows = []
        for entry in payload:
            rows.append(
                {
                    "date": entry["date"],
                    "close": float(entry.get("close", entry.get("adjClose", 0.0))),
                    "adj_close": float(entry.get("adjClose", entry.get("close", 0.0))),
                    "volume": float(entry.get("volume", 0.0)),
                    "source": "tiingo",
                }
            )
        return ensure_datetime_index(pd.DataFrame(rows))


class YahooFinanceProvider:
    """Explicit fallback placeholder.

    The fallback exists so the fetcher can retry a secondary provider path, but live tests
    never call it and the default implementation stays conservative.
    """

    def fetch_price_history(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        raise ProviderError(
            f"No fallback provider is configured for {ticker}. Inject a custom fallback adapter."
        )


class StaticPriceProvider:
    """Deterministic in-memory provider used by tests and fixture generation."""

    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = {
            ticker.upper(): ensure_datetime_index(frame) for ticker, frame in frames.items()
        }
        self.calls: list[dict[str, str | None]] = []

    def fetch_price_history(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        normalized = ticker.upper()
        if normalized not in self.frames:
            raise ProviderError(f"No static fixture data is available for {ticker}.")
        self.calls.append({"ticker": normalized, "start": start, "end": end})
        return slice_frame(self.frames[normalized], start=start, end=end)


class FailingProvider:
    """Test helper for explicit provider failures."""

    def __init__(self, message: str = "Provider failed.") -> None:
        self.message = message
        self.calls = 0

    def fetch_price_history(
        self,
        ticker: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        _ = (ticker, start, end)
        self.calls += 1
        raise ProviderError(self.message)
