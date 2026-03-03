#!/usr/bin/env python3

from __future__ import annotations

import json
import math
from pathlib import Path

from tests.helpers import load_expected_json, load_price_fixture, pivot_adj_close

from portfolio_bt.api import compare_portfolios
from portfolio_bt.engine.backtester import run_backtest
from portfolio_bt.models import REQUIRED_RESULT_KEYS, to_jsonable
from portfolio_bt.viz.charts import render_chart


def _check_metric_ranges(failures: list[str]) -> None:
    known_answers = load_expected_json("known_answers")
    fixture_map = {
        "spy_2010_2020": "spy_2010_2020",
        "three_fund_2011_2020": "three_fund_2011_2020",
        "bonds_only_2010_2020": "bond_2010_2020",
    }
    for scenario_name, scenario in known_answers.items():
        matrix = pivot_adj_close(load_price_fixture(fixture_map[scenario_name]))
        result = run_backtest(
            matrix,
            scenario["portfolio"],
            start=scenario["start"],
            end=scenario["end"],
            rebalance=scenario["rebalance"],
            portfolio_name=scenario_name,
        )
        if tuple(result.keys()) != REQUIRED_RESULT_KEYS:
            failures.append(
                f"{scenario_name}: output schema keys do not match the required contract."
            )
        for metric_name, bounds in scenario["expected"].items():
            actual = float(result["metrics"][metric_name])
            if not bounds["min"] <= actual <= bounds["max"]:
                failures.append(
                    f"{scenario_name}: {metric_name} expected between {bounds['min']} and "
                    f"{bounds['max']}, received {actual}."
                )
        for metric_name, value in result["metrics"].items():
            if isinstance(value, dict):
                continue
            if math.isnan(value) or math.isinf(value):
                failures.append(f"{scenario_name}: {metric_name} contains NaN or inf.")


def _check_comparison_output(failures: list[str], charts_dir: Path) -> dict:
    matrix = pivot_adj_close(load_price_fixture("compare_2011_2020"))
    comparison = compare_portfolios(
        matrix,
        [
            {"name": "Growth", "weights": {"VTI": 0.70, "VXUS": 0.20, "BND": 0.10}},
            {"name": "Balanced", "weights": {"VTI": 0.50, "VXUS": 0.20, "BND": 0.30}},
        ],
        benchmark={"SPY": 1.0},
    )
    names = [item["portfolio_name"] for item in comparison["portfolios"]]
    if names != ["Growth", "Balanced"]:
        failures.append("Comparison output does not preserve the supplied portfolio names.")
    chart_map = {
        "growth": comparison["portfolios"][0],
        "drawdown": comparison["portfolios"][0],
        "annual_returns": comparison["portfolios"][0],
        "comparison": comparison,
    }
    for chart_type, payload in chart_map.items():
        destination = charts_dir / f"{chart_type}.png"
        try:
            render_chart(chart_type, payload, output_path=str(destination))
        except Exception as exc:
            failures.append(f"Failed to render {chart_type} chart: {exc}")
            continue
        if not destination.exists() or destination.stat().st_size <= 1_000:
            failures.append(f"{chart_type} chart export did not create a non-trivial PNG artifact.")
    return comparison


def main() -> int:
    review_root = Path("review_outputs")
    charts_dir = review_root / "charts"
    reports_dir = review_root / "reports"
    charts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    _check_metric_ranges(failures)
    comparison = _check_comparison_output(failures, charts_dir)

    report = {
        "passed": len(failures) == 0,
        "failure_count": len(failures),
        "failures": failures,
        "artifacts": {
            "charts": str(charts_dir),
            "report": str(reports_dir / "review_report.json"),
        },
        "comparison_preview": to_jsonable(comparison["comparison_table"]),
    }

    with (reports_dir / "review_report.json").open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    print("REVIEW_REPORT_JSON:" + json.dumps(report))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
