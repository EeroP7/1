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


def test_sector_cap_caps_known_sectors():
    from risk.sizing import apply_sector_cap
    weights = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
    sectors = {"A": "Tech", "B": "Tech", "C": "Tech", "D": "Energy"}
    capped = apply_sector_cap(weights, 0.30, lambda t: sectors[t])
    assert abs(sum(capped.values()) - 1.0) < 1e-9
    tech_total = capped["A"] + capped["B"] + capped["C"]
    assert tech_total < 0.75  # was 0.75 before cap; must be scaled down


def test_sector_cap_unknown_sector_exempt():
    from risk.sizing import apply_sector_cap
    # All tickers unmapped → sector "Unknown" → no cap applied, weights unchanged
    weights = {"ZZZA": 0.4, "ZZZB": 0.6}
    capped = apply_sector_cap(weights, 0.30, lambda t: "Unknown")
    assert capped == pytest.approx(weights)


def test_risk_parity_weights_sum_to_one(prices):
    from risk.sizing import _risk_parity_weights
    tickers = prices.universe[:5]
    w = _risk_parity_weights(tickers, prices.close)
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(v > 0 for v in w.values())


def test_vol_target_scale_never_exceeds_one(prices):
    from risk.sizing import vol_target_scale
    tickers = prices.universe[:5]
    weights = {t: 0.2 for t in tickers}
    scale = vol_target_scale(weights, prices.close, target=10.0)  # absurdly high target
    assert scale <= 1.0  # long-only: never levers up


def test_vol_target_scale_reduces_for_low_target(prices):
    from risk.sizing import vol_target_scale
    tickers = prices.universe[:5]
    weights = {t: 0.2 for t in tickers}
    scale = vol_target_scale(weights, prices.close, target=0.01)  # 1% ann vol
    assert 0.0 < scale < 1.0


def test_vol_target_disabled_returns_full_exposure(prices):
    from risk.sizing import vol_target_scale
    weights = {t: 0.2 for t in prices.universe[:5]}
    assert vol_target_scale(weights, prices.close, target=0.0) == 1.0


def test_size_picks_risk_parity_mode(prices):
    from features.library import atr
    import pandas as pd
    atr_df = atr(prices)
    if not isinstance(atr_df.index, pd.DatetimeIndex):
        atr_df.index = pd.to_datetime(atr_df.index)
    ranked = [(t, 1.0) for t in prices.universe[:5]]
    config = RiskConfig(weight_mode="risk_parity", vol_target=0.15)
    picks = size_picks(ranked, prices, atr_df, config)
    total = sum(p.weight for p in picks)
    assert 0 < total <= 1.0 + 1e-6


def test_market_regime_on_in_uptrend():
    from risk.sizing import market_regime_on
    import pandas as pd, numpy as np
    dates = pd.bdate_range("2020-01-01", periods=300)
    close = pd.DataFrame({"A": np.linspace(100, 200, 300),
                          "B": np.linspace(50, 100, 300)}, index=dates)
    assert market_regime_on(close) is True


def test_market_regime_off_in_downtrend():
    from risk.sizing import market_regime_on
    import pandas as pd, numpy as np
    dates = pd.bdate_range("2020-01-01", periods=300)
    close = pd.DataFrame({"A": np.linspace(200, 100, 300),
                          "B": np.linspace(100, 50, 300)}, index=dates)
    assert market_regime_on(close) is False


def test_market_regime_defaults_on_with_short_history():
    from risk.sizing import market_regime_on
    import pandas as pd
    import numpy as np
    dates = pd.bdate_range("2020-01-01", periods=50)
    close = pd.DataFrame({"A": np.linspace(200, 100, 50)}, index=dates)
    assert market_regime_on(close) is True


def test_universe_config_scope_default_sp500():
    from data.universe import UniverseConfig
    assert UniverseConfig().scope == "sp500"


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
