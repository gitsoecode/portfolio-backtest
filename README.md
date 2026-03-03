# Portfolio Backtester

`portfolio-backtest` is a local-first Python package for long-term allocation backtesting.
It is designed to cache price data locally, run single or multi-portfolio backtests, compute
core risk metrics, and export static charts.

## What It Includes

- Local Parquet cache plus SQLite cache metadata
- Provider adapters for a primary API-backed source and an explicit fallback path
- A notebook-friendly Python API
- A deterministic fixture generator so tests never depend on live APIs
- Unit, integration, validation, and UX-contract tests
- Machine-readable `test_runner.py` and `review_pass.py` entrypoints

## Quick Start

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/generate_fixtures.py
make full
```

## Public API

```python
from portfolio_bt.api import compare_portfolios, fetch_prices, render_chart, run_backtest
```

The package accepts plain Python dictionaries for weights, preserves the portfolio names you
provide, and returns stable result schemas for scripts and notebooks.

## Data and Privacy

- Runtime cache is local-only and stored under `.portfolio_bt_cache/` by default
- Tests use checked-in deterministic fixtures and do not make live network calls
- `.env`, caches, and review artifacts are ignored by Git to reduce accidental leakage

## License

This repository is released under the MIT License so others can fork, use, and extend it.

