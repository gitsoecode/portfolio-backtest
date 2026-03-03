from __future__ import annotations

import pytest

from portfolio_bt.engine.allocations import validate_weights
from portfolio_bt.errors import ValidationError


def test_validate_weights_rejects_negative_weight():
    with pytest.raises(ValidationError):
        validate_weights({"SPY": 1.1, "BND": -0.1})


def test_validate_weights_rejects_non_summing_allocations():
    with pytest.raises(ValidationError):
        validate_weights({"SPY": 0.7, "BND": 0.2})


def test_validate_weights_accepts_valid_allocations():
    result = validate_weights({"spy": 0.6, "bnd": 0.4})
    assert result == {"SPY": 0.6, "BND": 0.4}
