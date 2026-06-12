"""
Polymarket CLOB interface.

Wraps py-clob-client to:
  - Discover the current BTC UP/DOWN 5MIN market
  - Poll order-book prices for YES and NO tokens
  - Submit limit/market orders
  - Track fills and open positions
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiohttp

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
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

    GAMMA_HOST = "https://gamma-api.polymarket.com"

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
        self.market_question: str = ""
        self._market_end_ts: float = 0.0
        self._loop = asyncio.get_event_loop()
        self._open_positions: dict[str, OpenPosition] = {}
        self.last_error: str = ""

    # ── market discovery ──────────────────────────────────────────────────────

    async def discover_market(self) -> bool:
        """
        Finds the live Bitcoin Up-or-Down market via the public Gamma API.

        The up/down series is recurring (new market every window), so we sort
        active markets by endDate ascending and take the soonest-ending one
        whose question matches — that's the current window.
        """
        now = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GAMMA_HOST}/markets",
                    params={
                        "active":       "true",
                        "closed":       "false",
                        "order":        "endDate",
                        "ascending":    "true",
                        "limit":        "300",
                        # only windows that are still open (skips stale listings)
                        "end_date_min": datetime.utcfromtimestamp(now).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"),
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    resp.raise_for_status()
                    markets = await resp.json()
        except Exception:
            return False

        for m in markets if isinstance(markets, list) else []:
            text = f"{m.get('question', '')} {m.get('slug', '')}".lower()
            if "bitcoin" not in text and "btc" not in text:
                continue
            if "up or down" not in text and "up-or-down" not in text:
                continue
            # strictly the 5-min series: question has a time RANGE like
            # "6:15AM-6:20AM ET" — hourly markets ("7AM ET") have no range
            if "am-" not in text and "pm-" not in text:
                continue
            try:
                token_ids = m.get("clobTokenIds") or "[]"
                if isinstance(token_ids, str):
                    token_ids = json.loads(token_ids)
                if len(token_ids) < 2:
                    continue
                outcomes = m.get("outcomes") or '["Yes", "No"]'
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)

                # first outcome is the bullish one ("Up"/"Yes")
                first_bull = str(outcomes[0]).lower() in ("yes", "up")
                self._yes_token_id = token_ids[0] if first_bull else token_ids[1]
                self._no_token_id  = token_ids[1] if first_bull else token_ids[0]
                self._condition_id = m.get("conditionId", "")
                self.market_question = m.get("question", "")

                end = m.get("endDate") or ""
                try:
                    end_ts = datetime.fromisoformat(
                        end.replace("Z", "+00:00")
                    ).timestamp()
                except ValueError:
                    continue
                if end_ts <= now:        # window already closed → not live
                    continue
                self._market_end_ts = end_ts
                return True
            except Exception:
                continue
        return False

    def market_ended(self) -> bool:
        """True once the discovered market's window has closed."""
        return bool(self._market_end_ts) and time.time() > self._market_end_ts

    # ── order book polling ────────────────────────────────────────────────────

    @staticmethod
    def _levels(book, side: str) -> list[tuple[float, float]]:
        """Normalise order-book levels to (price, size) — the CLOB client
        returns OrderBookSummary objects, raw REST returns dicts."""
        raw = (book.get(side, []) if isinstance(book, dict)
               else getattr(book, side, None)) or []
        out = []
        for lvl in raw:
            if isinstance(lvl, dict):
                out.append((float(lvl["price"]), float(lvl["size"])))
            else:
                out.append((float(lvl.price), float(lvl.size)))
        return out

    async def get_market_state(self) -> Optional[MarketState]:
        if not self._yes_token_id or not self._no_token_id:
            return None
        try:
            yes_book, no_book = await asyncio.gather(
                self._run(self._client.get_order_book, self._yes_token_id),
                self._run(self._client.get_order_book, self._no_token_id),
            )
            yes_bids = self._levels(yes_book, "bids")
            yes_asks = self._levels(yes_book, "asks")
            no_bids  = self._levels(no_book, "bids")
            no_asks  = self._levels(no_book, "asks")

            # best bid = highest price, best ask = lowest (sort order varies)
            yes_bid, yes_bid_sz = max(yes_bids, default=(0.0, 0.0))
            yes_ask, yes_ask_sz = min(yes_asks, default=(1.0, 0.0))
            no_bid,  no_bid_sz  = max(no_bids,  default=(0.0, 0.0))
            no_ask,  no_ask_sz  = min(no_asks,  default=(1.0, 0.0))

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
            # let the client resolve the market's tick size + neg-risk flag
            signed_order = await self._run(self._client.create_order, args)
            resp = await self._run(
                self._client.post_order, signed_order, order_type
            )
            order_id = resp.get("orderID")
            if not order_id:
                # API accepted the request but rejected the order — capture why
                self.last_error = str(
                    resp.get("errorMsg") or resp.get("error") or resp
                )[:120]
            return order_id
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:120]
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
