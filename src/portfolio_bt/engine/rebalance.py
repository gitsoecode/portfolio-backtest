from __future__ import annotations

import pandas as pd

from portfolio_bt.errors import ValidationError

VALID_REBALANCE = {"none", "monthly", "quarterly", "annual"}


def build_rebalance_schedule(index: pd.Index, rebalance: str) -> pd.DatetimeIndex:
    """Return the first trading day of each target period."""
    schedule = str(rebalance).lower()
    if schedule not in VALID_REBALANCE:
        raise ValidationError(
            f"Unsupported rebalance value '{rebalance}'. Expected one of {sorted(VALID_REBALANCE)}."
        )

    date_index = pd.DatetimeIndex(index).sort_values().unique()
    if len(date_index) == 0:
        raise ValidationError("Cannot build a rebalance schedule for an empty index.")

    if schedule == "none":
        return pd.DatetimeIndex([date_index[0]])

    freq_map = {"monthly": "M", "quarterly": "Q", "annual": "Y"}
    periods = date_index.to_period(freq_map[schedule])
    change_mask = [True]
    for position in range(1, len(periods)):
        change_mask.append(periods[position] != periods[position - 1])
    return pd.DatetimeIndex(date_index[change_mask])
