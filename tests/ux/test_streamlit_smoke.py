from __future__ import annotations

from pathlib import Path

import pytest


def test_streamlit_smoke():
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [repo_root / "streamlit_app.py", repo_root / "app.py"]
    if not any(path.exists() for path in candidates):
        pytest.skip("No Streamlit app exists for Phase 1.")
    pytest.skip("Streamlit UI is deferred in Phase 1.")
