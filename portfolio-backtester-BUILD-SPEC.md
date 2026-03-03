# Portfolio Backtester - Unified Build and Test Spec

**Author:** Codex (revised from the March 3, 2026 draft docs)  
**Date:** March 3, 2026  
**Status:** Buildable implementation spec  
**Audience:** AI coding agent and human reviewer  

---

## 1. Purpose

Build a local-first portfolio backtesting tool for long-term allocation analysis.

This document combines:

- Product requirements
- Implementation boundaries
- Build contract
- Automated test framework
- Autonomous agent loop

The goal is a spec an AI agent can implement end to end, then iterate against until all required tests and review checks pass.

This is intentionally narrower than the earlier draft. Anything not needed to ship a reliable Phase 1 is deferred.

---

## 2. Product Goal

The system must let the user:

- Backtest stock, ETF, mutual fund, or imported proxy portfolios over a valid shared date range
- Apply scheduled rebalancing (monthly, quarterly, annual)
- Compare multiple portfolios side by side
- Compute core risk metrics
- Export clean charts
- Run fully offline after data is cached

It must run locally on a 2018 Intel Mac Mini with 8 GB RAM.

### Non-Goals for Phase 1

Do not build any of the following in Phase 1:

- Intraday trading
- Order books, slippage models, leverage, margin
- Options, futures, or crypto-specific logic
- Automatic factor modeling
- Automatic pre-inception fund backfilling
- Threshold rebalancing
- Monte Carlo or withdrawal modeling

Those may be added later, but they are not part of the required green build.

---

## 3. Phase 1 Scope

Phase 1 is the minimum shippable product. The AI agent must complete this before attempting any optional expansion.

### Required Features

1. Local data fetch and cache
2. Single-portfolio backtest engine
3. Multi-portfolio comparison for up to 5 portfolios
4. Core metrics
5. Static chart generation
6. Jupyter-friendly API surface
7. Fully automated unit, integration, validation, and UX-contract tests

### Required Outputs

The system must be able to produce:

- A `BacktestResult` dictionary for one portfolio
- A `ComparisonResult` dictionary for multiple portfolios
- PNG chart artifacts
- JSON-serializable metric summaries

### Phase 2 (Optional, Not Required for Green Build)

Only after Phase 1 is green:

- Threshold rebalancing
- Monte Carlo simulation
- Withdrawal modeling
- Streamlit UI
- Saved portfolios

If Phase 2 is attempted, Phase 1 behavior must remain intact.

---

## 4. Data Policy and Historical Range Rules

This is the area most likely to produce misleading results if underspecified. The system must follow these rules exactly.

### Source Policy

- Primary provider: Tiingo (or another explicit API-backed provider with documented access terms)
- Optional fallback: yfinance, used only when the primary provider fails
- Tests must never depend on live API calls
- Provider choice must be isolated behind adapters so the engine is source-agnostic

### Cache Policy

- Price history is cached locally as one Parquet file per ticker
- Cache metadata is stored in SQLite
- Once cached, repeated backtests must not require network access

### Supported Price Field

Use adjusted close as the canonical portfolio pricing input.

Store the following minimum columns when available:

- `date`
- `close`
- `adj_close`
- `volume`
- `source`

The engine uses `adj_close` for return calculations.

### No Silent Backfilling

The engine must never silently invent pre-inception history for a fund.

If the user requests a date before a symbol's available history:

- The engine trims to the true common overlap, if overlap remains
- The engine returns a warning describing the trimmed range
- If no overlap remains, the engine raises a clear `NoOverlapError`

### Proxy Policy

Phase 1 does not auto-map symbols like `VXUS` or `BND` to substitute assets before inception.

If the user wants earlier history, they must provide an explicit imported proxy series under a separate symbol, for example:

- `INTL_PROXY`
- `BOND_PROXY`

Imported proxies are treated exactly like any other ticker once cached.

This avoids fake precision and removes ambiguity from testing.

### Phase 1 Date Guidance

The following symbols are safe examples, not hardcoded rules:

