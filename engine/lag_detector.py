"""
CLOB lag detector.

Compares Polymarket's implied BTC direction probability against Binance
spot price movement to find moments where the CLOB hasn't repriced yet.

The core insight: Polymarket's UP probability should track BTC's implied
probability of being higher in 5 minutes.  When Binance spot has already
moved significantly but the CLOB still reflects the old price, there's
an arbitrage window.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class LagSignal:
    has_edge: bool
    direction: str          # "UP" or "DOWN"
    lag_pct: float          # abs difference between implied and fair probability
    fair_up_prob: float     # our estimate of true UP probability
    clob_up_price: float    # Polymarket's current YES price for UP
    spot_price: float
    confidence: float       # 0-1, factoring in signal age and magnitude
    detected_at: float


class LagDetector:
    """
    Maintains a rolling price history and computes a fair-value UP
    probability from recent spot momentum.  Compares against CLOB price
    to detect lag opportunities.

    Parameters
    ----------
    lag_threshold   : minimum price divergence to signal (default 0.003 = 0.3%)
    history_window  : number of spot samples to track
    """

    def __init__(self, lag_threshold: float = 0.003, history_window: int = 50) -> None:
        self._threshold = lag_threshold
        self._spot_history: deque[tuple[float, float]] = deque(maxlen=history_window)
        self._last_signal: Optional[LagSignal] = None

    def update_spot(self, price: float) -> None:
        self._spot_history.append((time.time(), price))

    def detect(
        self,
        clob_up_price: float,
        spot_price: float,
        mirofish_direction: str,
        mirofish_confidence: float,
    ) -> Optional[LagSignal]:
        """
        Return a LagSignal when the CLOB lags spot by > threshold AND
        Mirofish agrees on direction.

        Fair-value UP probability is derived from:
          1. Short-term momentum (last 10 spot ticks)
          2. Deviation from the neutral 0.5 base
          3. Mirofish direction agreement as a confidence multiplier
        """
        if not self._spot_history or spot_price <= 0 or clob_up_price <= 0:
            return None

        # ── compute fair UP probability ───────────────────────────────────────
        fair_up = self._fair_value_up(spot_price)

        # ── measure CLOB lag ─────────────────────────────────────────────────
        clob_lag = fair_up - clob_up_price   # positive = CLOB under-priced UP

        abs_lag = abs(clob_lag)
        if abs_lag < self._threshold:
            return None

        direction = "UP" if clob_lag > 0 else "DOWN"

        # Mirofish must agree with lag direction, or confidence is zero
        if mirofish_direction != "NEUTRAL" and mirofish_direction != direction:
            return None

        miro_mult = mirofish_confidence if mirofish_direction == direction else 0.5
        confidence = float(np.clip(
            (abs_lag / self._threshold - 1) * 0.6 * miro_mult, 0.0, 1.0
        ))

        signal = LagSignal(
            has_edge=True,
            direction=direction,
            lag_pct=abs_lag,
            fair_up_prob=fair_up,
            clob_up_price=clob_up_price,
            spot_price=spot_price,
            confidence=confidence,
            detected_at=time.time(),
        )
        self._last_signal = signal
        return signal

    def _fair_value_up(self, current_spot: float) -> float:
        """
        Estimate the true probability that BTC is up in 5 minutes.

        Uses a logistic function of short-term momentum to push the base
        probability (0.5) toward 0 or 1.
        """
        history = list(self._spot_history)
        if len(history) < 5:
            return 0.5

        prices = np.array([p for _, p in history[-20:]])
        # 1-tick return (most recent momentum)
        ret1 = (prices[-1] - prices[-2]) / prices[-2] if len(prices) >= 2 else 0.0
        # 5-tick momentum
        ret5 = (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 6 else 0.0
        # Trend consistency (positive returns in last N ticks)
        diffs = np.diff(prices[-10:])
        trend = diffs[diffs > 0].shape[0] / len(diffs) if len(diffs) > 0 else 0.5

        # Weighted combination → shift from 0.5
        momentum = ret1 * 0.4 + ret5 * 0.4 + (trend - 0.5) * 0.2
        # Logistic scaling: tanh maps momentum to (-1, 1), then shift to (0, 1)
        shift = float(np.tanh(momentum * 200)) * 0.35   # max ±0.35 shift
        return float(np.clip(0.5 + shift, 0.05, 0.95))

    @property
    def last_signal(self) -> Optional[LagSignal]:
        return self._last_signal
