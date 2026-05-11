"""
Binance WebSocket feed.

Maintains a live BTC spot price and a rolling window of 5M kline data.
Computes derived signals (returns, volume ratios, VWAP deviation) used
by the signal aggregator.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

import aiohttp
import numpy as np
import websockets

BINANCE_WS = "wss://stream.binance.com:9443/ws"
BINANCE_REST = "https://api.binance.com"
KLINES_ENDPOINT = "/api/v3/klines"


@dataclass
class Kline:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    quote_volume: float
    taker_buy_base: float
    taker_buy_quote: float
    closed: bool = True


@dataclass
class BinanceState:
    spot_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    last_trade_price: float = 0.0
    last_trade_qty: float = 0.0
    last_update_ts: float = 0.0
    klines: Deque[Kline] = field(default_factory=lambda: deque(maxlen=60))


class BinanceFeed:
    """
    Subscribes to:
      - bookTicker (best bid/ask, <10ms latency)
      - aggTrade   (real-time trade stream for spot price)
      - kline_5m   (5-minute candle stream)

    Exposes `state` for other components to read (lock-free snapshot).
    """

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol.lower()
        self.state = BinanceState()
        self._running = False

    # ── bootstrap ────────────────────────────────────────────────────────────

    async def bootstrap_klines(self, limit: int = 60) -> None:
        url = f"{BINANCE_REST}{KLINES_ENDPOINT}"
        params = {"symbol": self.symbol.upper(), "interval": "5m", "limit": limit}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
        for row in data:
            k = Kline(
                open_time=row[0],
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                close_time=row[6],
                quote_volume=float(row[7]),
                taker_buy_base=float(row[9]),
                taker_buy_quote=float(row[10]),
            )
            self.state.klines.append(k)

    # ── WebSocket streams ─────────────────────────────────────────────────────

    async def _stream(self) -> None:
        streams = f"{self.symbol}@bookTicker/{self.symbol}@aggTrade/{self.symbol}@kline_5m"
        uri = f"{BINANCE_WS}/{streams}"
        backoff = 1
        while self._running:
            try:
                async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                    backoff = 1
                    async for raw in ws:
                        if not self._running:
                            return
                        self._handle(json.loads(raw))
            except Exception:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _handle(self, msg: dict) -> None:
        event = msg.get("e") or msg.get("stream", "").split("@")[-1]

        if event == "bookTicker" or "b" in msg and "a" in msg and "e" not in msg:
            # Combined stream wraps in {"stream":..., "data":{...}}
            data = msg.get("data", msg)
            self.state.bid = float(data.get("b", self.state.bid))
            self.state.ask = float(data.get("a", self.state.ask))
            mid = (self.state.bid + self.state.ask) / 2
            if mid > 0:
                self.state.spot_price = mid
                self.state.last_update_ts = time.time()

        elif event == "aggTrade":
            data = msg.get("data", msg)
            self.state.last_trade_price = float(data["p"])
            self.state.last_trade_qty = float(data["q"])
            self.state.spot_price = self.state.last_trade_price
            self.state.last_update_ts = time.time()

        elif event == "kline":
            data = msg.get("data", msg)
            k_raw = data["k"]
            k = Kline(
                open_time=k_raw["t"],
                open=float(k_raw["o"]),
                high=float(k_raw["h"]),
                low=float(k_raw["l"]),
                close=float(k_raw["c"]),
                volume=float(k_raw["v"]),
                close_time=k_raw["T"],
                quote_volume=float(k_raw["q"]),
                taker_buy_base=float(k_raw["V"]),
                taker_buy_quote=float(k_raw["Q"]),
                closed=k_raw["x"],
            )
            # Replace last kline if same candle, else append when closed
            if self.state.klines and self.state.klines[-1].open_time == k.open_time:
                self.state.klines[-1] = k
            elif k.closed:
                self.state.klines.append(k)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        await self.bootstrap_klines()
        asyncio.create_task(self._stream())

    async def stop(self) -> None:
        self._running = False

    # ── derived metrics ───────────────────────────────────────────────────────

    def momentum_signals(self, lookbacks: tuple[int, ...] = (1, 3, 6, 12)) -> dict[str, float]:
        """Return log-returns over N closed klines as sentiment values in [-1, 1]."""
        closes = [k.close for k in self.state.klines if k.closed]
        if len(closes) < max(lookbacks) + 1:
            return {}
        signals = {}
        for lb in lookbacks:
            ret = np.log(closes[-1] / closes[-1 - lb])
            signals[f"mom_{lb}"] = float(np.tanh(ret * 50))   # scale to ±1
        return signals

    def volume_signals(self) -> dict[str, float]:
        """Buy/sell volume ratio and volume surge vs 20-bar average."""
        klines = [k for k in self.state.klines if k.closed]
        if len(klines) < 20:
            return {}
        recent = klines[-1]
        sell_vol = recent.volume - recent.taker_buy_base
        bsratio = (recent.taker_buy_base - sell_vol) / (recent.volume + 1e-6)

        vols = np.array([k.volume for k in klines[-20:]])
        surge = (vols[-1] - vols[:-1].mean()) / (vols[:-1].std() + 1e-6)

        vwap_prices = np.array([k.close * k.volume for k in klines[-20:]])
        vwap_vols = np.array([k.volume for k in klines[-20:]])
        vwap = vwap_prices.sum() / (vwap_vols.sum() + 1e-6)
        vwap_dev = (self.state.spot_price - vwap) / (vwap + 1e-6)

        return {
            "bs_ratio": float(np.tanh(bsratio * 3)),
            "vol_surge": float(np.tanh(surge * 0.5)),
            "vwap_dev": float(np.tanh(vwap_dev * 100)),
        }

    def rsi(self, period: int = 14) -> Optional[float]:
        closes = [k.close for k in self.state.klines if k.closed]
        if len(closes) < period + 1:
            return None
        deltas = np.diff(closes[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = gains.mean()
        avg_loss = losses.mean() + 1e-10
        rs = avg_gain / avg_loss
        rsi_val = 100 - 100 / (1 + rs)
        # Map RSI to sentiment: 70+ = strong bull, 30- = strong bear
        return float(np.tanh((rsi_val - 50) / 20))

    def macd_signal(self) -> Optional[float]:
        closes = np.array([k.close for k in self.state.klines if k.closed])
        if len(closes) < 26:
            return None

        def ema(arr: np.ndarray, span: int) -> float:
            alpha = 2 / (span + 1)
            v = arr[0]
            for x in arr[1:]:
                v = alpha * x + (1 - alpha) * v
            return v

        e12 = ema(closes[-26:], 12)
        e26 = ema(closes[-26:], 26)
        macd = e12 - e26
        return float(np.tanh(macd / (closes[-1] * 0.001)))