- `SPY`: use windows from 2010 onward in validation fixtures
- `VTI`: use windows after its own trading history begins
- `VXUS`: use windows from 2011 onward in validation fixtures
- `BND`: use windows after its own trading history begins

The default three-fund validation portfolio in this spec uses `2011-02-01` through `2020-12-31` to avoid pre-inception ambiguity.

---

## 5. User Experience Requirements

Even without a full web app, the product must have a clear output contract.

### Required UX Pattern (Phase 1)

The primary user flow is:

1. Load or refresh cached data
2. Define one or more portfolios
3. Run backtest
4. Review metrics summary
5. Review charts
6. Export artifacts if desired

### UX Requirements

- The public API must accept plain Python dictionaries for weights
- Invalid weights must fail with actionable error messages
- Every chart must include a title and axis labels
- Growth charts must clearly identify the starting capital
- Multi-portfolio outputs must preserve the portfolio names the user supplied
- Result dictionaries must use stable field names so notebooks and scripts do not break

### Optional Streamlit UI (Phase 2)

If implemented later, the UI must include:

- Ticker inputs
- Allocation inputs
- Date range inputs
- Rebalance selector
- A visible `Run Backtest` action
- Rendered metric cards or a metrics table
- Rendered charts

The automated UX suite in this spec is written so it can validate Phase 1 output contracts and optionally run shallow UI smoke checks if a web app exists.

---

## 6. Technical Architecture

### Language and Core Libraries

- Python 3.11+
- `pandas`
- `numpy`
- `plotly`
- `requests`
- `pyarrow` for Parquet

`quantstats` may be used, but the core metric formulas must remain understandable and replaceable. Do not make the system dependent on a single external analytics package for correctness.

### Storage

- Parquet for price series
- SQLite for cache metadata

### Runtime

- Local-only execution
- No Docker requirement
- `pip install -e ".[dev]"` must be enough to run the build and tests

### Project Layout

```text
portfolio-bt/
├── pyproject.toml
├── Makefile
├── test_runner.py
├── review_pass.py
├── src/
│   └── portfolio_bt/
│       ├── __init__.py
│       ├── models.py
│       ├── errors.py
│       ├── data/
│       │   ├── __init__.py
│       │   ├── providers.py
│       │   ├── cache.py
│       │   └── fetcher.py
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── allocations.py
│       │   ├── rebalance.py
│       │   └── backtester.py
│       ├── metrics/
│       │   ├── __init__.py
│       │   └── calculator.py
│       ├── viz/
│       │   ├── __init__.py
│       │   └── charts.py
│       └── api.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── api/
│   │   ├── prices/
│   │   └── expected/
│   ├── unit/
│   ├── integration/
│   ├── validation/
│   └── ux/
└── notebooks/
    └── backtest_demo.ipynb
```

---

## 7. Public Interfaces the Agent Must Implement

The test suite will target these interfaces. Their signatures may add optional keyword arguments, but these names and baseline behaviors must exist.

### `fetch_prices`

```python
def fetch_prices(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """
    Return a DataFrame indexed by date.
    Required columns: close, adj_close, volume, source.
    Uses cache by default. Uses provider adapters only when cache miss or refresh.
    """
```

### `run_backtest`

```python
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
    """
    Run a long-only backtest over the shared date range.
    Supported rebalance values in Phase 1: none, monthly, quarterly, annual.
    """
```

### `compare_portfolios`

```python
def compare_portfolios(
    prices: pd.DataFrame,
    portfolios: list[dict],
    *,
    start: str | None = None,
    end: str | None = None,
    rebalance: str = "quarterly",
    initial_capital: float = 10_000.0,
    benchmark: dict[str, float] | None = None,
) -> dict:
    """
    Run multiple named portfolio backtests and return a comparison bundle.
    Each portfolio dict contains: {"name": str, "weights": dict[str, float]}.
    """
```

### `render_chart`

```python
def render_chart(
    chart_type: str,
    result: dict,
    *,
    output_path: str | None = None,
):
    """
    Supported chart types in Phase 1:
    growth, drawdown, annual_returns, comparison
    Returns a Plotly figure. If output_path is provided, writes a PNG.
    """
```

### Result Schema Contract

