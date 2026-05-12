"""
Order manager.

Handles the <100ms execution window: from signal → order → confirmation.
Tracks open positions and P&L realisation on contract settlement.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    from data.polymarket_clob import PolymarketCLOB, OrderResult
    from engine.lag_detector import LagSignal
    from execution.risk_manager import RiskManager

log = structlog.get_logger()


@dataclass
class Position:
    side: str               # "UP" or "DOWN"
    size_usdc: float
    entry_price: float
    order_id: str
    opened_at: float = field(default_factory=time.time)
    settled: bool = False
    settlement_price: Optional[float] = None
    pnl: Optional[float] = None


class OrderManager:
    def __init__(self, clob: "PolymarketCLOB", risk: "RiskManager") -> None:
        self._clob = clob
        self._risk = risk
        self._open_positions: list[Position] = []
        self._closed_positions: list[Position] = []

    async def execute(self, signal: "LagSignal") -> Optional["OrderResult"]:
        """
        Attempt to execute a trade for the given lag signal.

        Checks risk, sizes the order, places it, and records the position.
        Total path must complete in <100ms; CLOB client has its own 500ms
        session timeout so the hard deadline is enforced by asyncio.timeout.
        """
        allowed, reason = self._risk.can_trade()
        if not allowed:
            log.info("trade_blocked", reason=reason)
            return None

        # Size based on entry price (YES token price)
        entry_price = signal.clob_up_price if signal.direction == "UP" else (1 - signal.clob_up_price)
        size = self._risk.size_order(entry_price)
        if size is None:
            log.info("trade_skipped", reason="size_too_small")
            return None

        t0 = time.perf_counter()
        try:
            async with asyncio.timeout(0.095):   # 95ms hard deadline
                result = await self._clob.place_order(
                    side=signal.direction,
                    size_usdc=size,
                    limit_price=entry_price + 0.001,   # 0.1c aggressive limit
                )
        except TimeoutError:
            log.warning("execution_timeout", elapsed_ms=(time.perf_counter() - t0) * 1000)
            return None

        elapsed = (time.perf_counter() - t0) * 1000

        if result.filled or result.dry_run:
            pos = Position(
                side=signal.direction,
                size_usdc=size,
                entry_price=entry_price,
                order_id=result.order_id,
            )
            self._open_positions.append(pos)
            log.info(
                "order_filled",
                side=signal.direction,
                size=size,
                price=entry_price,
                lag_pct=f"{signal.lag_pct:.4f}",
                confidence=f"{signal.confidence:.2f}",
                latency_ms=f"{elapsed:.1f}",
                dry_run=result.dry_run,
            )
        else:
            log.warning("order_rejected", side=signal.direction, order_id=result.order_id)

        return result

    def settle_position(self, order_id: str, settlement_price: float) -> Optional[float]:
        """
        Mark a position as settled and record P&L.
        settlement_price = 1.0 if contract resolved in our direction, else 0.0.
        """
        for pos in self._open_positions:
            if pos.order_id == order_id:
                pos.settled = True
                pos.settlement_price = settlement_price
                # P&L: (settlement - entry) * size / entry  (simplified)
                pos.pnl = (settlement_price - pos.entry_price) * pos.size_usdc
                self._risk.record_fill(pos.pnl)
                self._open_positions.remove(pos)
                self._closed_positions.append(pos)
                log.info(
                    "position_settled",
                    order_id=order_id,
                    pnl=f"${pos.pnl:+.2f}",
                    portfolio=self._risk.summary(),
                )
                return pos.pnl
        return None

    @property
    def open_count(self) -> int:
        return len(self._open_positions)

    @property
    def total_trades(self) -> int:
        return len(self._closed_positions)
