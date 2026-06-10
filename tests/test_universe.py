import pandas as pd
import pytest
from data.universe import UniverseConfig, _make_synthetic, _apply_liquidity_filter


def test_synthetic_shape(prices):
    assert prices.close.shape[0] > 100
    assert prices.close.shape[1] == len(prices.config.tickers)


def test_synthetic_prices_positive(prices):
    assert (prices.close.values > 0).all()


def test_liquidity_filter_removes_low_price(prices):
    # inject a ticker with very low price
    import numpy as np
    from datetime import date, timedelta
    config = UniverseConfig(tickers=["LOWPRICE"], min_price=5.0, min_adv=1_000_000)
    end = date(2024, 1, 1)
    start = end - timedelta(days=100)
    p = _make_synthetic(config, start, end)
    # force close to $1
    p.close["LOWPRICE"] = 1.0
    p.volume["LOWPRICE"] = 2_000_000
    passed = _apply_liquidity_filter(p, config)
    assert "LOWPRICE" not in passed


def test_universe_has_universe_list(prices):
    assert len(prices.universe) > 0
    assert set(prices.universe).issubset(set(prices.close.columns))