Every single-portfolio result must include:

```python
{
    "portfolio_name": str,
    "weights": dict[str, float],
    "date_range": {"requested_start": str | None, "requested_end": str | None,
                   "actual_start": str, "actual_end": str},
    "warnings": list[str],
    "daily_returns": pd.Series,
    "growth_series": pd.Series,
    "drawdown_series": pd.Series,
    "metrics": {
        "cagr": float,
        "total_return": float,
        "annualized_volatility": float,
        "sharpe_ratio": float,
        "sortino_ratio": float,
        "max_drawdown": float,
        "best_year": {"year": int, "return": float},
        "worst_year": {"year": int, "return": float},
    },
}
```

All metric values must be decimal fractions, not percentages:

- `0.12` means 12%
- `-0.35` means -35%

This rule removes ambiguity in tests.

### Comparison Schema Contract

`compare_portfolios` must return:

```python
{
    "portfolios": list[dict],   # each item is a BacktestResult-like summary
    "benchmark": dict | None,
    "comparison_table": list[dict],  # rows of JSON-serializable metrics
}
```

---

## 8. Backtesting Rules

### Allocation Rules

- Weights must sum to 1.0 within a tolerance of `1e-6`
- Negative weights are not allowed in Phase 1
- Empty portfolios are not allowed

### Date Alignment Rules

- The engine must use the intersection of all selected series
- If the usable range is trimmed by more than 20 trading days relative to the requested range, append a warning
- If no overlapping date range remains, raise `NoOverlapError`
- One-day market holidays are acceptable and should be handled by ordinary index alignment, not by ad hoc date invention

### Rebalancing Rules

Phase 1 supports:

- `none`
- `monthly`
- `quarterly`
- `annual`

Rebalancing occurs at the first available trading day of the target period.

Threshold rebalancing is intentionally excluded from Phase 1 because it adds statefulness and drift semantics that are harder to validate cleanly.

### Transaction Cost Rules

- `fee_bps` is applied only when a rebalance creates turnover
- If `rebalance="none"`, transaction cost impact after the initial allocation is zero
- Transaction costs must reduce, not increase, ending value

---

## 9. Metrics Rules

The agent must implement these directly or through a wrapped library with matching behavior.

### Required Metrics

- CAGR
- Total return
- Annualized volatility
- Sharpe ratio
- Sortino ratio
- Maximum drawdown
- Best year
- Worst year

### Formula Conventions

- Use 252 trading days for annualization
- Default risk-free rate is `0.0` in Phase 1 unless explicitly passed
- Sharpe and Sortino may return `0.0` when the denominator is zero; do not emit `inf`
- Maximum drawdown must always be `<= 0.0`

### Numerical Stability Rules

- No `NaN` or `inf` values in user-facing metrics
- Convert NumPy scalars to plain Python types before returning JSON-ready output

---

## 10. Charts

### Required Charts

1. Growth of initial capital
2. Drawdown
3. Annual returns
4. Multi-portfolio comparison growth chart

### Chart Contract

Every chart must:

- Render without exceptions
- Have a non-empty title
- Have labeled x and y axes
- Match the result date range
- Be exportable to PNG through Plotly + Kaleido

The chart tests are structural. They do not use pixel diffs.

---

## 11. Build Sequence

The AI agent must implement the project in this order:

1. Core models and error types
2. Cache layer
3. Provider adapters
4. `fetch_prices`
5. Allocation validation
6. Rebalance schedule logic
7. `run_backtest`
8. Metrics calculator
9. Chart rendering
10. `compare_portfolios`
11. Test harness scripts
12. Notebook example

Do not start optional Phase 2 features until `make full` is green for Phase 1.

---

## 12. Test Strategy

The test suite is part of the product contract. The build is not complete until the tests and review pass.

### Test Suite Categories

- `unit`: pure logic and isolated adapter behavior
- `integration`: multi-module flows using fixtures
- `validation`: known-answer and sane-range checks
- `ux`: output contract and optional UI smoke checks

### Test Principles

1. No live API calls in tests
2. Stable fixtures checked into the repo
3. JSON-serializable outputs
4. Explicit failure messages with expected vs actual values
5. Test commands must not mutate source files

