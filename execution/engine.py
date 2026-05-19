"""
Execution engine + risk management.

Decides whether to enter a trade, sizes the position, places the order,
monitors for fill / stop / target, and tracks daily P&L.
"""
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from config import (
    STARTING_BALANCE, PER_TRADE_RISK, DAILY_CAP_RISK, HARD_STOP,
    MIN_LIQUIDITY, MAX_SPREAD, LAG_THRESHOLD, SLIPPAGE_LIMIT,
)
from feeds.binance_ws import BtcSnapshot
from feeds.indicators import IndicatorSet
from polymarket.clob_client import MarketState, OpenPosition, PolymarketClient
from signal.force_graph import Bias, GraphSignal


class TradeOutcome(str, Enum):
    WIN  = "WIN"
    LOSS = "LOSS"
    SKIP = "SKIP"


@dataclass
class TradeRecord:
    side: str                  # "YES" or "NO"
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    outcome: TradeOutcome
    reason: str
    entry_time_ms: int
    exit_time_ms: int
    hold_ms: int


@dataclass
class RiskState:
    balance: float
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    trades_today: int = 0
    wins: int = 0
    losses: int = 0
    skips: int = 0
    halted: bool = False
    halt_reason: str = ""

    def register_trade(self, pnl: float, outcome: TradeOutcome) -> None:
        self.balance += pnl
        self.daily_pnl += pnl
        self.daily_pnl_pct = self.daily_pnl / STARTING_BALANCE
        self.trades_today += 1
        if outcome == TradeOutcome.WIN:
            self.wins += 1
        elif outcome == TradeOutcome.LOSS:
            self.losses += 1
        else:
            self.skips += 1


