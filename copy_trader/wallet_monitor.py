"""
Monitors a set of wallet addresses for new Polymarket trades.

Polls the Polymarket data API every `poll_interval` seconds per wallet.
When a trade is detected that hasn't been seen before, it emits a
TradeSignal for the copy executor to act on.

Endpoint:
  GET https://data-api.polymarket.com/activity?user=<address>&limit=20
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import aiohttp
import structlog

log = structlog.get_logger()

DATA_API = "https://data-api.polymarket.com"


@dataclass
class TradeSignal:
    source_wallet: str
    source_name: str
    condition_id: str          # Polymarket token_id / condition_id
    market_question: str
    side: str                  # "BUY" or "SELL"
    outcome: str               # "YES" or "NO"
    price: float               # price paid (0-1)
    size_usdc: float           # notional size
    tx_hash: str
    detected_at: float = field(default_factory=time.time)

    @property
    def direction(self) -> str:
        """Simplified: BUY YES = bullish on outcome, BUY NO = bearish."""
        if self.side == "BUY" and self.outcome == "YES":
            return "LONG"
        if self.side == "BUY" and self.outcome == "NO":
            return "SHORT"
        return "EXIT"


TradeCallback = Callable[[TradeSignal], None]


class WalletMonitor:
    """
    Polls activity for a dynamic set of wallets.

    Usage:
        monitor = WalletMonitor(on_trade=my_callback)
        await monitor.start()
        monitor.watch(address, name)
        ...
        await monitor.stop()
    """

    def __init__(
        self,
        on_trade: TradeCallback,
        poll_interval: int = 30,
        min_trade_size_usdc: float = 100.0,    # ignore dust trades
    ) -> None:
        self._on_trade = on_trade
        self._poll_interval = poll_interval
        self._min_size = min_trade_size_usdc
        self._wallets: dict[str, str] = {}     # address → name
        self._seen_txs: set[str] = set()       # dedup by tx hash
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        self._running = True
        asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._session:
            await self._session.close()

    def watch(self, address: str, name: str = "") -> None:
        addr = address.lower()
        self._wallets[addr] = name or addr[:10] + "..."
        log.info("watching_wallet", address=addr, name=name)

    def unwatch(self, address: str) -> None:
        self._wallets.pop(address.lower(), None)

    @property
    def watched_count(self) -> int:
        return len(self._wallets)

    # ── polling ───────────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        while self._running:
            tasks = [
                self._poll_wallet(addr, name)
                for addr, name in list(self._wallets.items())
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(self._poll_interval)

    async def _poll_wallet(self, address: str, name: str) -> None:
        if not self._session:
            return
        url = f"{DATA_API}/activity"
        params = {"user": address, "limit": 20}
        try:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
        except Exception as exc:
            log.debug("poll_error", wallet=address, error=str(exc))
            return

        activities = data if isinstance(data, list) else data.get("data", [])
        for activity in activities:
            self._process_activity(activity, address, name)

    def _process_activity(self, raw: dict, address: str, name: str) -> None:
        tx = raw.get("transactionHash") or raw.get("id") or ""
        if not tx or tx in self._seen_txs:
            return
        self._seen_txs.add(tx)

        # Only keep recently seen (cap memory at 10k entries)
        if len(self._seen_txs) > 10_000:
            self._seen_txs = set(list(self._seen_txs)[-5_000:])

        # Parse activity type
        trade_type = raw.get("type", "").upper()
        if trade_type not in ("BUY", "SELL", "TRADE"):
            return

        size = float(raw.get("usdcSize") or raw.get("amount") or 0)
        if size < self._min_size:
            return

        price = float(raw.get("price") or 0)
        outcome = raw.get("outcome") or raw.get("side") or "YES"
        side = "BUY" if trade_type in ("BUY", "TRADE") else "SELL"

        condition_id = (
            raw.get("conditionId")
            or raw.get("tokenId")
            or raw.get("asset")
            or ""
        )
        question = raw.get("title") or raw.get("market") or "unknown market"

        signal = TradeSignal(
            source_wallet=address,
            source_name=name,
            condition_id=condition_id,
            market_question=question,
            side=side,
            outcome=outcome,
            price=price,
            size_usdc=size,
            tx_hash=tx,
        )

        log.info(
            "trade_detected",
            wallet=name,
            market=question[:60],
            side=f"{side} {outcome}",
            price=price,
            size_usdc=size,
        )
        self._on_trade(signal)
