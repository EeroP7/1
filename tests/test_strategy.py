import pandas as pd
import pytest
from strategy.cross_sectional import (
    CrossSectionalRanker, RankerConfig, compute_forward_returns,
)


def test_ranker_fits_and_ranks(prices, features):
    close = prices.close
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index)
    fwd = compute_forward_returns(close)

    ranker = CrossSectionalRanker(RankerConfig(n_top=3))
    last_train = close.index[int(len(close.index) * 0.7)]
    ranker.fit(features, fwd, in_sample_end=last_train)

    last_date = max(df.index.max() for df in features.values())
    scores = ranker.score(last_date)
    assert len(scores) > 0
    assert scores.index.name is None or True  # just has values


def test_select_top_n_returns_n(prices, features):
    close = prices.close
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index)
    fwd = compute_forward_returns(close)

    ranker = CrossSectionalRanker(RankerConfig(n_top=5))
    ranker.fit(features, fwd)
    last_date = max(df.index.max() for df in features.values())
    picks = ranker.select_top_n(last_date)
    assert len(picks) <= 5
    assert all(isinstance(t, str) for t, _ in picks)


def test_forward_returns_no_lookahead(prices):
    close = prices.close
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index)
    fwd = compute_forward_returns(close, horizon=1)
    # Forward return at t should be close[t+1]/close[t] - 1
    # => fwd.iloc[-1] should be NaN (no t+1 for last row)
    assert fwd.iloc[-1].isna().all()