---

## 13. Test Fixtures

### Fixture Directory Layout

```text
tests/fixtures/
├── api/
│   ├── tiingo_vti.json
│   ├── tiingo_vxus.json
│   ├── tiingo_bnd.json
│   └── tiingo_spy.json
├── prices/
│   ├── three_fund_2011_2020.parquet
│   ├── spy_2010_2020.parquet
│   ├── bond_2010_2020.parquet
│   └── compare_2011_2020.parquet
└── expected/
    ├── known_answers.json
    └── sample_output.json
```

### Fixture Rules

- `three_fund_2011_2020.parquet` must contain only `VTI`, `VXUS`, and `BND`
- Benchmark-only fixtures must be stored separately
- All expected-output directories must be created explicitly by fixture-generation code
- Fixture generation is a manual command, not part of test execution

### Fixture Generation Script Contract

The repo may include a `generate_fixtures.py` helper, but it must:

- create `tests/fixtures/api`, `tests/fixtures/prices`, and `tests/fixtures/expected`
- fetch each ticker once per run and reuse that response in memory
- write only the intended columns to each file
- not combine `SPY` into the three-fund parquet
- never run during CI unless explicitly requested

---

## 14. Validation Scenarios

These scenarios replace the earlier brittle date windows.

### Known-Answer Scenarios

The exact values may vary by provider. The tests use generous ranges.

```python
KNOWN_ANSWERS = {
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
            "sharpe_ratio": {"min": 0.30, "max": 1.20},
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
            "sharpe_ratio": {"min": 0.10, "max": 1.20},
        },
    },
}
```

### Sanity Bounds

These catch obviously broken implementations:

```python
BOUNDS = {
    "cagr": (-0.50, 0.50),
    "total_return": (-0.99, 10.0),
    "annualized_volatility": (0.0, 1.0),
    "sharpe_ratio": (-5.0, 5.0),
    "sortino_ratio": (-5.0, 10.0),
    "max_drawdown": (-1.0, 0.0),
}
```

### UX Contract Checks

The automated UX suite must verify:

- Result dictionaries contain the required top-level keys
- Metric keys are stable and named exactly as specified
- Charts have titles and axis labels
- Portfolio names are preserved in comparison outputs
- If a Streamlit app exists, the home page loads and contains `Run Backtest`

---

## 15. Required Test Files

The agent must create these test modules.

### Unit

- `tests/unit/test_fetcher.py`
- `tests/unit/test_allocations.py`
- `tests/unit/test_rebalance.py`
- `tests/unit/test_backtester.py`
- `tests/unit/test_metrics.py`
- `tests/unit/test_charts.py`

### Integration

- `tests/integration/test_single_portfolio_flow.py`
- `tests/integration/test_multi_portfolio_flow.py`
- `tests/integration/test_cache_refresh_flow.py`

### Validation

- `tests/validation/test_known_answers.py`
- `tests/validation/test_sanity_bounds.py`

### UX

- `tests/ux/test_output_contract.py`
- `tests/ux/test_streamlit_smoke.py` (skip cleanly if no UI app exists)

---

## 16. Minimal Test Expectations

The tests should assert the following at minimum.

### Fetcher

- Cache hit does not call the provider adapter
- Cache miss writes Parquet and metadata
- Refresh appends only new rows
- Corrupt Parquet triggers a re-fetch
- Provider failure raises a typed exception
- Fallback provider is used only after primary failure

### Engine

- Weight validation rejects negative or non-summing allocations
- Shared date range uses intersection
- Monthly, quarterly, and annual schedules land on the first trading day of the period
- Different rebalance schedules can produce different outputs
- Fees reduce returns when turnover occurs

### Metrics

- Constant positive returns yield positive CAGR
- Zero-return series yields zero CAGR and zero volatility
- Drawdown on a known price path matches the expected value
- No metric emits `NaN` or `inf`

### Charts

- Chart rendering returns a figure object
- PNG export creates a non-trivial file
- Titles and axis labels are present

### Output Contract

