"""
Polymarket CLOB feed and order executor.

Uses py-clob-client to:
  - Poll best bid/ask for the BTC UP/DOWN 5MIN market
  - Detect lag vs Binance spot price
  - Place market orders within the 100ms execution window
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp

CLOB_HOST = "https://clob.polymarket.com"


@dataclass
class CLOBSnapshot:
    condition_id: str
    best_bid: float        # highest YES bid price
    best_ask: float        # lowest YES ask price
    mid: float
    timestamp: float
    raw_up_price: float    # implied probability that BTC goes UP
    raw_down_price: float


@dataclass
class OrderResult:
    order_id: str
    side: str              # "UP" or "DOWN"
    size: float
    price: float
    filled: bool
    latency_ms: float
    dry_run: bool = False


class PolymarketCLOB:
    """
    Thin async wrapper around the Polymarket CLOB REST API.

    For live trading, initialise with a py-clob-client ClobClient.
    In DRY_RUN mode, all orders are simulated.
    """

    def __init__(
        self,
        host: str,
        condition_up: str,
        condition_down: str,
        api_key: str = "",
        api_secret: str = "",
        api_passphrase: str = "",
        private_key: str = "",
        dry_run: bool = True,
    ) -> None:
        self.host = host
        self.condition_up = condition_up
        self.condition_down = condition_down
        self.dry_run = dry_run
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase
        self._private_key = private_key
        self._session: Optional[aiohttp.ClientSession] = None
        self._clob_client = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=0.5),   # 500ms hard timeout
        )
        if not self.dry_run and self._private_key:
            self._init_clob_client()

    def _init_clob_client(self) -> None:
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds
            creds = ApiCreds(
                api_key=self._api_key,
                api_secret=self._api_secret,
                api_passphrase=self._api_passphrase,
            )
            self._clob_client = ClobClient(
                host=self.host,
                key=self._private_key,
                chain_id=137,       # Polygon
                creds=creds,
            )
        except ImportError:
            pass

    async def stop(self) -> None:
        if self._session:
            await self._session.close()

    # ── price feed ────────────────────────────────────────────────────────────

    async def get_snapshot(self) -> Optional[CLOBSnapshot]:
        """Fetch best bid/ask for both legs of the BTC 5MIN market."""
        if not self._session:
            return None
        try:
            # Orderbook endpoint: /book?token_id=<condition_id>
            up_book, down_book = await asyncio.gather(
                self._fetch_book(self.condition_up),
                self._fetch_book(self.condition_down),
            )
            if not up_book or not down_book:
                return None

            now = time.time()
            up_mid = (up_book["best_bid"] + up_book["best_ask"]) / 2
            down_mid = (down_book["best_bid"] + down_book["best_ask"]) / 2

            return CLOBSnapshot(
                condition_id=self.condition_up,
                best_bid=up_book["best_bid"],
                best_ask=up_book["best_ask"],
                mid=up_mid,
                timestamp=now,
                raw_up_price=up_mid,
                raw_down_price=down_mid,
            )
        except Exception:
            return None

    async def _fetch_book(self, token_id: str) -> Optional[dict]:
        if not token_id:
            # Return synthetic stub for dry-run testing without real market IDs
            import random
            mid = 0.48 + random.uniform(-0.03, 0.03)
            spread = 0.01
            return {"best_bid": mid - spread / 2, "best_ask": mid + spread / 2}
        try:
            url = f"{self.host}/book"
            params = {"token_id": token_id}
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 1.0
            return {"best_bid": best_bid, "best_ask": best_ask}
        except Exception:
            return None

    # ── execution ─────────────────────────────────────────────────────────────

    async def place_order(
        self,
        side: str,          # "UP" or "DOWN"
        size_usdc: float,
        limit_price: float,
    ) -> OrderResult:
        """
        Place a limit order on the relevant leg.
        side="UP"  → buy YES on the UP condition
        side="DOWN"→ buy YES on the DOWN condition
        """
        t0 = time.perf_counter()
        condition = self.condition_up if side == "UP" else self.condition_down

        if self.dry_run or not self._clob_client:
            latency = (time.perf_counter() - t0) * 1000
            return OrderResult(
                order_id=f"dry-{int(time.time()*1000)}",
                side=side,
                size=size_usdc,
                price=limit_price,
                filled=True,
                latency_ms=latency,
                dry_run=True,
            )

        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            args = OrderArgs(
                token_id=condition,
                price=limit_price,
                size=size_usdc,
                side="BUY",
            )
            resp = self._clob_client.create_and_post_order(args)
            latency = (time.perf_counter() - t0) * 1000
            return OrderResult(
                order_id=resp.get("orderID", "unknown"),
                side=side,
                size=size_usdc,
                price=limit_price,
                filled=resp.get("status") == "matched",
                latency_ms=latency,
            )
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000
            return OrderResult(
                order_id="error",
                side=side,
                size=size_usdc,
                price=limit_price,
                filled=False,
                latency_ms=latency,
            )
