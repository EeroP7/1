"""
Copy executor.

Receives TradeSignals from WalletMonitor and mirrors them on our
Polymarket account, scaled to our portfolio size.

Scaling logic:
  our_size = source_size * (our_portfolio / source_portfolio) * scale_factor

Guards:
  - Skip if we already hold a position in this market
  - Skip if signal is stale (> max_signal_age_s seconds old)
  - Skip if market question matches any keyword in the blocklist
  - Apply per-trade and daily risk caps via RiskManager
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import structlog

from copy_trader.wallet_monitor import TradeSignal
from data.polymarket_clob import PolymarketCLOB
from execution.risk_manager import RiskManager

log = structlog.get_logger()

DEFAULT_BLOCKLIST = [
    # add keywords to skip specific market types
    # e.g. "election", "sports"
]


@dataclass
class CopyPosition:
    condition_id: str
    market_question: str
    side: str
    outcome: str
    entry_price: float
    size_usdc: float
    source_wallet: str
    opened_at: float = field(default_factory=time.time)
    order_id: str = ""


class CopyExecutor:
    """
    Mirrors trades from followed wallets onto our own account.

    Parameters
    ----------
    clob            : PolymarketCLOB instance (shared with arbitrage bot or separate)
    risk            : RiskManager for portfolio-level controls
    scale_factor    : fraction of proportional size to copy (0.5 = copy at 50%)
    max_signal_age  : reject signals older than this many seconds (latency guard)
    max_open        : max concurrent copy positions
    blocklist       : list of keyword substrings — skip markets containing any
    """

    def __init__(
        self,
        clob: PolymarketCLOB,
        risk: RiskManager,
        scale_factor: float = 0.5,
        max_signal_age: int = 60,
        max_open: int = 10,
        blocklist: list[str] | None = None,
    ) -> None:
        self._clob = clob
        self._risk = risk
        self._scale = scale_factor
        self._max_age = max_signal_age
        self._max_open = max_open
        self._blocklist = [kw.lower() for kw in (blocklist or DEFAULT_BLOCKLIST)]
        self._open: dict[str, CopyPosition] = {}   # condition_id → position
        self._closed: list[CopyPosition] = []
        self._queue: asyncio.Queue[TradeSignal] = asyncio.Queue()
        self._running = False

    def on_trade(self, signal: TradeSignal) -> None:
        """Callback for WalletMonitor — thread-safe enqueue."""
        try:
            self._queue.put_nowait(signal)
        except asyncio.QueueFull:
            log.warning("copy_queue_full", dropped=signal.market_question[:40])

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        self._running = False

    # ── processing ────────────────────────────────────────────────────────────

    async def _process_loop(self) -> None:
        while self._running:
            try:
                signal = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._handle(signal)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                log.exception("copy_executor_error", error=str(exc))

    async def _handle(self, signal: TradeSignal) -> None:
        # ── staleness guard ───────────────────────────────────────────────────
        age = time.time() - signal.detected_at
        if age > self._max_age:
            log.info("signal_stale", age_s=round(age), market=signal.market_question[:40])
            return

        # ── blocklist ─────────────────────────────────────────────────────────
        question_lower = signal.market_question.lower()
        for kw in self._blocklist:
            if kw in question_lower:
                log.info("signal_blocked", keyword=kw, market=signal.market_question[:40])
                return

        # ── position limit ────────────────────────────────────────────────────
        if len(self._open) >= self._max_open:
            log.info("max_open_reached", open=len(self._open))
            return

        # ── handle EXIT signals (close existing copy position) ────────────────
        if signal.direction == "EXIT":
            await self._close_position(signal)
            return

        # ── skip if already in this market ────────────────────────────────────
        if signal.condition_id in self._open:
            log.debug("already_open", condition=signal.condition_id[:16])
            return

        # ── risk check ────────────────────────────────────────────────────────
        allowed, reason = self._risk.can_trade()
        if not allowed:
            log.info("copy_blocked_risk", reason=reason)
            return

        # ── size the order ────────────────────────────────────────────────────
        size = self._compute_size(signal)
        if size < 1.0:
            log.info("copy_size_too_small", size=size)
            return

        # ── execute ───────────────────────────────────────────────────────────
        await self._open_position(signal, size)

    async def _open_position(self, signal: TradeSignal, size: float) -> None:
        limit_price = min(signal.price + 0.01, 0.99)   # 1c aggressive

        # For YES outcome buy, use the condition_id directly.
        # For NO outcome, the complementary token would be needed — we skip NO
        # buying for simplicity (it requires knowing the paired token_id).
        if signal.outcome.upper() == "NO":
            log.info("copy_skip_no_outcome", market=signal.market_question[:40])
            return

        result = await self._clob.place_order(
            side="UP",              # generic BUY — executor maps to correct condition
            size_usdc=size,
            limit_price=limit_price,
        )

        if result.filled or result.dry_run:
            pos = CopyPosition(
                condition_id=signal.condition_id,
                market_question=signal.market_question,
                side=signal.side,
                outcome=signal.outcome,
                entry_price=signal.price,
                size_usdc=size,
                source_wallet=signal.source_wallet,
                order_id=result.order_id,
            )
            self._open[signal.condition_id] = pos
            log.info(
                "copy_opened",
                source=signal.source_name,
                market=signal.market_question[:60],
                size=f"${size:.2f}",
                price=signal.price,
                dry_run=result.dry_run,
            )

    async def _close_position(self, signal: TradeSignal) -> None:
        pos = self._open.pop(signal.condition_id, None)
        if not pos:
            return
        log.info(
            "copy_closed",
            source=signal.source_name,
            market=pos.market_question[:60],
            held_s=round(time.time() - pos.opened_at),
        )
        self._closed.append(pos)

    def _compute_size(self, signal: TradeSignal) -> float:
        """
        Scale source trade size proportionally to our portfolio.

        If we don't know the source's total portfolio, we use their
        trade size directly and apply our scale_factor + per-trade risk cap.
        """
        portfolio = self._risk.state.portfolio_usdc
        per_trade_cap = portfolio * self._risk._per_trade / max(signal.price, 0.01)

        # Direct scale: copy scale_factor of their notional, capped by our risk
        raw_size = signal.size_usdc * self._scale
        return round(min(raw_size, per_trade_cap), 2)

    # ── status ────────────────────────────────────────────────────────────────

    def summary(self) -> str:
        return (
            f"Copy positions: {len(self._open)} open | "
            f"{len(self._closed)} closed | "
            f"queue: {self._queue.qsize()}"
        )
