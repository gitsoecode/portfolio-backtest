from __future__ import annotations

from pathlib import Path

import pytest


def test_streamlit_smoke():
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [repo_root / "streamlit_app.py", repo_root / "app.py"]
    existing = next((path for path in candidates if path.exists()), None)
    if existing is None:
        pytest.skip("No Streamlit app exists for Phase 1.")

    source = existing.read_text(encoding="utf-8")
    assert "Run Backtest" in source
    assert "streamlit" in source
