"""
Binance WebSocket feed: spot order book, 5M klines, aggTrades,
and Binance Futures mark price.

The futures mark price is the canonical BTC reference price that
Polymarket binary markets settle against — it's the primary input
for the arbitrage gap calculation.

Three parallel WebSocket connections:
  1. Spot combined stream  — bookTicker + depth5@100ms + kline_5m
  2. Spot aggTrade stream  — individual aggressive trades (flow direction)
  3. Futures stream        — markPrice@1s (settlement reference)
"""
import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

import aiohttp
import websockets

from config import (
    BINANCE_WS_BASE, BINANCE_FUTURES_WS, BINANCE_REST, BINANCE_FUTURES_REST,
    BTC_SYMBOL, KLINE_INTERVAL, KLINE_LIMIT, DEPTH_LEVELS, AGG_TRADE_WINDOW,
)


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
    num_trades: int
    taker_buy_volume: float
    taker_sell_volume: float


@dataclass
class DepthLevel:
    price: float
    qty: float


@dataclass
class BtcSnapshot:
    # ── Spot prices ───────────────────────────────────────────────────────────
    price: float               # spot mid (bid+ask)/2
    bid: float
    ask: float
    bid_qty: float
    ask_qty: float

    # ── Futures reference ─────────────────────────────────────────────────────
    mark_price: float          # Binance perpetual futures mark price
    funding_rate: float        # current funding rate (+ = longs pay shorts)
    mark_price_ts: int         # ms timestamp of last mark price update

    # ── Order book depth ─────────────────────────────────────────────────────
    bids: list[DepthLevel]     # top-N bid levels, best first
    asks: list[DepthLevel]     # top-N ask levels, best first

    # ── Trade flow ────────────────────────────────────────────────────────────
    agg_buy_vol: float         # aggressive buy volume in last AGG_TRADE_WINDOW s
    agg_sell_vol: float        # aggressive sell volume
    flow_ratio: float          # buy_vol / (buy_vol + sell_vol)

    # ── Klines + derived ─────────────────────────────────────────────────────
    timestamp_ms: int
    klines: list[Kline]        # most-recent first
    buy_ratio: float           # taker buy / total for last completed kline
    order_flow_imbalance: float  # (bid_qty - ask_qty) / total

    # ── Arbitrage helpers ─────────────────────────────────────────────────────
    @property
    def mark_spot_spread(self) -> float:
        """Futures mark price premium over spot (positive = futures premium)."""
        return (self.mark_price - self.price) / self.price if self.price else 0.0

    @property
    def effective_price(self) -> float:
        """Best single-price reference for arbitrage: futures mark price."""
        return self.mark_price if self.mark_price > 0 else self.price


