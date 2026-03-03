from __future__ import annotations

from portfolio_bt.api import compare_portfolios


def test_multi_portfolio_flow_preserves_names(compare_price_matrix):
    result = compare_portfolios(
        compare_price_matrix,
        [
            {"name": "Growth", "weights": {"VTI": 0.70, "VXUS": 0.20, "BND": 0.10}},
            {"name": "Balanced", "weights": {"VTI": 0.50, "VXUS": 0.20, "BND": 0.30}},
        ],
        benchmark={"SPY": 1.0},
    )
    assert [item["portfolio_name"] for item in result["portfolios"]] == ["Growth", "Balanced"]
    assert [row["portfolio_name"] for row in result["comparison_table"]] == ["Growth", "Balanced"]
    assert result["benchmark"]["portfolio_name"] == "Benchmark"
