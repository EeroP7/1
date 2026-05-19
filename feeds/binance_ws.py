"""
Binance WebSocket feed: real-time trade ticks + 5-minute klines.

Maintains a rolling window of klines and emits a BtcSnapshot
on every tick so downstream consumers always have fresh data.
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from collections import deque
from typing import Deque, Optional

import aiohttp
import websockets

from config import (
    BINANCE_WS_BASE, BINANCE_REST, BTC_SYMBOL,
    KLINE_INTERVAL, KLINE_LIMIT,
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
    taker_buy_volume: float   # aggressive buy volume
    taker_sell_volume: float  # = volume - taker_buy


@dataclass
class BtcSnapshot:
    price: float
    bid: float
    ask: float
    bid_qty: float
    ask_qty: float
    timestamp_ms: int
    klines: list[Kline]       # most-recent first
    buy_ratio: float          # taker buy / total volume over last kline
    order_flow_imbalance: float  # (bid_qty - ask_qty) / (bid_qty + ask_qty)


class BinanceFeed:
    """
    Subscribes to:
      • <symbol>@bookTicker   – best bid/ask with quantities
      • <symbol>@kline_5m     – completed + live 5-min candles

    Call `start()` to launch the background tasks, then await `get_snapshot()`
    for the latest BtcSnapshot.
    """

    def __init__(self, symbol: str = BTC_SYMBOL) -> None:
        self._symbol = symbol
        self._klines: Deque[Kline] = deque(maxlen=KLINE_LIMIT)
        self._price: float = 0.0
        self._bid: float = 0.0
        self._ask: float = 0.0
        self._bid_qty: float = 0.0
        self._ask_qty: float = 0.0
        self._ts: int = 0
        self._ready = asyncio.Event()
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []

    # ── public ────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await self._seed_klines()
        self._tasks.append(asyncio.create_task(self._run_ws()))

    async def wait_ready(self) -> None:
        await self._ready.wait()

    async def get_snapshot(self) -> Optional[BtcSnapshot]:
        async with self._lock:
            if not self._klines or self._price == 0:
                return None
            klines = list(self._klines)
            last = klines[-1]
            buy_ratio = (
                last.taker_buy_volume / last.volume
                if last.volume > 0 else 0.5
            )
            denom = self._bid_qty + self._ask_qty
            ofi = (
                (self._bid_qty - self._ask_qty) / denom
                if denom > 0 else 0.0
            )
            return BtcSnapshot(
                price=self._price,
                bid=self._bid,
                ask=self._ask,
                bid_qty=self._bid_qty,
                ask_qty=self._ask_qty,
                timestamp_ms=self._ts,
                klines=list(reversed(klines)),   # most-recent first
                buy_ratio=buy_ratio,
                order_flow_imbalance=ofi,
            )

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()

    # ── seed historical klines ────────────────────────────────────────────────

    async def _seed_klines(self) -> None:
        url = (
            f"{BINANCE_REST}/api/v3/klines"
            f"?symbol={self._symbol.upper()}&interval={KLINE_INTERVAL}"
            f"&limit={KLINE_LIMIT}"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        async with self._lock:
            for row in data:
                self._klines.append(self._parse_kline_rest(row))

    @staticmethod
    def _parse_kline_rest(row: list) -> Kline:
        vol  = float(row[5])
        tbuy = float(row[9])
        return Kline(
            open_time=row[0],
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=vol,
            close_time=row[6],
            quote_volume=float(row[7]),
            num_trades=int(row[8]),
            taker_buy_volume=tbuy,
            taker_sell_volume=vol - tbuy,
        )

    # ── WebSocket handler ─────────────────────────────────────────────────────

    async def _run_ws(self) -> None:
        streams = (
            f"{self._symbol}@bookTicker"
            f"/{self._symbol}@kline_{KLINE_INTERVAL}"
        )
        uri = f"{BINANCE_WS_BASE}?streams={streams}"
        backoff = 1
        while True:
            try:
                async with websockets.connect(uri, ping_interval=20) as ws:
                    backoff = 1
                    async for raw in ws:
                        msg = json.loads(raw)
                        stream = msg.get("stream", "")
                        data   = msg.get("data", {})
                        if "bookTicker" in stream:
                            await self._handle_book(data)
                        elif "kline" in stream:
                            await self._handle_kline(data)
            except (websockets.WebSocketException, OSError):
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _handle_book(self, data: dict) -> None:
        async with self._lock:
            self._bid     = float(data["b"])
            self._ask     = float(data["a"])
            self._bid_qty = float(data["B"])
            self._ask_qty = float(data["A"])
            self._price   = (self._bid + self._ask) / 2
            self._ts      = int(time.time() * 1000)
            self._ready.set()

    async def _handle_kline(self, data: dict) -> None:
        k = data["k"]
        vol  = float(k["v"])
        tbuy = float(k["V"])
        kline = Kline(
            open_time=k["t"],
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=vol,
            close_time=k["T"],
            quote_volume=float(k["q"]),
            num_trades=int(k["n"]),
            taker_buy_volume=tbuy,
            taker_sell_volume=vol - tbuy,
        )
        async with self._lock:
            # replace current open candle or append closed candle
            if self._klines and self._klines[-1].open_time == kline.open_time:
                self._klines[-1] = kline
            else:
                self._klines.append(kline)
