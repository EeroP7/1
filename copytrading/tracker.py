"""
Leaderboard poller + activity watcher.

Fetches the top-N Polymarket wallets by all-time PNL, then polls each
wallet's recent activity every COPY_POLL_INTERVAL seconds.  New trades
are placed onto an asyncio.Queue for the CopyEngine to consume.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from config import (
    POLY_DATA_API, COPY_TOP_N, COPY_LEADERBOARD_WINDOW,
    COPY_POLL_INTERVAL, COPY_LEADERBOARD_REFRESH, COPY_MIN_TRADE_USD,
)

log = logging.getLogger(__name__)


@dataclass
class WalletInfo:
    address: str          # proxyWallet (0x...)
    username: str
    pnl: float
    volume: float
    rank: int


@dataclass
class CopySignal:
    """A new trade detected on a tracked wallet."""
    source_wallet: str    # wallet that placed the trade
    source_username: str
    source_rank: int
    condition_id: str     # Polymarket market condition ID
    token_id: str         # YES or NO token asset ID
    side: str             # BUY or SELL
    price: float          # fill price (0-1)
    size_usd: float       # USD size of the original trade
    outcome: str          # "Yes" or "No"
    market_title: str
    timestamp: int        # unix ms


class WalletTracker:
    """
    Background service that:
      1. Fetches leaderboard top-N wallets (refreshes hourly)
      2. Polls each wallet's activity every COPY_POLL_INTERVAL seconds
      3. Pushes CopySignal onto queue for any new BUY trade seen
    """

    def __init__(self, signal_queue: asyncio.Queue) -> None:
        self._queue    = signal_queue
        self._wallets: list[WalletInfo] = []
        self._seen: dict[str, int] = {}   # txHash → timestamp, dedup filter
        self._session: Optional[aiohttp.ClientSession] = None
        self._task: Optional[asyncio.Task] = None

    # ── public ────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(base_url=POLY_DATA_API)
        self._task = asyncio.create_task(self._run())
        log.info("WalletTracker started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._session:
            await self._session.close()

    @property
    def wallets(self) -> list[WalletInfo]:
        return list(self._wallets)

    # ── main loop ─────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        last_leaderboard_fetch = 0.0
        # stagger per-wallet polls so we don't blast all at once
        wallet_last_poll: dict[str, float] = {}

        while True:
            try:
                # refresh leaderboard hourly
                if time.time() - last_leaderboard_fetch > COPY_LEADERBOARD_REFRESH:
                    await self._fetch_leaderboard()
                    last_leaderboard_fetch = time.time()

                # poll each wallet, staggered
                for wallet in self._wallets:
                    last = wallet_last_poll.get(wallet.address, 0)
                    if time.time() - last >= COPY_POLL_INTERVAL:
                        await self._poll_wallet(wallet)
                        wallet_last_poll[wallet.address] = time.time()
                        # small gap between wallets to be polite to the API
                        await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(f"WalletTracker error: {exc}")

            await asyncio.sleep(1)

    # ── leaderboard ───────────────────────────────────────────────────────────

    async def _fetch_leaderboard(self) -> None:
        params = {
            "timePeriod": COPY_LEADERBOARD_WINDOW,
            "orderBy":    "PNL",
            "limit":      COPY_TOP_N,
            "offset":     0,
            "category":   "OVERALL",
        }
        try:
            async with self._session.get("/v1/leaderboard", params=params) as r:
                r.raise_for_status()
                entries = await r.json()

            wallets = []
            for entry in entries:
                wallets.append(WalletInfo(
                    address=entry.get("proxyWallet", ""),
                    username=entry.get("userName") or entry.get("pseudonym") or "anon",
                    pnl=float(entry.get("pnl", 0)),
                    volume=float(entry.get("vol", 0)),
                    rank=int(entry.get("rank", 0)),
                ))
            self._wallets = [w for w in wallets if w.address]
            log.info(f"Leaderboard updated: {len(self._wallets)} wallets tracked")

        except Exception as exc:
            log.warning(f"Leaderboard fetch failed: {exc}")

    # ── activity polling ──────────────────────────────────────────────────────

    async def _poll_wallet(self, wallet: WalletInfo) -> None:
        params = {
            "user":          wallet.address,
            "limit":         20,
            "type":          "TRADE",
            "sortBy":        "TIMESTAMP",
            "sortDirection": "DESC",
        }
        try:
            async with self._session.get("/activity", params=params) as r:
                if r.status != 200:
                    return
                trades = await r.json()

            for trade in trades:
                tx_hash = trade.get("transactionHash", "")
                if not tx_hash or tx_hash in self._seen:
                    continue

                ts = int(trade.get("timestamp", 0))
                # ignore trades older than 2× poll interval (already missed)
                if time.time() - ts > COPY_POLL_INTERVAL * 2:
                    self._seen[tx_hash] = ts
                    continue

                size_usd = float(trade.get("usdcSize") or
                                 float(trade.get("size", 0)) * float(trade.get("price", 0)))
                if size_usd < COPY_MIN_TRADE_USD:
                    self._seen[tx_hash] = ts
                    continue

                side = trade.get("side", "").upper()
                if side not in ("BUY", "SELL"):
                    self._seen[tx_hash] = ts
                    continue

                sig = CopySignal(
                    source_wallet=wallet.address,
                    source_username=wallet.username,
                    source_rank=wallet.rank,
                    condition_id=trade.get("conditionId", ""),
                    token_id=trade.get("asset", ""),
                    side=side,
                    price=float(trade.get("price", 0.5)),
                    size_usd=size_usd,
                    outcome=trade.get("outcome", ""),
                    market_title=trade.get("title", "")[:60],
                    timestamp=ts,
                )
                self._seen[tx_hash] = ts
                await self._queue.put(sig)
                log.info(
                    f"[{wallet.username} #{wallet.rank}] "
                    f"{side} {sig.outcome} @ {sig.price:.3f} "
                    f"${size_usd:.0f}  {sig.market_title[:40]}"
                )

        except Exception as exc:
            log.debug(f"Poll failed for {wallet.username}: {exc}")
