"""
Signal aggregator.

Collects signals from all data sources and maps them onto the 100-node
sentiment array consumed by the Mirofish engine.

Node assignment (matches mirofish.py docstring):
  0-09   price momentum
 10-19   volume
 20-34   technicals
 35-54   order-flow
 55-69   exchange flows
 70-79   derivatives (funding / OI proxies — synthetic when no feed)
 80-89   market structure
 90-99   cross-asset (synthetic)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from data.binance_ws import BinanceFeed
    from data.cryptoquant import CryptoQuantFeed


@dataclass
class AggregatedSignals:
    sentiments: np.ndarray          # shape (100,)
    timestamp: float = field(default_factory=time.time)
    signal_count: int = 0           # how many real signals populated


class SignalAggregator:
    def __init__(self, binance: "BinanceFeed", cryptoquant: "CryptoQuantFeed") -> None:
        self._binance = binance
        self._cryptoquant = cryptoquant
        self._prev_sentiments: np.ndarray = np.zeros(100)

    def aggregate(self) -> AggregatedSignals:
        arr = np.zeros(100)
        count = 0

        # ── 0-09: price momentum ─────────────────────────────────────────────
        mom = self._binance.momentum_signals(lookbacks=(1, 2, 3, 5, 8, 12, 20))
        mom_vals = list(mom.values())
        for i, v in enumerate(mom_vals[:10]):
            arr[i] = v
            count += 1

        # ── 10-19: volume ────────────────────────────────────────────────────
        vol = self._binance.volume_signals()
        vol_keys = ["bs_ratio", "vol_surge", "vwap_dev"]
        for i, k in enumerate(vol_keys):
            if k in vol:
                arr[10 + i] = vol[k]
                count += 1
        # Fill remaining volume nodes with noisy copies (same direction)
        base_vol = np.array([vol.get(k, 0.0) for k in vol_keys])
        for i in range(3, 10):
            arr[10 + i] = float(np.clip(base_vol.mean() + np.random.normal(0, 0.05), -1, 1))

        # ── 20-34: technicals ────────────────────────────────────────────────
        rsi = self._binance.rsi(14)
        macd = self._binance.macd_signal()
        rsi_fast = self._binance.rsi(7)
        if rsi is not None:
            arr[20] = rsi
            count += 1
        if macd is not None:
            arr[21] = macd
            count += 1
        if rsi_fast is not None:
            arr[22] = rsi_fast
            count += 1
        # Bollinger / ATR proxies via momentum spread
        if mom_vals:
            vol_arr = np.array([k.volume for k in self._binance.state.klines if k.closed][-20:])
            if len(vol_arr) >= 5:
                atr_proxy = float(np.tanh(vol_arr.std() / (vol_arr.mean() + 1e-6) * 3))
                arr[23] = atr_proxy
        # Fill rest with interpolations
        for i in range(24, 35):
            if rsi is not None and macd is not None:
                arr[i] = float(np.clip((rsi + macd) / 2 + np.random.normal(0, 0.04), -1, 1))

        # ── 35-54: order-flow ────────────────────────────────────────────────
        bid = self._binance.state.bid
        ask = self._binance.state.ask
        spread = ask - bid
        spot = self._binance.state.spot_price
        if spot > 0 and spread > 0:
            spread_bps = spread / spot * 10000
            # Tight spread = liquid / trending market
            arr[35] = float(np.tanh(-spread_bps / 5))
            arr[36] = float(np.tanh((spot - (bid + ask) / 2) / (spread + 1e-6)))
            count += 2
        # Simulated large-order flags from volume bursts
        vol_surge = vol.get("vol_surge", 0.0)
        for i in range(37, 55):
            arr[i] = float(np.clip(vol_surge * 0.6 + np.random.normal(0, 0.07), -1, 1))

        # ── 55-69: exchange flows ─────────────────────────────────────────────
        flows = self._cryptoquant.get_sentiments()
        flow_keys = ["flow_net", "flow_ratio", "whale_pressure", "miner_pressure"]
        for i, k in enumerate(flow_keys[:10]):
            if k in flows:
                arr[55 + i] = flows[k]
                count += 1
        for i in range(len(flow_keys), 15):
            arr[55 + i] = float(np.clip(
                flows.get("flow_net", 0.0) * 0.7 + np.random.normal(0, 0.05), -1, 1
            ))

        # ── 70-79: derivatives (synthetic) ───────────────────────────────────
        # Proxy: use momentum direction + volume as funding-rate surrogate
        mom_mean = np.array(mom_vals).mean() if mom_vals else 0.0
        for i in range(10):
            arr[70 + i] = float(np.clip(mom_mean * 0.8 + np.random.normal(0, 0.06), -1, 1))

        # ── 80-89: market structure ───────────────────────────────────────────
        klines = [k for k in self._binance.state.klines if k.closed]
        if len(klines) >= 20:
            closes = np.array([k.close for k in klines[-20:]])
            sma20 = closes.mean()
            trend = float(np.tanh((closes[-1] - sma20) / (sma20 * 0.005)))
            highs = np.array([k.high for k in klines[-20:]])
            lows = np.array([k.low for k in klines[-20:]])
            hh = float(np.tanh((closes[-1] - highs.max()) / (spot * 0.002))) if spot > 0 else 0.0
            ll = float(np.tanh((closes[-1] - lows.min()) / (spot * 0.002))) if spot > 0 else 0.0
            for i in range(10):
                weights = [trend, hh, ll, mom_mean]
                arr[80 + i] = float(np.clip(
                    np.array(weights).mean() + np.random.normal(0, 0.04), -1, 1
                ))
                count += 1

        # ── 90-99: cross-asset (synthetic) ───────────────────────────────────
        # In production: pull DXY, gold futures, equity index futures
        # Here we use a mean-reverting synthetic correlated with BTC momentum
        for i in range(10):
            arr[90 + i] = float(np.clip(mom_mean * 0.5 + np.random.normal(0, 0.1), -1, 1))

        # Smooth with previous tick (reduce noise churn)
        arr = 0.7 * arr + 0.3 * self._prev_sentiments
        arr = np.clip(arr, -1.0, 1.0)
        self._prev_sentiments = arr.copy()

        return AggregatedSignals(sentiments=arr, signal_count=count)
