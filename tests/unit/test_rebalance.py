from __future__ import annotations

import pandas as pd

from portfolio_bt.engine.rebalance import build_rebalance_schedule


def test_monthly_schedule_uses_first_trading_day_of_each_month():
    index = pd.to_datetime(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-04", "2020-04-01"])
    schedule = build_rebalance_schedule(index, "monthly")
    assert list(schedule.strftime("%Y-%m-%d")) == ["2020-01-30", "2020-02-03", "2020-04-01"]


def test_quarterly_schedule_uses_first_trading_day_of_each_quarter():
    index = pd.to_datetime(["2020-01-30", "2020-02-03", "2020-04-01", "2020-04-02"])
    schedule = build_rebalance_schedule(index, "quarterly")
    assert list(schedule.strftime("%Y-%m-%d")) == ["2020-01-30", "2020-04-01"]


def test_annual_schedule_uses_first_trading_day_of_each_year():
    index = pd.to_datetime(["2020-01-02", "2020-12-31", "2021-01-04", "2021-03-01"])
    schedule = build_rebalance_schedule(index, "annual")
    assert list(schedule.strftime("%Y-%m-%d")) == ["2020-01-02", "2021-01-04"]
