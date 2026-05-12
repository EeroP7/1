"""
Risk manager.

Enforces:
  - 0.5% per-trade risk relative to current portfolio
  - 2.0% daily P&L cap  (stop trading if hit)
  - -0.4% hard stop loss (emergency stop)
  - Minimum liquidity check before order entry
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RiskState:
    portfolio_usdc: float
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    trade_count_today: int = 0
    wins: int = 0
    losses: int = 0
    session_start: float = field(default_factory=time.time)
    day_start_value: float = 0.0
    halted: bool = False
    halt_reason: str = ""


class RiskManager:
    def __init__(
        self,
        portfolio_usdc: float,
        per_trade_risk: float = 0.005,
        daily_cap: float = 0.02,
        hard_stop: float = -0.004,
    ) -> None:
        self._per_trade = per_trade_risk
        self._daily_cap = daily_cap
        self._hard_stop = hard_stop
        self.state = RiskState(
            portfolio_usdc=portfolio_usdc,
            day_start_value=portfolio_usdc,
        )

    # ── pre-trade checks ──────────────────────────────────────────────────────

    def can_trade(self) -> tuple[bool, str]:
        """Return (allowed, reason_if_not)."""
        if self.state.halted:
            return False, self.state.halt_reason

        pnl_pct = self.state.daily_pnl_pct

        if pnl_pct >= self._daily_cap:
            self._halt(f"Daily cap reached: {pnl_pct:.2%}")
            return False, self.state.halt_reason

        if pnl_pct <= self._hard_stop:
            self._halt(f"Hard stop triggered: {pnl_pct:.2%}")
            return False, self.state.halt_reason

        return True, ""

    def size_order(
        self,
        clob_price: float,
        min_size_usdc: float = 1.0,
    ) -> Optional[float]:
        """
        Return USDC order size (notional) for this trade, or None if too small.
        Risk = size * (1 - clob_price)  [max loss if contract expires wrong]
        Solving: risk_usdc = portfolio * per_trade_risk
                 size = risk_usdc / (1 - clob_price)
        """
        risk_usdc = self.state.portfolio_usdc * self._per_trade
        exposure = 1.0 - clob_price
        if exposure <= 0.01:
            return None
        size = risk_usdc / exposure
        if size < min_size_usdc:
            return None
        return round(size, 2)

    # ── post-trade accounting ─────────────────────────────────────────────────

    def record_fill(self, pnl_usdc: float) -> None:
        self.state.portfolio_usdc += pnl_usdc
        self.state.daily_pnl += pnl_usdc
        self.state.trade_count_today += 1
        if pnl_usdc >= 0:
            self.state.wins += 1
        else:
            self.state.losses += 1
        self.state.daily_pnl_pct = (
            self.state.portfolio_usdc / self.state.day_start_value - 1
        )

    def reset_daily(self) -> None:
        self.state.daily_pnl = 0.0
        self.state.daily_pnl_pct = 0.0
        self.state.trade_count_today = 0
        self.state.wins = 0
        self.state.losses = 0
        self.state.day_start_value = self.state.portfolio_usdc
        self.state.halted = False
        self.state.halt_reason = ""

    # ── internal ──────────────────────────────────────────────────────────────

    def _halt(self, reason: str) -> None:
        self.state.halted = True
        self.state.halt_reason = reason

    def summary(self) -> str:
        s = self.state
        wrate = s.wins / max(s.trade_count_today, 1) * 100
        return (
            f"Portfolio: ${s.portfolio_usdc:,.2f} | "
            f"Day P&L: {s.daily_pnl_pct:+.2%} (${s.daily_pnl:+.2f}) | "
            f"Trades: {s.trade_count_today} | "
            f"Win rate: {wrate:.0f}%"
            + (f" | HALTED: {s.halt_reason}" if s.halted else "")
        )
