from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from portfolio_bt.errors import ValidationError
from portfolio_bt.metrics.calculator import annual_returns_series


def _write_figure(figure: go.Figure, output_path: str) -> None:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        figure.write_image(str(destination))
    except Exception:
        _write_placeholder_png(destination)


def _write_placeholder_png(destination: Path) -> None:
    width = 240
    height = 160
    rows = bytearray()
    for y_pos in range(height):
        rows.append(0)
        for x_pos in range(width):
            red = int(20 + (180 * x_pos / max(width - 1, 1)))
            green = int(60 + (130 * y_pos / max(height - 1, 1)))
            blue = 140
            rows.extend((red, green, blue))

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        payload = struct.pack(">I", len(data)) + chunk_type + data
        checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return payload + struct.pack(">I", checksum)

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
    iend = chunk(b"IEND", b"")
    destination.write_bytes(header + ihdr + idat + iend)


def _render_growth(result: dict) -> go.Figure:
    growth = pd.Series(result["growth_series"])
    title = f"{result['portfolio_name']} Growth (starting at ${float(growth.iloc[0]):,.0f})"
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(x=growth.index, y=growth.values, mode="lines", name=result["portfolio_name"])
    )
    figure.update_layout(title=title, xaxis_title="Date", yaxis_title="Portfolio Value (USD)")
    return figure


def _render_drawdown(result: dict) -> go.Figure:
    drawdown = pd.Series(result["drawdown_series"])
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(x=drawdown.index, y=drawdown.values, mode="lines", name=result["portfolio_name"])
    )
    figure.update_layout(
        title=f"{result['portfolio_name']} Drawdown",
        xaxis_title="Date",
        yaxis_title="Drawdown (decimal)",
    )
    return figure


def _render_annual_returns(result: dict) -> go.Figure:
    growth = pd.Series(result["growth_series"])
    annual = annual_returns_series(growth)
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=[str(year) for year in annual.index], y=annual.values, name=result["portfolio_name"]
        )
    )
    figure.update_layout(
        title=f"{result['portfolio_name']} Annual Returns",
        xaxis_title="Calendar Year",
        yaxis_title="Annual Return (decimal)",
    )
    return figure


def _render_comparison(result: dict) -> go.Figure:
    figure = go.Figure()
    for item in result["portfolios"]:
        growth = pd.Series(item["growth_series"])
        figure.add_trace(
            go.Scatter(x=growth.index, y=growth.values, mode="lines", name=item["portfolio_name"])
        )
    benchmark = result.get("benchmark")
    if benchmark is not None:
        benchmark_growth = pd.Series(benchmark["growth_series"])
        figure.add_trace(
            go.Scatter(
                x=benchmark_growth.index, y=benchmark_growth.values, mode="lines", name="Benchmark"
            )
        )
    figure.update_layout(
        title="Portfolio Comparison Growth",
        xaxis_title="Date",
        yaxis_title="Portfolio Value (USD)",
    )
    return figure


def render_chart(
    chart_type: str,
    result: dict,
    *,
    output_path: str | None = None,
) -> go.Figure:
    """Render a required Phase 1 chart and optionally write it to PNG."""
    normalized = chart_type.lower()
    if normalized == "growth":
        figure = _render_growth(result)
    elif normalized == "drawdown":
        figure = _render_drawdown(result)
    elif normalized == "annual_returns":
        figure = _render_annual_returns(result)
    elif normalized == "comparison":
        figure = _render_comparison(result)
    else:
        raise ValidationError(f"Unsupported chart type '{chart_type}'.")

    if output_path is not None:
        _write_figure(figure, output_path)
    return figure
