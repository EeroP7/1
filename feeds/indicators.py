"""
Technical indicators computed over a list of Klines.

All functions take a list[Kline] (most-recent first) and return
a single float or a named-tuple of floats.
"""
import math
from dataclasses import dataclass
from typing import Sequence

from feeds.binance_ws import Kline


@dataclass
class IndicatorSet:
    # momentum
    rsi_14: float           # 0-100
    stoch_rsi_k: float      # 0-100
    stoch_rsi_d: float      # 0-100

    # trend
    ema_9: float
    ema_21: float
    ema_50: float
    macd_line: float
    macd_signal: float
    macd_hist: float

    # volatility / bands
    bb_upper: float
    bb_mid: float
    bb_lower: float
    bb_width: float         # (upper - lower) / mid
    bb_pct_b: float         # (price - lower) / (upper - lower)

    # volume
    obv: float              # on-balance volume (normalised delta)
    vwap: float
    buy_sell_ratio: float   # taker buy / total volume (last 12 candles)

    # derived directional bias
    bull_score: float       # 0-1 weighted consensus of bullish signals
    bear_score: float       # 0-1


def _closes(klines: Sequence[Kline]) -> list[float]:
    return [k.close for k in reversed(klines)]   # oldest first


def _ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def _stoch_rsi(closes: list[float], rsi_period: int = 14,
               stoch_period: int = 14, k_smooth: int = 3,
               d_smooth: int = 3) -> tuple[float, float]:
    if len(closes) < rsi_period + stoch_period + k_smooth + d_smooth:
        return 50.0, 50.0
    rsi_vals = [
        _rsi(closes[:i + 1], rsi_period)
        for i in range(rsi_period, len(closes))
    ]
    stoch = []
    for i in range(stoch_period, len(rsi_vals) + 1):
        window = rsi_vals[i - stoch_period:i]
        lo, hi = min(window), max(window)
        stoch.append(0.0 if hi == lo else (rsi_vals[i - 1] - lo) / (hi - lo) * 100)
    def _smooth(vals: list[float], n: int) -> list[float]:
        out = []
        for i in range(n - 1, len(vals)):
            out.append(sum(vals[i - n + 1:i + 1]) / n)
        return out
    k_line = _smooth(stoch, k_smooth)
    d_line = _smooth(k_line, d_smooth)
    return (k_line[-1] if k_line else 50.0,
            d_line[-1] if d_line else 50.0)


def _bollinger(closes: list[float], period: int = 20,
               std_mult: float = 2.0) -> tuple[float, float, float]:
    if len(closes) < period:
        p = closes[-1] if closes else 0
        return p, p, p
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = math.sqrt(variance)
    return mid + std_mult * std, mid, mid - std_mult * std


def _obv_delta(klines: list[Kline], lookback: int = 12) -> float:
    """Normalised OBV change: positive = accumulation."""
    subset = list(reversed(klines))[-lookback - 1:]
    obv = 0.0
    for i in range(1, len(subset)):
        if subset[i].close > subset[i - 1].close:
            obv += subset[i].volume
        elif subset[i].close < subset[i - 1].close:
            obv -= subset[i].volume
    total_vol = sum(k.volume for k in subset) or 1
    return obv / total_vol


def _vwap(klines: list[Kline], lookback: int = 20) -> float:
    subset = list(reversed(klines))[-lookback:]
    total_pv = sum((k.high + k.low + k.close) / 3 * k.volume for k in subset)
    total_v  = sum(k.volume for k in subset)
    return total_pv / total_v if total_v else 0.0


def compute(klines: Sequence[Kline], price: float) -> IndicatorSet:
    closes = _closes(klines)
    ema9_series  = _ema(closes, 9)
    ema21_series = _ema(closes, 21)
    ema50_series = _ema(closes, 50)
    ema9  = ema9_series[-1]  if ema9_series  else price
    ema21 = ema21_series[-1] if ema21_series else price
    ema50 = ema50_series[-1] if ema50_series else price

    # MACD
    macd_line = (
        (_ema(closes, 12)[-1] if len(closes) >= 12 else price)
        - (_ema(closes, 26)[-1] if len(closes) >= 26 else price)
    )
    # signal = 9-period EMA of MACD (approximate with a single value here)
    macd_signal = macd_line * 0.9   # simplified; full impl needs MACD history
    macd_hist   = macd_line - macd_signal

    rsi = _rsi(closes)
    stoch_k, stoch_d = _stoch_rsi(closes)
    bb_upper, bb_mid, bb_lower = _bollinger(closes)
    bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid else 0
    bb_pct_b = ((price - bb_lower) / (bb_upper - bb_lower)
                if (bb_upper - bb_lower) > 0 else 0.5)

    obv = _obv_delta(list(klines))
    vwap = _vwap(list(klines))

    kl = list(reversed(klines))
    lookback = min(12, len(kl))
    total_vol = sum(k.volume for k in kl[-lookback:])
    buy_vol   = sum(k.taker_buy_volume for k in kl[-lookback:])
    bsr = buy_vol / total_vol if total_vol else 0.5

    # ── directional scoring ───────────────────────────────────────────────────
    bull_signals = [
        rsi < 70,                    # not overbought
        rsi > 50,                    # above midline
        stoch_k > stoch_d,           # stoch momentum up
        stoch_k < 80,                # not overbought
        price > ema9,                # short trend up
        ema9 > ema21,                # trend alignment
        ema21 > ema50,               # long trend up
        macd_hist > 0,               # MACD positive
        bb_pct_b > 0.5,              # above BB midline
        obv > 0.05,                  # accumulation
        bsr > 0.55,                  # buyers dominating
        price > vwap,                # above VWAP
    ]
    bear_signals = [
        rsi > 30,                    # not oversold
        rsi < 50,                    # below midline
        stoch_k < stoch_d,           # stoch momentum down
        stoch_k > 20,                # not oversold
        price < ema9,
        ema9 < ema21,
        ema21 < ema50,
        macd_hist < 0,
        bb_pct_b < 0.5,
        obv < -0.05,
        bsr < 0.45,
        price < vwap,
    ]
    bull_score = sum(1 for s in bull_signals if s) / len(bull_signals)
    bear_score = sum(1 for s in bear_signals if s) / len(bear_signals)

    return IndicatorSet(
        rsi_14=rsi, stoch_rsi_k=stoch_k, stoch_rsi_d=stoch_d,
        ema_9=ema9, ema_21=ema21, ema_50=ema50,
        macd_line=macd_line, macd_signal=macd_signal, macd_hist=macd_hist,
        bb_upper=bb_upper, bb_mid=bb_mid, bb_lower=bb_lower,
        bb_width=bb_width, bb_pct_b=bb_pct_b,
        obv=obv, vwap=vwap, buy_sell_ratio=bsr,
        bull_score=bull_score, bear_score=bear_score,
    )