- Result objects are convertible to JSON after serialization helpers run
- Comparison tables contain one row per named portfolio
- Warnings are always a list, even if empty

---

## 17. Buildable Test Runner Contract

`test_runner.py` is the machine-readable entry point for the agent.

It must:

- run suites independently
- collect pass/fail/error counts
- collect node IDs and source locations
- print one final line prefixed with `TEST_REPORT_JSON:`
- use stable exit codes

### Exit Codes

- `0`: all suites passed
- `1`: one or more test failures
- `2`: one or more test errors (import errors, setup errors, syntax issues)

### Reference Implementation Pattern

This pattern is preferred because it avoids brittle XML parsing:

```python
#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field

import pytest


@dataclass
class SuiteCollector:
    passed: int = 0
    skipped: int = 0
    failures: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.passed:
            self.passed += 1
            return
        if report.skipped and report.when == "call":
            self.skipped += 1
            return

        if not report.failed:
            return

        path, line, _ = report.location
        payload = {
            "test": report.nodeid,
            "file": path,
            "line": line + 1,
            "message": str(report.longrepr)[:800],
        }

        if report.when == "call":
            self.failures.append(payload)
        else:
            self.errors.append(payload)


def run_suite(label: str, path: str) -> dict:
    collector = SuiteCollector()
    code = pytest.main([path, "-q", "--tb=short"], plugins=[collector])
    failed = len(collector.failures)
    errors = len(collector.errors)
    return {
        "exit_code": int(code),
        "passed": collector.passed,
        "failed": failed,
        "errors": errors,
        "skipped": collector.skipped,
        "failures": collector.failures,
        "error_details": collector.errors,
    }


def main() -> int:
    suites = {
        "unit": "tests/unit",
        "integration": "tests/integration",
        "validation": "tests/validation",
        "ux": "tests/ux",
    }

    selected = suites
    if len(sys.argv) == 2 and sys.argv[1] in {"unit", "integration", "validation", "ux"}:
        selected = {sys.argv[1]: suites[sys.argv[1]]}

    started = time.time()
    totals = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    suite_results = {}
    all_failures = []
    all_errors = []

    for label, path in selected.items():
        result = run_suite(label, path)
        suite_results[label] = {
            "passed": result["passed"],
            "failed": result["failed"],
            "errors": result["errors"],
            "skipped": result["skipped"],
        }
        totals["passed"] += result["passed"]
        totals["failed"] += result["failed"]
        totals["errors"] += result["errors"]
        totals["skipped"] += result["skipped"]
        all_failures.extend(result["failures"])
        all_errors.extend(result["error_details"])

    report = {
        **totals,
        "failures": all_failures,
        "error_details": all_errors,
        "duration_seconds": round(time.time() - started, 2),
        "suite_results": suite_results,
    }
    print("TEST_REPORT_JSON:" + json.dumps(report))

    if totals["errors"] > 0:
        return 2
    if totals["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 18. Buildable Review Pass Contract

`review_pass.py` is the second machine-readable entry point. It is not a placeholder.

It must:

- run a fixed set of scenario backtests from fixtures
- validate metric ranges
- render required charts
- write review artifacts
- print one final line prefixed with `REVIEW_REPORT_JSON:`

### Exit Codes

- `0`: review checks all passed
- `1`: one or more review checks failed

### Required Review Checks

- Metric ranges for all known-answer scenarios
- Chart export success for each required chart
- No `NaN` or `inf` anywhere in metrics
- Output schema matches the required contract
- Comparison output preserves portfolio names

### Review Artifact Output

```text
review_outputs/
├── charts/
└── reports/
```

`review_pass.py` must create these directories before writing files.

### Review Logic Guidance

The implementation should:

1. Load fixture prices
2. Run `run_backtest` or `compare_portfolios`
3. Check each expected metric range
4. Render PNG charts to `review_outputs/charts`
5. Write a JSON report to `review_outputs/reports/review_report.json`
6. Print `REVIEW_REPORT_JSON:{...}`

The script must use real outputs, not placeholder values.

---

## 19. Makefile Contract

The Makefile is the command contract. Test commands must not auto-fix source code.

### Required Targets

```makefile
PYTHON := python3

