from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from portfolio_bt.api import compare_portfolios, fetch_prices, render_chart, run_backtest
from portfolio_bt.metrics.calculator import annual_returns_series
from portfolio_bt.models import to_jsonable

FIXTURE_PATH = Path("tests/fixtures/prices/compare_2011_2020.parquet")
DEFAULT_TICKERS = ("SPY", "VTI", "VXUS", "BND")
DEFAULT_WEIGHTS = {"SPY": 40.0, "VTI": 25.0, "VXUS": 20.0, "BND": 15.0}
DEFAULT_ALT_WEIGHTS = {"VTI": 60.0, "BND": 40.0}
REBALANCE_OPTIONS = ("none", "monthly", "quarterly", "annual")
WEIGHT_TOLERANCE = 0.25


@st.cache_data
def load_fixture_prices() -> pd.DataFrame:
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(
            "Fixture data is missing. Run `python scripts/generate_fixtures.py` first."
        )
    prices = pd.read_parquet(FIXTURE_PATH)
    prices["date"] = pd.to_datetime(prices["date"])
    return prices


def fixture_universe() -> list[str]:
    prices = load_fixture_prices()
    return sorted({str(value) for value in prices["ticker"].unique()})


def build_price_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pivot_table(
        index="date",
        columns="ticker",
        values="adj_close",
        aggfunc="last",
    ).sort_index()


def collect_weight_inputs(
    tickers: list[str],
    *,
    state_prefix: str,
    presets: dict[str, float] | None = None,
    label_prefix: str = "",
) -> dict[str, float]:
    inputs: dict[str, float] = {}
    presets = presets or {}
    if not tickers:
        return inputs

    columns = st.columns(3)
    for index, ticker in enumerate(tickers):
        default_value = float(presets.get(ticker, 0.0))
        with columns[index % 3]:
            inputs[ticker] = st.number_input(
                f"{label_prefix}{ticker} (%)",
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                value=default_value,
                key=f"{state_prefix}_{ticker}",
            )
    return inputs


def weight_state(raw_weights: dict[str, float]) -> dict:
    positive = {ticker: value for ticker, value in raw_weights.items() if value > 0}
    total = round(sum(raw_weights.values()), 2)
    delta = round(100.0 - total, 2)
    valid = bool(positive) and abs(delta) <= WEIGHT_TOLERANCE
    fractions: dict[str, float] = {}
    if positive and total > 0:
        fractions = {ticker: round(value / total, 6) for ticker, value in positive.items()}
    return {
        "positive": positive,
        "total": total,
        "delta": delta,
        "valid": valid,
        "fractions": fractions,
    }


def weight_status_copy(total: float, delta: float, valid: bool) -> tuple[str, str]:
    if not total:
        return "No weights entered yet.", "Set one or more weights and make the total 100%."
    if valid:
        return "Weight total is valid.", f"Current total: {total:.2f}%"
    if delta > 0:
        return "Portfolio is underweight.", f"Add {abs(delta):.2f}% to reach 100%."
    return "Portfolio is overweight.", f"Remove {abs(delta):.2f}% to reach 100%."


