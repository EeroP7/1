"""Shared fixtures for all tests — uses synthetic data, no network calls."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from data.universe import PriceData, UniverseConfig, _make_synthetic


@pytest.fixture(scope="session")
def prices() -> PriceData:
    from datetime import date, timedelta
    end = date(2024, 6, 1)
    start = end - timedelta(days=365 * 2 + 30)
    config = UniverseConfig(tickers=[
        "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL",
        "META", "TSLA", "AVGO", "JPM", "V",
        "XOM", "JNJ", "UNH", "PG", "HD",
    ])
    p = _make_synthetic(config, start, end)
    p.universe = config.tickers
    return p


@pytest.fixture(scope="session")
def features(prices):
    import pandas as pd
    from features.library import compute_features
    raw = compute_features(prices, normalize=True)
    # convert date index to datetime
    for k in raw:
        if not isinstance(raw[k].index, pd.DatetimeIndex):
            raw[k].index = pd.to_datetime(raw[k].index)
    return raw
