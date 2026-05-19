"""
Polymarket CLOB interface.

Wraps py-clob-client to:
  - Discover the current BTC UP/DOWN 5MIN market
  - Poll order-book prices for YES and NO tokens
  - Submit limit/market orders
  - Track fills and open positions
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    ApiCreds, OrderArgs, OrderType, PartialCreateOrderOptions,
)
from py_clob_client.order_builder.constants import BUY, SELL

from config import (
    POLY_HOST, POLY_PRIVATE_KEY, POLY_API_KEY, POLY_API_SECRET,
    POLY_PASSPHRASE, POLY_CHAIN_ID,
)


@dataclass
class MarketState:
    condition_id: str
    yes_token_id: str
    no_token_id: str
    yes_bid: float        # best bid for YES token
    yes_ask: float        # best ask
    no_bid: float
    no_ask: float
    yes_bid_size: float
    yes_ask_size: float
    no_bid_size: float
    no_ask_size: float
    mid_yes: float        # (yes_bid + yes_ask) / 2
    mid_no: float
    timestamp_ms: int


@dataclass
class OpenPosition:
    token_id: str
    side: str             # "YES" or "NO"
    size: float
    entry_price: float
    entry_time_ms: int
    order_id: str


class PolymarketClient:
    """
    Async wrapper around the synchronous py-clob-client.
    All CLOB calls are dispatched to a thread pool to avoid blocking the event loop.
    """

    BTC_5MIN_SLUG = "will-btc-price-increase-in-the-next-5-minutes"

    def __init__(self) -> None:
        creds = ApiCreds(
            api_key=POLY_API_KEY,
            api_secret=POLY_API_SECRET,
            api_passphrase=POLY_PASSPHRASE,
        )
        self._client = ClobClient(
            host=POLY_HOST,
            chain_id=POLY_CHAIN_ID,
            key=POLY_PRIVATE_KEY,
            creds=creds,
        )
        self._condition_id: Optional[str] = None
        self._yes_token_id: Optional[str] = None
        self._no_token_id: Optional[str] = None
        self._loop = asyncio.get_event_loop()
        self._open_positions: dict[str, OpenPosition] = {}

    # ── market discovery ──────────────────────────────────────────────────────

    async def discover_market(self) -> bool:
        """
        Searches for the active BTC UP/DOWN 5MIN market.
        Returns True if found.
        """
        try:
            markets = await self._run(
                self._client.get_markets,
                next_cursor="MA==",
            )
            for market in markets.get("data", []):
                slug = market.get("market_slug", "")
                if "btc" in slug.lower() and "5" in slug and "minute" in slug.lower():
                    self._condition_id = market["condition_id"]
                    tokens = market.get("tokens", [])
                    for tok in tokens:
                        if tok.get("outcome", "").upper() == "YES":
                            self._yes_token_id = tok["token_id"]
                        elif tok.get("outcome", "").upper() == "NO":
                            self._no_token_id = tok["token_id"]
                    return self._yes_token_id is not None
        except Exception:
            pass
        return False

    # ── order book polling ────────────────────────────────────────────────────

    async def get_market_state(self) -> Optional[MarketState]:
        if not self._yes_token_id or not self._no_token_id:
            return None
        try:
            yes_book, no_book = await asyncio.gather(
                self._run(self._client.get_order_book, self._yes_token_id),
                self._run(self._client.get_order_book, self._no_token_id),
            )
            yes_bids = yes_book.get("bids", [])
            yes_asks = yes_book.get("asks", [])
            no_bids  = no_book.get("bids", [])
            no_asks  = no_book.get("asks", [])

            yes_bid = float(yes_bids[0]["price"]) if yes_bids else 0.0
            yes_ask = float(yes_asks[0]["price"]) if yes_asks else 1.0
            no_bid  = float(no_bids[0]["price"])  if no_bids  else 0.0
            no_ask  = float(no_asks[0]["price"])  if no_asks  else 1.0

            yes_bid_sz = float(yes_bids[0]["size"]) if yes_bids else 0.0
            yes_ask_sz = float(yes_asks[0]["size"]) if yes_asks else 0.0
            no_bid_sz  = float(no_bids[0]["size"])  if no_bids  else 0.0
            no_ask_sz  = float(no_asks[0]["size"])  if no_asks  else 0.0

            return MarketState(
                condition_id=self._condition_id,
                yes_token_id=self._yes_token_id,
                no_token_id=self._no_token_id,
                yes_bid=yes_bid, yes_ask=yes_ask,
                no_bid=no_bid,   no_ask=no_ask,
                yes_bid_size=yes_bid_sz, yes_ask_size=yes_ask_sz,
                no_bid_size=no_bid_sz,   no_ask_size=no_ask_sz,
                mid_yes=(yes_bid + yes_ask) / 2,
                mid_no=(no_bid + no_ask) / 2,
                timestamp_ms=int(time.time() * 1000),
            )
        except Exception:
            return None

    # ── order execution ───────────────────────────────────────────────────────

    async def place_order(
        self,
        token_id: str,
        side: str,          # BUY or SELL
        size: float,
        price: float,
        order_type: OrderType = OrderType.GTC,
    ) -> Optional[str]:
        """Places a limit order. Returns order_id or None on failure."""
        try:
            args = OrderArgs(
                token_id=token_id,
                price=round(price, 4),
                size=round(size, 2),
                side=BUY if side == "BUY" else SELL,
            )
            opts = PartialCreateOrderOptions(tick_size=0.01)
            signed_order = await self._run(
                self._client.create_order, args, opts
            )
            resp = await self._run(
                self._client.post_order, signed_order, order_type
            )
            return resp.get("orderID")
        except Exception:
            return None

    async def cancel_order(self, order_id: str) -> bool:
        try:
            await self._run(self._client.cancel, order_id)
            return True
        except Exception:
            return False

    async def get_order(self, order_id: str) -> Optional[dict]:
        try:
            return await self._run(self._client.get_order, order_id)
        except Exception:
            return None

    # ── position helpers ──────────────────────────────────────────────────────

    def record_position(self, pos: OpenPosition) -> None:
        self._open_positions[pos.order_id] = pos

    def get_positions(self) -> list[OpenPosition]:
        return list(self._open_positions.values())

    def close_position(self, order_id: str) -> None:
        self._open_positions.pop(order_id, None)

    # ── util ──────────────────────────────────────────────────────────────────

    async def _run(self, fn, *args, **kwargs):
        return await self._loop.run_in_executor(None, lambda: fn(*args, **kwargs))