class BinanceFeed:
    """
    Maintains three parallel WebSocket connections and exposes a unified
    BtcSnapshot on every tick.
    """

    def __init__(self, symbol: str = BTC_SYMBOL) -> None:
        self._sym = symbol
        self._klines: Deque[Kline] = deque(maxlen=KLINE_LIMIT)

        # Spot book
        self._bid = self._ask = self._bid_qty = self._ask_qty = 0.0
        self._bids: list[DepthLevel] = []
        self._asks: list[DepthLevel] = []

        # Futures mark
        self._mark_price: float = 0.0
        self._funding_rate: float = 0.0
        self._mark_ts: int = 0

        # aggTrade ring buffer: (timestamp_ms, buy_vol, sell_vol)
        self._trades: Deque[tuple[int, float, float]] = deque(maxlen=5000)

        self._ts: int = 0
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []

    # ── public ────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await self._seed_klines()
        self._tasks = [
            asyncio.create_task(self._run_spot_ws()),
            asyncio.create_task(self._run_agg_trade_ws()),
            asyncio.create_task(self._run_futures_ws()),
        ]

    async def wait_ready(self) -> None:
        await self._ready.wait()

    async def get_snapshot(self) -> Optional[BtcSnapshot]:
        async with self._lock:
            if not self._klines or self._bid == 0:
                return None

            klines = list(self._klines)
            last_k = klines[-1]
            buy_ratio = (
                last_k.taker_buy_volume / last_k.volume
                if last_k.volume > 0 else 0.5
            )
            denom = self._bid_qty + self._ask_qty
            ofi = (self._bid_qty - self._ask_qty) / denom if denom > 0 else 0.0

            # aggTrade flow in last AGG_TRADE_WINDOW seconds
            cutoff = self._ts - AGG_TRADE_WINDOW * 1000
            buy_vol = sell_vol = 0.0
            for ts_ms, bv, sv in self._trades:
                if ts_ms >= cutoff:
                    buy_vol += bv
                    sell_vol += sv
            total_flow = buy_vol + sell_vol
            flow_ratio = buy_vol / total_flow if total_flow > 0 else 0.5

            price = (self._bid + self._ask) / 2

            return BtcSnapshot(
                price=price,
                bid=self._bid, ask=self._ask,
                bid_qty=self._bid_qty, ask_qty=self._ask_qty,
                mark_price=self._mark_price,
                funding_rate=self._funding_rate,
                mark_price_ts=self._mark_ts,
                bids=list(self._bids),
                asks=list(self._asks),
                agg_buy_vol=buy_vol,
                agg_sell_vol=sell_vol,
                flow_ratio=flow_ratio,
                timestamp_ms=self._ts,
                klines=list(reversed(klines)),
                buy_ratio=buy_ratio,
                order_flow_imbalance=ofi,
            )

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()

    # ── historical seed ───────────────────────────────────────────────────────

    async def _seed_klines(self) -> None:
        url = (
            f"{BINANCE_REST}/api/v3/klines"
            f"?symbol={self._sym.upper()}&interval={KLINE_INTERVAL}"
            f"&limit={KLINE_LIMIT}"
        )
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                data = await r.json()
        async with self._lock:
            for row in data:
                self._klines.append(_parse_kline_rest(row))

    # ── WebSocket: spot (bookTicker + depth + kline) ──────────────────────────

    async def _run_spot_ws(self) -> None:
        sym = self._sym
        streams = (
            f"{sym}@bookTicker"
            f"/{sym}@depth{DEPTH_LEVELS}@100ms"
            f"/{sym}@kline_{KLINE_INTERVAL}"
        )
        uri = f"{BINANCE_WS_BASE}?streams={streams}"
        await _ws_loop(uri, self._handle_spot)

    async def _handle_spot(self, msg: dict) -> None:
        stream = msg.get("stream", "")
        data   = msg.get("data", {})
        if "bookTicker" in stream:
            async with self._lock:
                self._bid     = float(data["b"])
                self._ask     = float(data["a"])
                self._bid_qty = float(data["B"])
                self._ask_qty = float(data["A"])
                self._ts = int(time.time() * 1000)
                self._ready.set()
        elif "depth" in stream:
            async with self._lock:
                self._bids = [
                    DepthLevel(float(p), float(q))
                    for p, q in data.get("bids", [])[:DEPTH_LEVELS]
                ]
                self._asks = [
                    DepthLevel(float(p), float(q))
                    for p, q in data.get("asks", [])[:DEPTH_LEVELS]
                ]
        elif "kline" in stream:
            k = data["k"]
            vol  = float(k["v"])
            tbuy = float(k["V"])
            kline = Kline(
                open_time=k["t"], open=float(k["o"]),
                high=float(k["h"]), low=float(k["l"]),
                close=float(k["c"]), volume=vol,
                close_time=k["T"], quote_volume=float(k["q"]),
                num_trades=int(k["n"]),
                taker_buy_volume=tbuy, taker_sell_volume=vol - tbuy,
            )
            async with self._lock:
                if self._klines and self._klines[-1].open_time == kline.open_time:
                    self._klines[-1] = kline
                else:
                    self._klines.append(kline)

    # ── WebSocket: aggTrade (spot trade direction) ────────────────────────────

    async def _run_agg_trade_ws(self) -> None:
        uri = f"{BINANCE_WS_BASE}?streams={self._sym}@aggTrade"
        await _ws_loop(uri, self._handle_agg_trade)

    async def _handle_agg_trade(self, msg: dict) -> None:
        data = msg.get("data", {})
        qty = float(data.get("q", 0))
        is_sell = bool(data.get("m", False))  # m=True means buyer is market maker → seller aggressor
        ts = int(data.get("T", time.time() * 1000))
        async with self._lock:
            if is_sell:
                self._trades.append((ts, 0.0, qty))
            else:
                self._trades.append((ts, qty, 0.0))

    # ── WebSocket: Binance Futures mark price ─────────────────────────────────

    async def _run_futures_ws(self) -> None:
        uri = f"{BINANCE_FUTURES_WS}?streams={self._sym}@markPrice@1s"
        await _ws_loop(uri, self._handle_mark_price)

    async def _handle_mark_price(self, msg: dict) -> None:
        data = msg.get("data", {})
        async with self._lock:
            self._mark_price   = float(data.get("p", self._mark_price))
            self._funding_rate = float(data.get("r", 0))
            self._mark_ts      = int(data.get("T", time.time() * 1000))


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_kline_rest(row: list) -> Kline:
    vol  = float(row[5])
    tbuy = float(row[9])
    return Kline(
        open_time=row[0], open=float(row[1]),
        high=float(row[2]), low=float(row[3]),
        close=float(row[4]), volume=vol,
        close_time=row[6], quote_volume=float(row[7]),
        num_trades=int(row[8]),
        taker_buy_volume=tbuy, taker_sell_volume=vol - tbuy,
    )


async def _ws_loop(uri: str, handler) -> None:
    backoff = 1
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                backoff = 1
                async for raw in ws:
                    await handler(json.loads(raw))
        except (websockets.WebSocketException, OSError):
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
