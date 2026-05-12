"""
Feature engineering for the RL trading environment.

Takes raw OHLCV candles (pandas DataFrame) and produces a normalised
feature matrix that the agent observes at each timestep.

Features (34 total):
  Returns:      log-return 1/3/6/12/24 bars
  Momentum:     ROC 5/10/20
  Trend:        SMA ratio 10/20/50, EMA ratio 9/21
  Volatility:   ATR/price 14, rolling std 10/20
  Oscillators:  RSI 14/7, Stoch %K/%D, CCI 20
  Volume:       volume z-score, OBV change, buy-ratio proxy
  MACD:         MACD line, signal line, histogram
  Position:     current position (0=flat, 1=long), unrealised P&L
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_div(a: pd.Series, b: pd.Series, fill: float = 0.0) -> pd.Series:
    return a.div(b.replace(0, np.nan)).fillna(fill)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Parameters
    ----------
    df : DataFrame with columns [open, high, low, close, volume].
         Index should be datetime or integer.

    Returns
    -------
    DataFrame with same index, NaN rows dropped.
    """
    f = pd.DataFrame(index=df.index)
    c = df["close"]
    h = df["high"]
    lo = df["low"]
    v = df["volume"]

    # ── returns ──────────────────────────────────────────────────────────────
    for lb in (1, 3, 6, 12, 24):
        f[f"ret_{lb}"] = np.log(c / c.shift(lb)).fillna(0)

    # ── momentum (rate of change) ─────────────────────────────────────────────
    for lb in (5, 10, 20):
        f[f"roc_{lb}"] = (c - c.shift(lb)) / c.shift(lb).replace(0, np.nan)

    # ── trend: price / moving-average ratios ─────────────────────────────────
    for w in (10, 20, 50):
        ma = c.rolling(w).mean()
        f[f"sma_ratio_{w}"] = _safe_div(c, ma) - 1.0
    for w in (9, 21):
        ema = c.ewm(span=w, adjust=False).mean()
        f[f"ema_ratio_{w}"] = _safe_div(c, ema) - 1.0

    # ── volatility ────────────────────────────────────────────────────────────
    tr = pd.concat([
        h - lo,
        (h - c.shift(1)).abs(),
        (lo - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    f["atr_ratio"] = _safe_div(atr14, c)
    for w in (10, 20):
        f[f"vol_std_{w}"] = np.log(c).diff().rolling(w).std().fillna(0)

    # ── RSI ───────────────────────────────────────────────────────────────────
    for period in (14, 7):
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = _safe_div(gain, loss)
        f[f"rsi_{period}"] = (100 - 100 / (1 + rs)) / 100 - 0.5   # centre at 0

    # ── Stochastic %K and %D ─────────────────────────────────────────────────
    low14 = lo.rolling(14).min()
    high14 = h.rolling(14).max()
    stoch_k = _safe_div(c - low14, high14 - low14)
    f["stoch_k"] = stoch_k - 0.5
    f["stoch_d"] = stoch_k.rolling(3).mean() - 0.5

    # ── CCI ───────────────────────────────────────────────────────────────────
    tp = (h + lo + c) / 3
    ma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = _safe_div(tp - ma_tp, 0.015 * mad)
    f["cci"] = np.tanh(cci / 100)

    # ── volume ────────────────────────────────────────────────────────────────
    vol_mean = v.rolling(20).mean()
    vol_std = v.rolling(20).std().replace(0, np.nan)
    f["vol_zscore"] = ((v - vol_mean) / vol_std).fillna(0).clip(-3, 3) / 3
    obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
    f["obv_change"] = np.tanh(obv.diff(5).fillna(0) / (v.rolling(5).sum() + 1e-6))

    # ── MACD ─────────────────────────────────────────────────────────────────
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_sig = macd.ewm(span=9, adjust=False).mean()
    norm = c * 0.001
    f["macd"] = np.tanh(macd / norm)
    f["macd_signal"] = np.tanh(macd_sig / norm)
    f["macd_hist"] = np.tanh((macd - macd_sig) / norm)

    return f.dropna()
