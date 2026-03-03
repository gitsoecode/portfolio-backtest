from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd

from portfolio_bt.errors import CacheError
from portfolio_bt.models import ensure_datetime_index


class CacheStore:
    """Manage local Parquet files plus SQLite cache metadata."""

    def __init__(self, root: str | Path | None = None) -> None:
        cache_root = root or os.getenv("PORTFOLIO_BT_CACHE_DIR") or ".portfolio_bt_cache"
        self.root = Path(cache_root)
        self.prices_dir = self.root / "prices"
        self.db_path = self.root / "cache.sqlite3"
        self.root.mkdir(parents=True, exist_ok=True)
        self.prices_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    ticker TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def price_path(self, ticker: str) -> Path:
        return self.prices_dir / f"{ticker.upper()}.parquet"

    def read_prices(self, ticker: str) -> pd.DataFrame | None:
        path = self.price_path(ticker)
        if not path.exists():
            return None
        try:
            frame = pd.read_parquet(path)
        except Exception as exc:  # pragma: no cover - exercised by tests through public API
            raise CacheError(f"Corrupt cache for {ticker}: {exc}") from exc
        frame = ensure_datetime_index(frame)
        expected_columns = ["close", "adj_close", "volume", "source"]
        missing = [column for column in expected_columns if column not in frame.columns]
        if missing:
            raise CacheError(f"Cached data for {ticker} is missing columns: {', '.join(missing)}")
        return frame.loc[:, [*expected_columns]]

    def write_prices(self, ticker: str, frame: pd.DataFrame) -> Path:
        try:
            cleaned = ensure_datetime_index(frame)
            payload = cleaned.copy().reset_index().rename(columns={"index": "date"})
            path = self.price_path(ticker)
            payload.to_parquet(path, index=False)
            self._write_metadata(ticker.upper(), path, cleaned)
        except Exception as exc:  # pragma: no cover - handled by tests at API level
            raise CacheError(f"Unable to write cache for {ticker}: {exc}") from exc
        return path

    def delete_prices(self, ticker: str) -> None:
        path = self.price_path(ticker)
        if path.exists():
            path.unlink()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("DELETE FROM cache_metadata WHERE ticker = ?", (ticker.upper(),))
            connection.commit()

    def metadata_for(self, ticker: str) -> dict[str, str | int] | None:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT path, row_count, start_date, end_date, updated_at
                FROM cache_metadata
                WHERE ticker = ?
                """,
                (ticker.upper(),),
            ).fetchone()
        if row is None:
            return None
        return {
            "path": row[0],
            "row_count": int(row[1]),
            "start_date": row[2],
            "end_date": row[3],
            "updated_at": row[4],
        }

    def _write_metadata(self, ticker: str, path: Path, frame: pd.DataFrame) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO cache_metadata (
                    ticker, path, row_count, start_date, end_date, updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(ticker) DO UPDATE SET
                    path = excluded.path,
                    row_count = excluded.row_count,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    ticker,
                    str(path),
                    int(len(frame)),
                    frame.index.min().date().isoformat(),
                    frame.index.max().date().isoformat(),
                ),
            )
            connection.commit()