.PHONY: lint-check lint-fix typecheck test review full unit integration validation ux

lint-check:
	$(PYTHON) -m ruff check src tests

lint-fix:
	$(PYTHON) -m ruff check src tests --fix

typecheck:
	$(PYTHON) -m mypy src --ignore-missing-imports

test: lint-check typecheck
	$(PYTHON) test_runner.py

unit:
	$(PYTHON) test_runner.py unit

integration:
	$(PYTHON) test_runner.py integration

validation:
	$(PYTHON) test_runner.py validation

ux:
	$(PYTHON) test_runner.py ux

review:
	$(PYTHON) review_pass.py

full: test review
```

### Makefile Rules

- `test` is read-only with respect to source code
- `lint-fix` is explicit and never chained into `test`
- `full` means `test` plus `review`

---

## 20. CI Contract

CI should run the same commands the agent runs locally.

### Required CI Steps

1. Install dependencies
2. `make test`
3. `make review`
4. Upload review artifacts if a step fails

The CI workflow must not use a different hidden test command path than local development.

---

## 21. Dependencies

The minimum dev extras should include:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-timeout>=2.3",
    "ruff>=0.4",
    "mypy>=1.10",
    "pandas>=2.0",
    "numpy>=1.26",
    "plotly>=5.0",
    "kaleido>=0.2.1",
    "requests>=2.31",
    "pyarrow>=15.0",
]
```

If a Streamlit UI is added in Phase 2, `streamlit` becomes an explicit dependency and the UX smoke test may check that `http://127.0.0.1:8501/` loads and contains `Run Backtest`.

---

## 22. Agent Workflow

This is the required autonomous loop.

### Phase 1: Build

1. Read this spec
2. Create the project structure
3. Implement the required interfaces in the prescribed order
4. Create fixtures and tests

### Phase 2: Test Loop

Run:

```bash
make test
```

Read the final line beginning with `TEST_REPORT_JSON:`.

Decision rules:

- If `errors > 0`, fix import errors, syntax errors, setup failures, or broken fixtures first
- Else if `failed > 0`, fix logic failures
- Re-run `make test`
- Repeat until `failed == 0` and `errors == 0`

### Phase 3: Review Loop

Run:

```bash
make review
```

Read the final line beginning with `REVIEW_REPORT_JSON:`.

Decision rules:

- If any check failed, fix the implementation or fixture expectation
- Re-run `make review`
- Repeat until all review checks pass

### Phase 4: Final Verification

Run:

```bash
make full
```

The build is complete only when:

- `make test` exits `0`
- `make review` exits `0`

### Agent Constraints

- Do not edit tests merely to silence valid failures
- It is acceptable to update fixtures only when the fixture itself is wrong or incomplete
- Do not expand scope before Phase 1 is green
- Do not introduce automatic proxy mapping in order to make earlier date tests pass

---

## 23. Acceptance Criteria

The Phase 1 implementation is accepted when all of the following are true:

1. The required interfaces exist and match the contract in this file
2. The system can backtest at least the known-answer scenarios in this file using local fixtures
3. All tests pass through `make test`
4. All review checks pass through `make review`
5. Charts export to PNG
6. Result objects are JSON-serializable after serialization helpers run
7. No test or review command depends on a live network call

---

## 24. Explicit Deferrals

These are intentionally excluded from the green build so the agent does not drift:

- Threshold rebalancing
- Monte Carlo
- Retirement withdrawal simulation
- Factor analysis
- Efficient frontier
- Saved portfolios
- Automatic proxy inference

If any of these are added later, they must be introduced behind new tests without weakening the Phase 1 contract.

---

## 25. First Deliverable

The first deliverable is not a polished UI. It is:

- a working Python package
- a notebook-ready API
- a repeatable local test harness
- a green `make full`

That is the correct stopping point for the initial build.

---

## 26. Summary for the Agent

Build the narrow version first:

- cache
- backtest
- compare
- metrics
- charts
- tests
- review loop

Keep the date rules honest, do not fabricate history, keep outputs stable, and treat `make full` as the completion gate.