def render_status_band(title: str, total: float, valid: bool, delta: float) -> None:
    headline, detail = weight_status_copy(total, delta, valid)
    status_class = "status-ok" if valid else "status-bad"
    st.markdown(
        f"""
        <div class="status-band {status_class}">
            <div class="status-title">{title}</div>
            <div class="status-total">{total:.2f}%</div>
            <div class="status-copy">{headline} {detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def to_long_prices(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    working = frame.reset_index()
    if "index" in working.columns:
        working = working.rename(columns={"index": "date"})
    if "date" not in working.columns:
        working = working.rename(columns={working.columns[0]: "date"})
    working["ticker"] = ticker
    return working.loc[:, ["date", "ticker", "close", "adj_close", "volume", "source"]]


def load_requested_prices(
    tickers: list[str],
    *,
    start: date,
    end: date,
    refresh_live_data: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fixture_prices = load_fixture_prices()
    fixture_tickers = set(fixture_prices["ticker"].unique())
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)

    frames: list[pd.DataFrame] = []
    coverage_rows: list[dict[str, str | int]] = []
    errors: list[str] = []

    for ticker in tickers:
        if ticker in fixture_tickers:
            frame = fixture_prices.loc[fixture_prices["ticker"] == ticker].copy()
            frame = frame.loc[(frame["date"] >= start_ts) & (frame["date"] <= end_ts)]
            if frame.empty:
                errors.append(
                    f"{ticker}: no bundled data exists in the selected range. "
                    "Choose a different date range."
                )
                continue
            source_label = "bundled-fixture"
        else:
            try:
                fetched = fetch_prices(
                    ticker,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    refresh=refresh_live_data,
                )
            except Exception as exc:
                errors.append(
                    f"{ticker}: live data is unavailable. Configure `TIINGO_API_KEY`, "
                    f"cache the symbol first, or use a bundled ticker. Details: {exc}"
                )
                continue
            if fetched.empty:
                errors.append(f"{ticker}: no price rows were returned for the selected date range.")
                continue
            frame = to_long_prices(fetched, ticker)
            source_label = ", ".join(sorted({str(value) for value in frame["source"].unique()}))

        coverage_rows.append(
            {
                "ticker": ticker,
                "rows": int(len(frame)),
                "source": source_label,
                "start": pd.Timestamp(frame["date"].min()).date().isoformat(),
                "end": pd.Timestamp(frame["date"].max()).date().isoformat(),
            }
        )
        frames.append(frame)

    if errors:
        raise RuntimeError("\n".join(errors))
    if not frames:
        raise RuntimeError("No price data could be loaded for the selected tickers.")

    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    return combined, pd.DataFrame(coverage_rows)


def create_allocation_chart(
    values: dict[str, float], title: str, *, percent_mode: bool = False
) -> go.Figure:
    positive = {ticker: value for ticker, value in values.items() if value > 0}
    figure = go.Figure()
    if positive:
        chart_values = list(positive.values())
        if percent_mode:
            chart_values = [float(value) for value in chart_values]
        figure.add_trace(
            go.Pie(
                labels=list(positive.keys()),
                values=chart_values,
                hole=0.58,
                sort=False,
                marker=dict(
                    colors=["#0d6b6b", "#eb6e4b", "#e2b714", "#3859d8", "#70a37f", "#8e44ad"]
                ),
            )
        )
    else:
        figure.add_annotation(
            text="Add weights to preview allocation",
            showarrow=False,
            font=dict(size=14, color="#475467"),
        )
    figure.update_layout(
        title=title,
        margin=dict(t=56, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_asset_chart(price_matrix: pd.DataFrame, tickers: list[str]) -> go.Figure:
    figure = go.Figure()
    for ticker in tickers:
        if ticker not in price_matrix.columns:
            continue
        series = price_matrix[ticker].dropna()
        if series.empty:
            continue
        normalized = (series / float(series.iloc[0])) * 100.0
        figure.add_trace(
            go.Scatter(x=normalized.index, y=normalized.values, mode="lines", name=ticker)
        )
    figure.update_layout(
        title="Underlying Asset Growth (normalized to 100)",
        xaxis_title="Date",
        yaxis_title="Normalized Value",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_rolling_return_chart(result: dict, window: int = 63) -> go.Figure:
    growth = pd.Series(result["growth_series"]).astype(float)
    rolling = growth.pct_change(window).dropna()
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=rolling.index,
            y=rolling.values,
            mode="lines",
            name=f"{window}-day return",
            line=dict(color="#eb6e4b", width=2.5),
        )
    )
    figure.update_layout(
        title=f"Rolling {window}-Day Return",
        xaxis_title="Date",
        yaxis_title="Return (decimal)",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_rolling_volatility_chart(result: dict, window: int = 63) -> go.Figure:
    returns = pd.Series(result["daily_returns"]).astype(float)
    rolling = returns.rolling(window).std(ddof=0).dropna() * (252.0**0.5)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=rolling.index,
            y=rolling.values,
            mode="lines",
            name=f"{window}-day vol",
            line=dict(color="#0d6b6b", width=2.5),
        )
    )
    figure.update_layout(
        title=f"Rolling {window}-Day Annualized Volatility",
        xaxis_title="Date",
        yaxis_title="Volatility (decimal)",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_return_distribution_chart(result: dict) -> go.Figure:
    returns = pd.Series(result["daily_returns"]).astype(float)
    filtered = returns[returns != 0.0]
    if filtered.empty:
        filtered = returns
    figure = go.Figure()
    figure.add_trace(
        go.Histogram(
            x=filtered.values,
            nbinsx=40,
            marker=dict(color="#3859d8"),
            opacity=0.85,
            name="Daily returns",
        )
    )
    figure.update_layout(
        title="Daily Return Distribution",
        xaxis_title="Daily Return (decimal)",
        yaxis_title="Frequency",
        margin=dict(t=60, l=20, r=20, b=20),
        bargap=0.05,
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_monthly_heatmap(result: dict) -> go.Figure:
    growth = pd.Series(result["growth_series"]).astype(float)
    month_end = growth.resample("M").last().pct_change().dropna()
    if month_end.empty:
        figure = go.Figure()
        figure.add_annotation(
            text="Not enough data for monthly heatmap",
            showarrow=False,
            font=dict(size=14, color="#475467"),
        )
        figure.update_layout(
            title="Monthly Return Heatmap",
            xaxis_title="Month",
            yaxis_title="Year",
            paper_bgcolor="rgba(255,255,255,0)",
        )
        return figure

    heatmap_frame = pd.DataFrame(
        {
            "year": month_end.index.year,
            "month": month_end.index.month,
            "return": month_end.values,
        }
    )
    pivot = heatmap_frame.pivot(index="year", columns="month", values="return").sort_index(
        ascending=False
    )
    month_labels = [calendar.month_abbr[month] for month in range(1, 13)]
    pivot = pivot.reindex(columns=range(1, 13))

    figure = go.Figure(
        data=[
            go.Heatmap(
                z=pivot.values,
                x=month_labels,
                y=[str(index) for index in pivot.index],
                colorscale=[
                    [0.0, "#c0392b"],
                    [0.5, "#f6f1e9"],
                    [1.0, "#1f9b55"],
                ],
                colorbar=dict(title="Return"),
                zmid=0.0,
            )
        ]
    )
    figure.update_layout(
        title="Monthly Return Heatmap",
        xaxis_title="Month",
        yaxis_title="Year",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_correlation_heatmap(price_matrix: pd.DataFrame, tickers: list[str]) -> go.Figure:
    returns = price_matrix.loc[:, [ticker for ticker in tickers if ticker in price_matrix.columns]]
    correlation = returns.pct_change().dropna().corr()
    figure = go.Figure()
    if correlation.empty:
        figure.add_annotation(
            text="Not enough overlapping data for correlation",
            showarrow=False,
            font=dict(size=14, color="#475467"),
        )
    else:
        figure.add_trace(
            go.Heatmap(
                z=correlation.values,
                x=list(correlation.columns),
                y=list(correlation.index),
                colorscale="RdBu",
                zmin=-1.0,
                zmax=1.0,
                zmid=0.0,
                colorbar=dict(title="Corr"),
            )
        )
    figure.update_layout(
        title="Asset Correlation Heatmap",
        xaxis_title="Ticker",
        yaxis_title="Ticker",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_drawdown_comparison_chart(comparison: dict) -> go.Figure:
    figure = go.Figure()
    for item in comparison["portfolios"]:
        drawdown = pd.Series(item["drawdown_series"]).astype(float)
        figure.add_trace(
            go.Scatter(
                x=drawdown.index,
                y=drawdown.values,
                mode="lines",
                name=item["portfolio_name"],
            )
        )
    figure.update_layout(
        title="Portfolio Drawdown Comparison",
        xaxis_title="Date",
        yaxis_title="Drawdown (decimal)",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_rolling_return_comparison_chart(comparison: dict, window: int = 63) -> go.Figure:
    figure = go.Figure()
    for item in comparison["portfolios"]:
        growth = pd.Series(item["growth_series"]).astype(float)
        rolling = growth.pct_change(window).dropna()
        figure.add_trace(
            go.Scatter(
                x=rolling.index,
                y=rolling.values,
                mode="lines",
                name=item["portfolio_name"],
            )
        )
    figure.update_layout(
        title=f"Rolling {window}-Day Return Comparison",
        xaxis_title="Date",
        yaxis_title="Return (decimal)",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_metric_snapshot_chart(comparison: dict) -> go.Figure:
    metric_labels = {
        "cagr": "CAGR",
        "total_return": "Total Return",
        "annualized_volatility": "Volatility",
        "max_drawdown": "Max Drawdown",
    }
    figure = go.Figure()
    for item in comparison["portfolios"]:
        metrics = item["metrics"]
        figure.add_trace(
            go.Bar(
                name=item["portfolio_name"],
                x=list(metric_labels.values()),
                y=[float(metrics[key]) for key in metric_labels],
            )
        )
    figure.update_layout(
        title="Performance Snapshot",
        xaxis_title="Metric",
        yaxis_title="Value (decimal)",
        barmode="group",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_ending_value_comparison_chart(comparison: dict) -> go.Figure:
    names: list[str] = []
    ending_values: list[float] = []
    for item in comparison["portfolios"]:
        growth = pd.Series(item["growth_series"]).astype(float)
        names.append(item["portfolio_name"])
        ending_values.append(float(growth.iloc[-1]))

    figure = go.Figure(
        data=[
            go.Bar(
                x=names,
                y=ending_values,
                marker=dict(color=["#0d6b6b", "#eb6e4b", "#3859d8", "#e2b714", "#8e44ad"]),
            )
        ]
    )
    figure.update_layout(
        title="Ending Portfolio Value",
        xaxis_title="Portfolio",
        yaxis_title="Ending Value ($)",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def create_annual_return_comparison_chart(comparison: dict) -> go.Figure:
    annual_series: dict[str, pd.Series] = {}
    all_years: set[int] = set()
    for item in comparison["portfolios"]:
        annual = annual_returns_series(pd.Series(item["growth_series"]).astype(float))
        annual_series[item["portfolio_name"]] = annual
        all_years.update(int(year) for year in annual.index.tolist())

    years = sorted(all_years)
    figure = go.Figure()
    for name, annual in annual_series.items():
        figure.add_trace(
            go.Bar(
                name=name,
                x=[str(year) for year in years],
                y=[float(annual.get(year, 0.0)) for year in years],
            )
        )
    figure.update_layout(
        title="Annual Returns by Portfolio",
        xaxis_title="Year",
        yaxis_title="Return (decimal)",
        barmode="group",
        margin=dict(t=60, l=20, r=20, b=20),
        paper_bgcolor="rgba(255,255,255,0)",
    )
    return figure


def render_head_to_head_summary(comparison: dict) -> None:
    table = pd.DataFrame(comparison["comparison_table"])
    st.dataframe(table, use_container_width=True)

    if len(comparison["portfolios"]) < 2:
        return

    baseline = comparison["portfolios"][0]
    challenger = comparison["portfolios"][1]
    base_metrics = baseline["metrics"]
    challenger_metrics = challenger["metrics"]
    baseline_ending = float(pd.Series(baseline["growth_series"]).iloc[-1])
    challenger_ending = float(pd.Series(challenger["growth_series"]).iloc[-1])
    ending_delta = float(
        challenger_ending - baseline_ending
    )

    st.markdown("**Baseline vs Comparison**")
    cols = st.columns(4)
    cols[0].metric(
        "CAGR Delta",
        f"{challenger_metrics['cagr'] - base_metrics['cagr']:+.2%}",
        delta=f"{challenger['portfolio_name']} vs {baseline['portfolio_name']}",
    )
    cols[1].metric(
        "Total Return Delta",
        f"{challenger_metrics['total_return'] - base_metrics['total_return']:+.2%}",
        delta=f"{challenger['portfolio_name']} vs {baseline['portfolio_name']}",
    )
    cols[2].metric(
        "Sharpe Delta",
        f"{challenger_metrics['sharpe_ratio'] - base_metrics['sharpe_ratio']:+.2f}",
        delta=f"{challenger['portfolio_name']} vs {baseline['portfolio_name']}",
    )
    cols[3].metric(
        "Ending Value Delta",
        f"${ending_delta:,.0f}",
        delta=f"{challenger['portfolio_name']} vs {baseline['portfolio_name']}",
    )


def series_frame(series: pd.Series, label: str) -> pd.DataFrame:
    frame = pd.DataFrame({label: pd.Series(series)})
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "date"
    return frame


def render_metrics(metrics: dict) -> None:
    row_one = st.columns(4)
    row_one[0].metric("CAGR", f"{metrics['cagr']:.2%}")
    row_one[1].metric("Total Return", f"{metrics['total_return']:.2%}")
    row_one[2].metric("Volatility", f"{metrics['annualized_volatility']:.2%}")
    row_one[3].metric("Max Drawdown", f"{metrics['max_drawdown']:.2%}")

    row_two = st.columns(4)
    row_two[0].metric("Sharpe", f"{metrics['sharpe_ratio']:.2f}")
    row_two[1].metric("Sortino", f"{metrics['sortino_ratio']:.2f}")
    row_two[2].metric(
        "Best Year",
        f"{metrics['best_year']['year']}",
        delta=f"{metrics['best_year']['return']:.2%}",
    )
    row_two[3].metric(
        "Worst Year",
        f"{metrics['worst_year']['year']}",
        delta=f"{metrics['worst_year']['return']:.2%}",
    )


def render_result_contract(result: dict, price_matrix: pd.DataFrame) -> None:
    tickers = list(result["weights"].keys())
    tabs = st.tabs(["Overview", "Charts", "Deep Dive", "Series", "Raw Output"])

    with tabs[0]:
        render_metrics(result["metrics"])
        left, right = st.columns([1.0, 1.1])
        with left:
            st.markdown("**Weights**")
            weights_table = pd.DataFrame(
                [
                    {"Ticker": ticker, "Weight": f"{weight:.2%}"}
                    for ticker, weight in result["weights"].items()
                ]
            )
            st.dataframe(weights_table, use_container_width=True, hide_index=True)
            st.markdown("**Date Range**")
            st.dataframe(
                pd.DataFrame([result["date_range"]]), use_container_width=True, hide_index=True
            )
            if result["warnings"]:
                st.markdown("**Warnings**")
                for warning in result["warnings"]:
                    st.warning(warning)
            else:
                st.success("No warnings for this run.")
        with right:
            st.plotly_chart(
                create_allocation_chart(result["weights"], "Portfolio Allocation"),
                use_container_width=True,
                key=f"{result['portfolio_name']}-overview-allocation",
            )

    with tabs[1]:
        top = st.columns(2)
        top[0].plotly_chart(
            render_chart("growth", result),
            use_container_width=True,
            key=f"{result['portfolio_name']}-growth",
        )
        top[1].plotly_chart(
            render_chart("drawdown", result),
            use_container_width=True,
            key=f"{result['portfolio_name']}-drawdown",
        )
        middle = st.columns(2)
        middle[0].plotly_chart(
            render_chart("annual_returns", result),
            use_container_width=True,
            key=f"{result['portfolio_name']}-annual-returns",
        )
        middle[1].plotly_chart(
            create_asset_chart(price_matrix, tickers),
            use_container_width=True,
            key=f"{result['portfolio_name']}-asset-growth",
        )
        bottom = st.columns(2)
        bottom[0].plotly_chart(
            create_rolling_return_chart(result),
            use_container_width=True,
            key=f"{result['portfolio_name']}-rolling-return",
        )
        bottom[1].plotly_chart(
            create_rolling_volatility_chart(result),
            use_container_width=True,
            key=f"{result['portfolio_name']}-rolling-volatility",
        )

    with tabs[2]:
        top = st.columns(2)
        top[0].plotly_chart(
            create_monthly_heatmap(result),
            use_container_width=True,
            key=f"{result['portfolio_name']}-monthly-heatmap",
        )
        top[1].plotly_chart(
            create_return_distribution_chart(result),
            use_container_width=True,
            key=f"{result['portfolio_name']}-return-distribution",
        )
        bottom = st.columns(2)
        bottom[0].plotly_chart(
            create_correlation_heatmap(price_matrix, tickers),
            use_container_width=True,
            key=f"{result['portfolio_name']}-correlation-heatmap",
        )
        bottom[1].plotly_chart(
            create_allocation_chart(result["weights"], "Allocation Donut"),
            use_container_width=True,
            key=f"{result['portfolio_name']}-allocation-donut",
        )

    with tabs[3]:
        annual = annual_returns_series(pd.Series(result["growth_series"]))
        annual_table = annual.rename("annual_return").to_frame()
        annual_table.index.name = "year"
        st.markdown("**Daily Returns**")
        st.dataframe(
            series_frame(result["daily_returns"], "daily_return"), use_container_width=True
        )
        st.markdown("**Growth Series**")
        st.dataframe(
            series_frame(result["growth_series"], "portfolio_value"), use_container_width=True
        )
        st.markdown("**Drawdown Series**")
        st.dataframe(series_frame(result["drawdown_series"], "drawdown"), use_container_width=True)
        st.markdown("**Annual Returns**")
        st.dataframe(annual_table, use_container_width=True)

    with tabs[4]:
        st.json(to_jsonable(result))


def render_comparison_contract(comparison: dict, price_matrix: pd.DataFrame) -> None:
    tabs = st.tabs(["Head to Head", "Comparison Charts", "Portfolio Outputs", "Raw Output"])

    with tabs[0]:
        render_head_to_head_summary(comparison)
        top = st.columns(2)
        top[0].plotly_chart(
            create_metric_snapshot_chart(comparison),
            use_container_width=True,
            key="comparison-metric-snapshot-chart",
        )
        top[1].plotly_chart(
            create_ending_value_comparison_chart(comparison),
            use_container_width=True,
            key="comparison-ending-value-chart",
        )

    with tabs[1]:
        chart_cols = st.columns(2)
        chart_cols[0].plotly_chart(
            render_chart("comparison", comparison),
            use_container_width=True,
            key="comparison-growth-chart",
        )
        first = comparison["portfolios"][0]
        chart_cols[1].plotly_chart(
            create_asset_chart(price_matrix, list(first["weights"].keys())),
            use_container_width=True,
            key="comparison-asset-growth-chart",
        )
        lower = st.columns(2)
        lower[0].plotly_chart(
            create_drawdown_comparison_chart(comparison),
            use_container_width=True,
            key="comparison-drawdown-chart",
        )
        lower[1].plotly_chart(
            create_rolling_return_comparison_chart(comparison),
            use_container_width=True,
            key="comparison-rolling-return-chart",
        )
        annual_row = st.columns(1)
        annual_row[0].plotly_chart(
            create_annual_return_comparison_chart(comparison),
            use_container_width=True,
            key="comparison-annual-return-chart",
        )

    with tabs[2]:
        for item in comparison["portfolios"]:
            with st.expander(f"{item['portfolio_name']} details", expanded=False):
                render_metrics(item["metrics"])
                cols = st.columns(2)
                cols[0].dataframe(
                    pd.DataFrame([item["date_range"]]), use_container_width=True, hide_index=True
                )
                cols[1].plotly_chart(
                    create_allocation_chart(
                        item["weights"], f"{item['portfolio_name']} Allocation"
                    ),
                    use_container_width=True,
                    key=f"{item['portfolio_name']}-comparison-allocation",
                )
                st.plotly_chart(
                    render_chart("growth", item),
                    use_container_width=True,
                    key=f"{item['portfolio_name']}-comparison-growth",
                )
                st.dataframe(
                    series_frame(item["growth_series"], "portfolio_value").tail(25),
                    use_container_width=True,
                )

    with tabs[3]:
        st.json(to_jsonable(comparison))


def build_page_style() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

        .stApp, .stApp [data-testid="stAppViewContainer"] {
            background:
                radial-gradient(circle at 12% 15%, rgba(236, 110, 79, 0.18), transparent 26%),
                radial-gradient(circle at 88% 10%, rgba(17, 138, 178, 0.18), transparent 24%),
                linear-gradient(180deg, #f4efe6 0%, #f8f6f0 42%, #fcfbf8 100%);
            font-family: 'IBM Plex Sans', sans-serif;
            color: #1b2430;
        }

        .block-container {
            max-width: 1240px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        h1, h2, h3, .hero-title {
            font-family: 'Space Grotesk', sans-serif;
            letter-spacing: -0.03em;
        }

        .hero-shell {
            background: linear-gradient(135deg, rgba(255,255,255,0.92), rgba(255,247,237,0.96));
            border: 1px solid rgba(27, 36, 48, 0.08);
            border-radius: 24px;
            padding: 1.6rem 1.8rem;
            box-shadow: 0 24px 60px rgba(27, 36, 48, 0.08);
            margin-bottom: 1.25rem;
        }

        .hero-title {
            font-size: 3rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            color: #14213d;
        }

        .hero-copy {
            font-size: 1.05rem;
            line-height: 1.6;
            color: #475467;
            margin: 0;
            max-width: 65ch;
        }

        .card-shell {
            background: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(27, 36, 48, 0.08);
            border-radius: 22px;
            padding: 1.15rem 1.2rem;
            box-shadow: 0 16px 40px rgba(27, 36, 48, 0.06);
            margin-bottom: 1rem;
        }

        .kicker {
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.75rem;
            font-weight: 600;
            color: #0d6b6b;
            margin-bottom: 0.45rem;
        }

        .status-band {
            border-radius: 18px;
            padding: 0.9rem 1rem;
            border: 1px solid transparent;
            margin: 0.4rem 0 0.8rem 0;
        }

        .status-ok {
            background: rgba(31, 155, 85, 0.1);
            border-color: rgba(31, 155, 85, 0.18);
        }

        .status-bad {
            background: rgba(231, 76, 60, 0.1);
            border-color: rgba(231, 76, 60, 0.18);
        }

        .status-title {
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            font-weight: 600;
            color: #475467;
            margin-bottom: 0.15rem;
        }

        .status-total {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 2rem;
            font-weight: 700;
            color: #14213d;
            line-height: 1;
            margin-bottom: 0.25rem;
        }

        .status-copy {
            color: #475467;
            font-size: 0.92rem;
            line-height: 1.45;
        }

        .ticker-chip {
            display: inline-block;
            padding: 0.3rem 0.6rem;
            border-radius: 999px;
            background: rgba(13, 107, 107, 0.08);
            border: 1px solid rgba(13, 107, 107, 0.12);
            color: #0d6b6b;
            font-size: 0.82rem;
            font-weight: 600;
            margin: 0 0.35rem 0.35rem 0;
        }

        div[data-testid="stButton"] > button {
            border-radius: 14px;
            border: none;
            background: linear-gradient(135deg, #ec6e4f, #db4f45);
            color: white;
            font-weight: 600;
            min-height: 3.1rem;
            box-shadow: 0 16px 30px rgba(236, 110, 79, 0.25);
        }

        div[data-testid="stButton"] > button:hover {
            background: linear-gradient(135deg, #db6042, #c2433a);
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def ticker_chip_html(tickers: list[str]) -> str:
    return "".join(f'<span class="ticker-chip">{ticker}</span>' for ticker in tickers)


def main() -> None:
    st.set_page_config(
        page_title="Portfolio Backtester",
        page_icon="chart_with_upwards_trend",
        layout="wide",
    )
    build_page_style()

    fixture_prices = load_fixture_prices()
    bundled_tickers = fixture_universe()
    fixture_min_date = fixture_prices["date"].min().date()
    fixture_max_date = fixture_prices["date"].max().date()
    today = date.today()

    st.markdown(
        """
        <div class="hero-shell">
            <div class="kicker">Local-first backtesting</div>
            <div class="hero-title">Portfolio Backtester</div>
            <p class="hero-copy">
                Build a portfolio with a proper ticker picker, validate that weights add up to 100%,
                and inspect the same Python result contract through charts, tables, warnings,
                and raw output.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    controls_col, context_col = st.columns([1.2, 0.9])

    with controls_col:
        st.markdown('<div class="card-shell">', unsafe_allow_html=True)
        st.markdown('<div class="kicker">Portfolio Builder</div>', unsafe_allow_html=True)
        st.subheader("Choose assets and assign weights")

        primary_tickers = st.multiselect(
            "Tickers",
            options=bundled_tickers,
            default=[ticker for ticker in DEFAULT_TICKERS if ticker in bundled_tickers],
            accept_new_options=True,
            placeholder="Select bundled tickers or type a new ticker and press Enter",
            help=(
                "Bundled tickers work immediately. You can also type a new symbol "
                "like `VT` and press Enter to add it."
            ),
        )

        if not primary_tickers:
            st.warning("Select at least one bundled ticker or enter one live ticker.")

        raw_weights = collect_weight_inputs(
            primary_tickers,
            state_prefix="primary_weight",
            presets=DEFAULT_WEIGHTS,
        )
        primary_state = weight_state(raw_weights)
        render_status_band(
            "Primary portfolio total",
            primary_state["total"],
            primary_state["valid"],
            primary_state["delta"],
        )

        option_cols = st.columns(3)
        portfolio_name = option_cols[0].text_input("Portfolio name", value="My Portfolio").strip()
        rebalance = option_cols[1].selectbox("Rebalance", REBALANCE_OPTIONS, index=2)
        initial_capital = option_cols[2].number_input(
            "Initial capital ($)",
            min_value=1000.0,
            max_value=10_000_000.0,
            value=10_000.0,
            step=1000.0,
        )

        date_cols = st.columns(2)
        start_date = date_cols[0].date_input(
            "Start date",
            value=fixture_min_date,
            min_value=date(2000, 1, 1),
            max_value=today,
        )
        end_date = date_cols[1].date_input(
            "End date",
            value=fixture_max_date,
            min_value=date(2000, 1, 1),
            max_value=today,
        )

        st.markdown("### Comparison")
        enable_comparison = st.toggle(
            "Compare against a second portfolio",
            value=False,
            help="Turn this on to build and render a second portfolio in the same run.",
        )
        alt_name = ""
        alt_tickers: list[str] = []
        alt_state = weight_state({})
        if enable_comparison:
            st.markdown('<div class="card-shell">', unsafe_allow_html=True)
            st.markdown('<div class="kicker">Comparison Builder</div>', unsafe_allow_html=True)
            alt_tickers = st.multiselect(
                "Comparison tickers",
                options=bundled_tickers,
                default=[ticker for ticker in DEFAULT_ALT_WEIGHTS if ticker in bundled_tickers],
                key="comparison_bundled_tickers",
                accept_new_options=True,
                placeholder="Select bundled tickers or type a new ticker and press Enter",
                help=(
                    "Choose a different asset mix for the comparison portfolio. "
                    "Type a new symbol and press Enter to add it."
                ),
            )
            alt_name = st.text_input("Comparison name", value="Alternate Portfolio").strip()
            alt_raw_weights = collect_weight_inputs(
                alt_tickers,
                state_prefix="alt_weight",
                presets=DEFAULT_ALT_WEIGHTS,
                label_prefix="Alt ",
            )
            alt_state = weight_state(alt_raw_weights)
            render_status_band(
                "Comparison portfolio total",
                alt_state["total"],
                alt_state["valid"],
                alt_state["delta"],
            )
            st.markdown("</div>", unsafe_allow_html=True)

        refresh_live_data = st.checkbox(
            "Refresh live/cache data for non-bundled tickers",
            value=False,
        )

        run_clicked = st.button("Run Backtest", type="primary", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with context_col:
        st.markdown('<div class="card-shell">', unsafe_allow_html=True)
        st.markdown('<div class="kicker">Supported Universe</div>', unsafe_allow_html=True)
        st.subheader("Bundled tickers that work immediately")
        st.markdown(ticker_chip_html(bundled_tickers), unsafe_allow_html=True)
        st.caption(
            "Bundled tickers use the local deterministic dataset. "
            "Optional live tickers use the fetch/cache layer."
        )
        st.plotly_chart(
            create_allocation_chart(
                primary_state["positive"], "Live Allocation Preview", percent_mode=True
            ),
            use_container_width=True,
            key="builder-live-allocation-preview",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card-shell">', unsafe_allow_html=True)
        st.markdown('<div class="kicker">What Changed</div>', unsafe_allow_html=True)
        st.markdown(
            "- Weight totals must validate to 100% before the backtest runs.\n"
            "- `VWO` and several additional ETFs are now bundled locally.\n"
            "- Ticker pickers now accept new symbols directly when you type and press Enter.\n"
            "- Comparison now has its own ticker set, weights, and visible builder.\n"
            "- The output area shows charts, tables, warnings, and raw payloads "
            "from the Python engine."
        )
        st.markdown("</div>", unsafe_allow_html=True)

    if run_clicked:
        validation_errors: list[str] = []
        if not primary_tickers:
            validation_errors.append("Add at least one ticker before running a backtest.")
        if start_date > end_date:
            validation_errors.append("Start date must be on or before the end date.")
        if not primary_state["positive"]:
            validation_errors.append(
                "Enter at least one non-zero weight for the primary portfolio."
            )
        if not primary_state["valid"]:
            validation_errors.append(
                "Primary portfolio weights must total 100%. "
                f"Current total: {primary_state['total']:.2f}%."
            )
        if enable_comparison:
            if not alt_tickers:
                validation_errors.append(
                    "Add at least one ticker to the comparison portfolio."
                )
            if not alt_state["positive"]:
                validation_errors.append(
                    "Enter at least one non-zero weight for the comparison portfolio."
                )
            if not alt_state["valid"]:
                validation_errors.append(
                    "Comparison portfolio weights must total 100%. "
                    f"Current total: {alt_state['total']:.2f}%."
                )

        if validation_errors:
            for error in validation_errors:
                st.error(error)
        else:
            try:
                with st.spinner("Loading prices and running the backtest..."):
                    requested_tickers: list[str] = []
                    for ticker in [*primary_tickers, *alt_tickers]:
                        if ticker not in requested_tickers:
                            requested_tickers.append(ticker)
                    loaded_prices, coverage = load_requested_prices(
                        requested_tickers,
                        start=start_date,
                        end=end_date,
                        refresh_live_data=refresh_live_data,
                    )
                    price_matrix = build_price_matrix(loaded_prices)
                    single_result = run_backtest(
                        price_matrix,
                        primary_state["fractions"],
                        start=start_date.isoformat(),
                        end=end_date.isoformat(),
                        rebalance=rebalance,
                        initial_capital=initial_capital,
                        portfolio_name=portfolio_name or "My Portfolio",
                    )
                    comparison_result = None
                    if enable_comparison:
                        comparison_result = compare_portfolios(
                            price_matrix,
                            [
                                {
                                    "name": portfolio_name or "My Portfolio",
                                    "weights": primary_state["fractions"],
                                },
                                {
                                    "name": alt_name or "Alternate Portfolio",
                                    "weights": alt_state["fractions"],
                                },
                            ],
                            start=start_date.isoformat(),
                            end=end_date.isoformat(),
                            rebalance=rebalance,
                            initial_capital=initial_capital,
                        )

                    st.session_state["latest_ui_run"] = {
                        "coverage": coverage,
                        "prices": loaded_prices,
                        "price_matrix": price_matrix,
                        "single_result": single_result,
                        "comparison_result": comparison_result,
                        "comparison_enabled": enable_comparison,
                    }
            except Exception as exc:
                st.error(str(exc))

    latest_run = st.session_state.get("latest_ui_run")
    if latest_run is None:
        st.info("Build a valid 100% portfolio, then click `Run Backtest`.")
        return

    st.divider()
    st.header("Loaded Data")
    data_cols = st.columns([0.95, 1.05])
    data_cols[0].dataframe(latest_run["coverage"], use_container_width=True, hide_index=True)
    data_cols[1].dataframe(
        latest_run["prices"]
        .sort_values(["date", "ticker"])
        .loc[:, ["date", "ticker", "adj_close", "source"]]
        .tail(20),
        use_container_width=True,
        hide_index=True,
    )

    st.header("Single Portfolio Output")
    render_result_contract(latest_run["single_result"], latest_run["price_matrix"])

    if latest_run.get("comparison_enabled") and latest_run["comparison_result"] is not None:
        st.header("Comparison Output")
        render_comparison_contract(latest_run["comparison_result"], latest_run["price_matrix"])


if __name__ == "__main__":
    main()
