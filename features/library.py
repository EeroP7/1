"""
Cross-sectional feature library.

Each function takes the full PriceData and returns a DataFrame (date x ticker)
of raw feature values.  compute_features() stacks them and applies cross-
sectional normalization (z-score per date) so the ranker sees comparable inputs.

No look-ahead: all features on date t use data through close of t.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from data.universe import PriceData

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "mom_1m",
    "mom_3m",
    "mom_6m",
    "mom_12m_skip1m",
    "vol_adj_trend",
    "mean_rev_z20",
    "dist_52w_high",
    "vol_trend",
    "price_range",
]


# ---------------------------------------------------------------------------
# Individual features
# ---------------------------------------------------------------------------

def momentum(close: pd.DataFrame, lookback: int, skip: int = 0) -> pd.DataFrame:
    """Simple return over `lookback` trading days, optionally skipping the most recent `skip` days."""
    shifted_close = close.shift(skip)
    past_close = shifted_close.shift(lookback)
    return (shifted_close / past_close) - 1


def vol_adjusted_trend(close: pd.DataFrame, lookback: int = 63, vol_window: int = 21) -> pd.DataFrame:
    """Momentum / recent volatility — rewards smooth trends."""
    mom = momentum(close, lookback, skip=0)
    vol = close.pct_change().rolling(vol_window).std()
    return mom / vol.replace(0, np.nan)


def mean_reversion_zscore(close: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """z-score of price relative to its own recent mean (negative = oversold)."""
    rolling_mean = close.rolling(window).mean()
    rolling_std = close.rolling(window).std()
    return (close - rolling_mean) / rolling_std.replace(0, np.nan)


def dist_from_52w_high(close: pd.DataFrame) -> pd.DataFrame:
    """Pct distance below 52-week high (0 = at the high, -0.3 = 30% below)."""
    high_52w = close.rolling(252).max()
    return (close / high_52w) - 1


def volume_trend(volume: pd.DataFrame, short: int = 5, long: int = 20) -> pd.DataFrame:
    """Short-term / long-term volume ratio — rising volume is bullish."""
    return volume.rolling(short).mean() / volume.rolling(long).mean()


def normalized_price_range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Average True Range (ATR) as fraction of close — proxy for volatility regime."""
    tr = (high - low) / close
    return tr.rolling(window).mean()


# ---------------------------------------------------------------------------
# Cross-sectional normalization
# ---------------------------------------------------------------------------

def cs_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """z-score each row (date) across tickers, clipping at ±3."""
    mean = df.mean(axis=1)
    std = df.std(axis=1)
    z = df.sub(mean, axis=0).div(std, axis=0)
    return z.clip(-3, 3)


def cs_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Rank each row (date) across tickers, scaled to [-0.5, +0.5]."""
    ranked = df.rank(axis=1, pct=True) - 0.5
    return ranked


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_features(prices: "PriceData", normalize: bool = True) -> dict[str, pd.DataFrame]:
    """
    Compute all cross-sectional features.

    Returns a dict mapping feature_name -> (date x ticker) DataFrame of
    cross-sectionally normalized values.  Only tickers in prices.universe
    are included in the output.
    """
    close = prices.close
    high = prices.high
    low = prices.low
    volume = prices.volume

    universe = prices.universe
    if universe:
        close = close[universe]
        high = high[universe]
        low = low[universe]
        volume = volume[universe]

    raw: dict[str, pd.DataFrame] = {
        "mom_1m": momentum(close, 21, skip=0),
        "mom_3m": momentum(close, 63, skip=0),
        "mom_6m": momentum(close, 126, skip=0),
        "mom_12m_skip1m": momentum(close, 252, skip=21),
        "vol_adj_trend": vol_adjusted_trend(close, 63, 21),
        "mean_rev_z20": mean_reversion_zscore(close, 20),
        "dist_52w_high": dist_from_52w_high(close),
        "vol_trend": volume_trend(volume, 5, 20),
        "price_range": normalized_price_range(high, low, close, 14),
    }

    if normalize:
        return {name: cs_zscore(df) for name, df in raw.items()}
    return raw


def compute_feature_matrix(
    prices: "PriceData",
    date_: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Return a (ticker x feature) matrix for a single date, suitable for ranking.
    If date_ is None, uses the most recent date.
    """
    features = compute_features(prices, normalize=True)
    def _get_row(df: pd.DataFrame) -> pd.Series:
        if date_ is None:
            return df.iloc[-1]
        # Handle both date and Timestamp index
        if isinstance(df.index, pd.DatetimeIndex):
            return df.loc[date_]
        # date index stored as objects — convert key
        key = date_.date() if hasattr(date_, "date") else date_
        return df.loc[key]

    stacked = pd.DataFrame({name: _get_row(df) for name, df in features.items()})
    return stacked


def compute_forward_returns(close: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """
    Forward return matrix: value at date t = return from t to t+horizon.
    No look-ahead: result at date t requires price at t+horizon.
    Last `horizon` rows will be NaN.
    """
    return close.pct_change(horizon).shift(-horizon)


def atr(prices: "PriceData", window: int = 14) -> pd.DataFrame:
    """
    Average True Range per ticker, returned as a (date x ticker) DataFrame.
    Used by risk module for stop placement.
    """
    close = prices.close
    high = prices.high
    low = prices.low

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=0,
    ).groupby(level=0).max()
    # above concat approach won't work for multi-column; do it properly:
    tr = pd.DataFrame(
        np.maximum(
            (high - low).values,
            np.maximum(
                (high - prev_close).abs().values,
                (low - prev_close).abs().values,
            ),
        ),
        index=close.index,
        columns=close.columns,
    )
    return tr.rolling(window).mean()