class ExecutionEngine:
    """
    One active trade at a time to keep risk controlled.
    Runs a tight event loop:
      1. Pre-flight checks (risk limits, liquidity, spread, signal quality)
      2. Edge detection (CLOB vs spot lag + graph convergence)
      3. Order placement + fill monitoring
      4. Exit on target / stop / timeout
    """

    FILL_POLL_INTERVAL = 0.05   # 50ms
    MAX_HOLD_SECONDS   = 290    # exit before next 5-min window
    TARGET_PROFIT_PCT  = 0.005  # 0.5% target

    def __init__(self, clob: PolymarketClient) -> None:
        self._clob = clob
        self._risk = RiskState(balance=STARTING_BALANCE)
        self._history: list[TradeRecord] = []
        self._active: Optional[OpenPosition] = None
        self._last_trade_time = 0

    # ── public ────────────────────────────────────────────────────────────────

    @property
    def risk(self) -> RiskState:
        return self._risk

    @property
    def history(self) -> list[TradeRecord]:
        return self._history

    async def evaluate_and_trade(
        self,
        snap: BtcSnapshot,
        ind: IndicatorSet,
        market: MarketState,
        signal: GraphSignal,
    ) -> Optional[TradeRecord]:
        """
        Main entry point called on every tick.
        Returns a TradeRecord if a trade was completed this tick, else None.
        """
        if self._active:
            return await self._monitor_active(market, snap)

        skip_reason = self._pre_flight(market, signal)
        if skip_reason:
            return None

        edge = self._detect_edge(snap, market, signal)
        if not edge:
            return None

        return await self._execute(edge, market, snap, signal)

    # ── pre-flight ────────────────────────────────────────────────────────────

    def _pre_flight(self, market: MarketState, signal: GraphSignal) -> Optional[str]:
        r = self._risk
        if r.halted:
            return r.halt_reason
        if r.daily_pnl_pct <= -DAILY_CAP_RISK:
            r.halted = True
            r.halt_reason = "daily cap hit"
            return r.halt_reason
        if not signal.converged:
            return "no convergence"
        if signal.confidence < 0.65:
            return "low confidence"
        # liquidity check
        if signal.bias == Bias.BULL:
            liq = market.yes_ask_size * market.yes_ask
        else:
            liq = market.no_ask_size * market.no_ask
        if liq < MIN_LIQUIDITY:
            return "thin liquidity"
        # spread check
        spread = market.yes_ask - market.yes_bid
        if spread > MAX_SPREAD:
            return "spread too wide"
        return None

    # ── edge detection ────────────────────────────────────────────────────────

    def _detect_edge(
        self,
        snap: BtcSnapshot,
        market: MarketState,
        signal: GraphSignal,
    ) -> Optional[dict]:
        """
        Detects a tradeable edge when the Polymarket CLOB lags spot price
        in the direction confirmed by the force-graph signal.

        Returns a dict with trade parameters or None.
        """
        spot = snap.price
        if signal.bias == Bias.BULL:
            # YES token should be priced closer to 1.0 if BTC is going up
            # Implied probability from spot momentum vs current YES ask price
            clob_price = market.yes_ask
            # If the market is underpricing YES given our signal: edge exists
            # Use (signal confidence - clob_price) as the edge magnitude
            implied_fair = signal.confidence
            lag = implied_fair - clob_price
            if lag < LAG_THRESHOLD:
                return None
            return {
                "side": "YES",
                "token_id": market.yes_token_id,
                "entry_price": clob_price,
                "implied_fair": implied_fair,
                "lag": lag,
                "signal": signal,
            }
        else:  # BEAR
            clob_price = market.no_ask
            implied_fair = signal.confidence
            lag = implied_fair - clob_price
            if lag < LAG_THRESHOLD:
                return None
            return {
                "side": "NO",
                "token_id": market.no_token_id,
                "entry_price": clob_price,
                "implied_fair": implied_fair,
                "lag": lag,
                "signal": signal,
            }

    # ── execution ─────────────────────────────────────────────────────────────

    async def _execute(
        self,
        edge: dict,
        market: MarketState,
        snap: BtcSnapshot,
        signal: GraphSignal,
    ) -> Optional[TradeRecord]:
        entry_time = int(time.time() * 1000)
        balance = self._risk.balance
        size_usd = balance * PER_TRADE_RISK
        price = edge["entry_price"]
        if price <= 0:
            return None
        size = round(size_usd / price, 2)
        if size < 1.0:
            return None

        # limit order slightly above ask to maximise fill speed
        limit_price = round(min(price * (1 + SLIPPAGE_LIMIT), 0.99), 4)

        order_id = await self._clob.place_order(
            token_id=edge["token_id"],
            side="BUY",
            size=size,
            price=limit_price,
        )
        if not order_id:
            return None

        pos = OpenPosition(
            token_id=edge["token_id"],
            side=edge["side"],
            size=size,
            entry_price=price,
            entry_time_ms=entry_time,
            order_id=order_id,
        )
        self._clob.record_position(pos)
        self._active = pos
        return None  # position opened; will be closed on next monitor call

    # ── position monitoring ───────────────────────────────────────────────────

    async def _monitor_active(
        self, market: MarketState, snap: BtcSnapshot
    ) -> Optional[TradeRecord]:
        pos = self._active
        now_ms = int(time.time() * 1000)
        hold_s = (now_ms - pos.entry_time_ms) / 1000

        # current mark price
        if pos.side == "YES":
            mark = market.mid_yes
        else:
            mark = market.mid_no

        unrealised_pct = (mark - pos.entry_price) / pos.entry_price

        # --- exit conditions ---
        exit_reason = None
        if unrealised_pct >= self.TARGET_PROFIT_PCT:
            exit_reason = f"target +{unrealised_pct:.2%}"
        elif unrealised_pct <= HARD_STOP:
            exit_reason = f"hard stop {unrealised_pct:.2%}"
        elif hold_s >= self.MAX_HOLD_SECONDS:
            exit_reason = "window expiry"

        if not exit_reason:
            return None

        # close the position (market sell)
        exit_price = mark
        exit_time  = int(time.time() * 1000)
        pnl = (exit_price - pos.entry_price) * pos.size
        outcome = TradeOutcome.WIN if pnl > 0 else TradeOutcome.LOSS

        # cancel unfilled order if still open
        order_info = await self._clob.get_order(pos.order_id)
        if order_info and order_info.get("status") in ("OPEN", "UNMATCHED"):
            await self._clob.cancel_order(pos.order_id)
        # sell position if filled
        elif order_info and order_info.get("status") == "MATCHED":
            if pos.side == "YES":
                sell_tid = market.yes_token_id
            else:
                sell_tid = market.no_token_id
            await self._clob.place_order(
                token_id=sell_tid,
                side="SELL",
                size=pos.size,
                price=round(exit_price * 0.99, 4),
            )

        self._clob.close_position(pos.order_id)
        self._active = None

        record = TradeRecord(
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            size=pos.size,
            pnl=pnl,
            outcome=outcome,
            reason=exit_reason,
            entry_time_ms=pos.entry_time_ms,
            exit_time_ms=exit_time,
            hold_ms=exit_time - pos.entry_time_ms,
        )
        self._risk.register_trade(pnl, outcome)
        self._history.append(record)
        return record
