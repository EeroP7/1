#!/usr/bin/env python3
"""
Head-to-head 5-year backtest of strategy upgrades.

Variants (all walk-forward, costs charged, no look-ahead):
  baseline          — current production strategy (top-5, monthly, inv-vol)
  vol_target        — baseline returns scaled to 15% ann. vol target (lagged vol)
  regime_filter     — baseline gated flat when universe index < 200d MA (lagged)
  residual_momentum — momentum features computed on market-relative prices
  combined          — residual momentum + vol target + regime filter

⚠️  SURVIVORSHIP BIAS: current-only universe; all figures optimistic upper bounds.
"""

from __future__ import annotations

import os
import sys
from copy import copy
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from data.universe import UniverseConfig, load_universe
from features.library import compute_features
from strategy.cross_sectional import CrossSectionalRanker, RankerConfig
from backtest.portfolio import (
    BacktestConfig, SURVIVORSHIP_WARNING, run_backtest,
    _annualized_sharpe, _max_drawdown,
)

TOP_N = 5
REBALANCE = "M"
VOL_TARGET = 0.15          # annualized
VOL_LOOKBACK = 21
REGIME_MA = 200


def _filter_warmup(features: dict, n_universe: int) -> dict:
    count_series = [df.count(axis=1) for df in features.values()]
    min_valid = count_series[0].copy()
    for s in count_series[1:]:
        min_valid = min_valid.where(min_valid <= s, s)
    valid = min_valid[min_valid > n_universe * 0.5].index
    return {k: v.loc[valid] for k, v in features.items()}


def _stats(returns: pd.Series, label: str) -> dict:
    eq = (1 + returns.fillna(0)).cumprod()
    return {
        "strategy": label,
        "total_return_pct": round((eq.iloc[-1] - 1) * 100, 1),
        "sharpe": round(_annualized_sharpe(returns), 2),
        "max_drawdown_pct": round(_max_drawdown(eq) * 100, 1),
        "oos_days": len(returns),
    }


def vol_target_overlay(returns: pd.Series) -> pd.Series:
    realized = returns.rolling(VOL_LOOKBACK).std() * np.sqrt(252)
    lev = (VOL_TARGET / realized).clip(upper=1.0).shift(1).fillna(1.0)
    return returns * lev


def regime_overlay(returns: pd.Series, index_level: pd.Series) -> pd.Series:
    risk_on = (index_level > index_level.rolling(REGIME_MA).mean()).shift(1)
    risk_on = risk_on.reindex(returns.index).fillna(True)
    return returns.where(risk_on, 0.0)


def _load_from_yahoo(start: date, end: date) -> "PriceData":
    """20y+ history via Yahoo Finance (Alpaca only goes back to 2016).

    ⚠️  Survivorship bias is WORSE at long horizons: the current S&P list
    contains none of the names that died in 2008 etc.  Results are even
    more optimistic than usual.
    """
    import yfinance as yf
    from data.universe import _SP500_TICKERS, PriceData

    tickers = [t.replace(".", "-") for t in _SP500_TICKERS]  # BRK.B → BRK-B
    df = yf.download(tickers, start=start.isoformat(), end=end.isoformat(),
                     progress=False, auto_adjust=True, group_by="column")

    def _field(name: str) -> pd.DataFrame:
        out = df[name].copy()
        out.columns = [c.replace("-", ".") for c in out.columns]
        return out

    close = _field("Close")
    # drop tickers with <60% coverage to avoid all-NaN columns from delistings
    keep = close.columns[close.notna().mean() > 0.6]
    prices = PriceData(
        open=_field("Open")[keep], high=_field("High")[keep],
        low=_field("Low")[keep], close=close[keep],
        volume=_field("Volume")[keep],
        universe=list(keep), config=UniverseConfig(),
    )
    return prices


def main() -> None:
    print(SURVIVORSHIP_WARNING, "\n")
    end = date.today()
    years = int(os.getenv("YEARS", "5"))
    start = end - timedelta(days=365 * years + 30)

    if os.getenv("DATA_SOURCE", "alpaca") == "yahoo":
        prices = _load_from_yahoo(start, end)
    else:
        prices = load_universe(config=UniverseConfig(), start=start, end=end)
    print(f"Universe: {len(prices.universe)} tickers, "
          f"{len(prices.close)} days ({prices.close.index[0]} → {prices.close.index[-1]})")

    close = prices.close
    if not isinstance(close.index, pd.DatetimeIndex):
        for attr in ("open", "high", "low", "close", "volume"):
            df = getattr(prices, attr)
            df.index = pd.to_datetime(df.index)
        close = prices.close

    # equal-weight universe index (for regime filter and residual momentum)
    index_level = (1 + close.pct_change().mean(axis=1)).cumprod()

    features = _filter_warmup(compute_features(prices, normalize=True),
                              len(prices.universe))

    bt_config = BacktestConfig(n_top=TOP_N, rebalance_freq=REBALANCE)

    # --- baseline ---
    ranker = CrossSectionalRanker(RankerConfig(n_top=TOP_N))
    base = run_backtest(prices, ranker, features, bt_config)
    base_r = base.oos_returns

    # --- residual momentum: features from market-relative prices ---
    rel = copy(prices)
    rel.open = prices.open.div(index_level, axis=0)
    rel.high = prices.high.div(index_level, axis=0)
    rel.low = prices.low.div(index_level, axis=0)
    rel.close = prices.close.div(index_level, axis=0)
    rel_features = _filter_warmup(compute_features(rel, normalize=True),
                                  len(prices.universe))
    ranker_res = CrossSectionalRanker(RankerConfig(n_top=TOP_N))
    res = run_backtest(prices, ranker_res, rel_features, bt_config)
    res_r = res.oos_returns

    # --- residual momentum + risk-parity (correlation-aware) weighting ---
    rp_config = BacktestConfig(n_top=TOP_N, rebalance_freq=REBALANCE,
                               weight_mode="risk_parity")
    ranker_rp = CrossSectionalRanker(RankerConfig(n_top=TOP_N))
    res_rp = run_backtest(prices, ranker_rp, rel_features, rp_config)
    res_rp_r = res_rp.oos_returns

    rows = [
        _stats(base_r, "baseline (current production)"),
        _stats(res_r, "residual momentum"),
        _stats(res_rp_r, "residual + risk parity"),
        _stats(vol_target_overlay(res_r), "residual + vol target"),
        _stats(regime_overlay(res_r, index_level), "residual + regime filter"),
        _stats(vol_target_overlay(res_rp_r), "residual + risk parity + vol target"),
        _stats(regime_overlay(vol_target_overlay(res_rp_r), index_level),
               "residual + risk parity + vol target + regime"),
    ]
    out = pd.DataFrame(rows)
    print("\n", out.to_string(index=False))
    out.to_csv("output_data/strategy_comparison.csv", index=False)
    print("\nSaved to output_data/strategy_comparison.csv")
    print("\n" + SURVIVORSHIP_WARNING)


if __name__ == "__main__":
    main()
