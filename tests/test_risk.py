import numpy as np
import pytest
from risk.sizing import RiskConfig, size_picks


def test_size_picks_weights_sum_le_total_exposure(prices):
    from features.library import atr
    atr_df = atr(prices)
    import pandas as pd
    if not isinstance(atr_df.index, pd.DatetimeIndex):
        atr_df.index = pd.to_datetime(atr_df.index)

    tickers = prices.universe[:5]
    ranked = [(t, float(i)) for i, t in enumerate(reversed(tickers))]
    config = RiskConfig(max_weight=0.20, sector_cap=0.40, total_exposure=1.0)
    picks = size_picks(ranked, prices, atr_df, config)
    total_weight = sum(p.weight for p in picks)
    assert total_weight <= config.total_exposure + 1e-6


def test_size_picks_no_weight_exceeds_max(prices):
    from features.library import atr
    atr_df = atr(prices)
    import pandas as pd
    if not isinstance(atr_df.index, pd.DatetimeIndex):
        atr_df.index = pd.to_datetime(atr_df.index)

    tickers = prices.universe[:8]
    ranked = [(t, float(i)) for i, t in enumerate(reversed(tickers))]
    config = RiskConfig(max_weight=0.15)
    picks = size_picks(ranked, prices, atr_df, config)
    for p in picks:
        assert p.weight <= config.max_weight + 1e-6


def test_size_picks_stop_below_entry(prices):
    from features.library import atr
    atr_df = atr(prices)
    import pandas as pd
    if not isinstance(atr_df.index, pd.DatetimeIndex):
        atr_df.index = pd.to_datetime(atr_df.index)

    ranked = [(t, 1.0) for t in prices.universe[:3]]
    picks = size_picks(ranked, prices, atr_df)
    for p in picks:
        if not np.isnan(p.stop):
            assert p.stop < p.entry_ref


def test_size_picks_rank_order(prices):
    from features.library import atr
    atr_df = atr(prices)
    import pandas as pd
    if not isinstance(atr_df.index, pd.DatetimeIndex):
        atr_df.index = pd.to_datetime(atr_df.index)

    ranked = [(t, float(10 - i)) for i, t in enumerate(prices.universe[:5])]
    picks = size_picks(ranked, prices, atr_df)
    assert picks[0].rank == 1
    assert picks[-1].rank == len(picks)
