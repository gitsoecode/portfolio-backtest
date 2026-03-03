from __future__ import annotations

import pytest

from portfolio_bt.data.cache import CacheStore
from tests.helpers import FIXTURES, load_expected_json, load_price_fixture, pivot_adj_close


@pytest.fixture(scope="session")
def fixtures_root():
    return FIXTURES


@pytest.fixture(scope="session")
def three_fund_prices():
    return load_price_fixture("three_fund_2011_2020")


@pytest.fixture(scope="session")
def compare_prices():
    return load_price_fixture("compare_2011_2020")


@pytest.fixture(scope="session")
def three_fund_matrix(three_fund_prices):
    return pivot_adj_close(three_fund_prices)


@pytest.fixture(scope="session")
def compare_price_matrix(compare_prices):
    return pivot_adj_close(compare_prices)


@pytest.fixture(scope="session")
def known_answers():
    return load_expected_json("known_answers")


@pytest.fixture()
def cache_store(tmp_path):
    return CacheStore(root=tmp_path / "cache")
