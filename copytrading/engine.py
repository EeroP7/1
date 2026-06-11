"""
Copy-trade execution engine.

Consumes CopySignals from the queue and places mirror orders on Polymarket.
Shares the same risk budget as the BTC arbitrage engine (daily cap applies
across both strategies combined).
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from config import (
    COPY_RISK_PER_TRADE, COPY_MAX_TRADE_USD,
    COPY_MARKET_COOLDOWN, SLIPPAGE_LIMIT, DAILY_CAP_RISK,
)
from copytrading.tracker import CopySignal
from execution.engine import RiskState, TradeOutcome
from polymarket.clob_client import PolymarketClient

log = logging.getLogger(__name__)


@dataclass
class CopyTradeRecord:
    source_username: str
    source_rank: int
    market_title: str
    outcome: str
    side: str
    entry_price: float
    size: float
    size_usd: float
    order_id: Optional[str]
    timestamp: int
    skipped: bool = False
    skip_reason: str = ""


class CopyEngine:
    """
    Pulls CopySignals from a queue and mirrors them onto Polymarket,
    scaled to COPY_RISK_PER_TRADE of the shared balance.

    Guards:
      - Daily PNL cap shared with arb engine (passed in as RiskState ref)
      - Per-market cooldown: don't copy same market twice within 5 min
      - Max copy size cap: never more than COPY_MAX_TRADE_USD per trade
      - Skip SELL signals (we don't short-sell; only copy BUY entries)
      - Skip if token_id missing (incomplete trade data)
    """

    def __init__(
        self,
        clob: PolymarketClient,
        risk: RiskState,
        signal_queue: asyncio.Queue,
    ) -> None:
        self._clob   = clob
        self._risk   = risk
        self._queue  = signal_queue
        self._history: list[CopyTradeRecord] = []
        self._cooldowns: dict[str, float] = {}   # condition_id → last copy time
        self._task: Optional[asyncio.Task] = None

    @property
    def history(self) -> list[CopyTradeRecord]:
        return list(self._history)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    # ── consumer loop ─────────────────────────────────────────────────────────

    async def _run(self) -> None:
        while True:
            try:
                sig: CopySignal = await asyncio.wait_for(
                    self._queue.get(), timeout=5.0
                )
                record = await self._process(sig)
                self._history.append(record)
                if not record.skipped:
                    log.info(
                        f"COPY [{sig.source_username}] "
                        f"{sig.side} {sig.outcome} @ {sig.price:.3f} "
                        f"size=${record.size_usd:.0f}  order={record.order_id}"
                    )
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(f"CopyEngine error: {exc}")

    # ── trade processing ──────────────────────────────────────────────────────

    async def _process(self, sig: CopySignal) -> CopyTradeRecord:
        def skip(reason: str) -> CopyTradeRecord:
            return CopyTradeRecord(
                source_username=sig.source_username,
                source_rank=sig.source_rank,
                market_title=sig.market_title,
                outcome=sig.outcome,
                side=sig.side,
                entry_price=sig.price,
                size=0, size_usd=0, order_id=None,
                timestamp=sig.timestamp,
                skipped=True, skip_reason=reason,
            )

        # ── guards ────────────────────────────────────────────────────────────
        if self._risk.halted:
            return skip("risk halted")
        if self._risk.daily_pnl_pct <= -DAILY_CAP_RISK:
            return skip("daily cap hit")
        if not sig.token_id:
            return skip("no token_id")
        # only copy BUY entries (mirrors opening a position)
        if sig.side != "BUY":
            return skip("sell — skip")
        # per-market cooldown
        last_copy = self._cooldowns.get(sig.condition_id, 0)
        if time.time() - last_copy < COPY_MARKET_COOLDOWN:
            return skip(f"cooldown ({int(time.time()-last_copy)}s)")
        if sig.price <= 0 or sig.price >= 1:
            return skip("price out of range")

        # ── size calculation ──────────────────────────────────────────────────
        balance  = self._risk.balance
        size_usd = min(balance * COPY_RISK_PER_TRADE, COPY_MAX_TRADE_USD)
        size     = round(size_usd / sig.price, 2)
        if size < 1.0:
            return skip("size too small")

        # ── place order ───────────────────────────────────────────────────────
        limit_price = round(min(sig.price * (1 + SLIPPAGE_LIMIT), 0.99), 4)
        order_id = await self._clob.place_order(
            token_id=sig.token_id,
            side="BUY",
            size=size,
            price=limit_price,
        )

        self._cooldowns[sig.condition_id] = time.time()

        return CopyTradeRecord(
            source_username=sig.source_username,
            source_rank=sig.source_rank,
            market_title=sig.market_title,
            outcome=sig.outcome,
            side=sig.side,
            entry_price=sig.price,
            size=size,
            size_usd=size_usd,
            order_id=order_id,
            timestamp=sig.timestamp,
            skipped=order_id is None,
            skip_reason="" if order_id else "order placement failed",
        )
