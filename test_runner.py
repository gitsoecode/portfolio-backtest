#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field

import pytest


@dataclass(eq=False)
class SuiteCollector:
    passed: int = 0
    skipped: int = 0
    failures: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def pytest_runtest_logreport(self, report) -> None:
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


def run_suite(path: str) -> dict:
    collector = SuiteCollector()
    code = pytest.main([path, "-q", "--tb=short"], plugins=[collector])
    exit_code = int(code)
    if exit_code not in {0, 1, 5} and not collector.errors:
        collector.errors.append(
            {
                "test": path,
                "file": path,
                "line": 1,
                "message": f"pytest exited with internal error code {exit_code}",
            }
        )
    return {
        "exit_code": exit_code,
        "passed": collector.passed,
        "failed": len(collector.failures),
        "errors": len(collector.errors),
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
    if len(sys.argv) == 2 and sys.argv[1] in suites:
        selected = {sys.argv[1]: suites[sys.argv[1]]}

    started = time.time()
    totals = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    suite_results = {}
    failures: list[dict] = []
    errors: list[dict] = []

    for label, path in selected.items():
        result = run_suite(path)
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
        failures.extend(result["failures"])
        errors.extend(result["error_details"])

    report = {
        **totals,
        "failures": failures,
        "error_details": errors,
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
