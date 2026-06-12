"""
Execution engine + risk management.

Arbitrage logic:
  1. MiroFish swarm signal (macro): must agree on direction
  2. Force-graph signal (micro):    must converge with separation > 1.5
  3. Binance futures mark price lag vs Polymarket CLOB > 0.3%
  → All three must align before placing an order.

Exit on target (+0.5%), hard stop (-0.4%), or window expiry.
"""
import asyncio
import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

from config import (
    STARTING_BALANCE, PER_TRADE_RISK, DAILY_CAP_RISK, HARD_STOP,
    MIN_LIQUIDITY, MAX_SPREAD, LAG_THRESHOLD, SLIPPAGE_LIMIT, EDGE_EXPIRE_MS,
    MIROFISH_ENABLED, MIROFISH_MIN_CONFIDENCE,
    MOMENTUM_RISK_PER_TRADE, MOMENTUM_MIN_MOVE, MOMENTUM_ENTRY_SECONDS,
    MOMENTUM_PROFIT_TARGET, MOMENTUM_STOP_LOSS, MOMENTUM_EXIT_BEFORE_CLOSE,
    MOMENTUM_VALUE_EDGE,
)
from execution.adaptive import AdaptiveMemory
from feeds.binance_ws import BtcSnapshot
from feeds.indicators import IndicatorSet
from polymarket.clob_client import MarketState, OpenPosition, PolymarketClient
from forcegraph.force_graph import Bias, GraphSignal

if TYPE_CHECKING:
    from mirofish.client import MirofishClient, MirofishSignal


class TradeOutcome(str, Enum):
    WIN  = "WIN"
    LOSS = "LOSS"
    SKIP = "SKIP"


@dataclass
class TradeRecord:
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    outcome: TradeOutcome
    reason: str
    entry_time_ms: int
    exit_time_ms: int
    hold_ms: int
    lag_at_entry: float      # mark_price_lag when trade was entered
    edge_age_ms: int         # ms from edge detection to order placement


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


def _fair_yes_from_mark(snap: BtcSnapshot) -> float:
    """
    Estimate fair probability of BTC going up in current 5min window
    using Binance futures mark price momentum relative to window open.

    Uses a logistic function scaled to 0.5% moves ≈ full confidence.
    """
    mark = snap.mark_price
    if mark <= 0 or not snap.klines:
        return 0.5
    window_open = snap.klines[-1].open   # current 5m candle open
    move_pct = (mark - window_open) / (window_open + 1e-9)
    # tanh saturates at ±0.5%: beyond that we're confident in direction
    return 0.5 + 0.5 * math.tanh(move_pct / 0.005)


class ExecutionEngine:
    """
    Three-layer signal stack before any order is placed:
      1. MiroFish swarm (macro): direction + confidence from social simulation
      2. Force-graph physics (micro): real-time cluster convergence
      3. Binance mark price lag vs Polymarket CLOB (the actual arbitrage)
    All three must agree; any disagreement or missing signal skips the trade.
    """

    MAX_HOLD_SECONDS = 290
    TARGET_PROFIT    = 0.005

    def __init__(self, clob: PolymarketClient,
                 risk: Optional[RiskState] = None) -> None:
        self._clob    = clob
        self._risk    = risk or RiskState(balance=STARTING_BALANCE)
        self._history: list[TradeRecord] = []
        self._active: Optional[OpenPosition] = None
        self._edge_detected_at: int = 0
        self._mirofish: Optional["MirofishClient"] = None

    def set_mirofish(self, client: "MirofishClient") -> None:
        self._mirofish = client

    @property
    def risk(self) -> RiskState:
        return self._risk

    @property
    def history(self) -> list[TradeRecord]:
        return self._history

    @property
    def mirofish_signal(self) -> Optional["MirofishSignal"]:
        return self._mirofish.signal if self._mirofish else None

    async def evaluate_and_trade(
        self,
        snap: BtcSnapshot,
        ind: IndicatorSet,
        market: MarketState,
        signal: GraphSignal,
    ) -> Optional[TradeRecord]:
        if self._active:
            return await self._monitor_active(market)

        reason = self._pre_flight(market, signal)
        if reason:
            return None

        edge = self._detect_edge(snap, market, signal)
        if not edge:
            self._edge_detected_at = 0
            return None

        # First tick we see an edge: record the time
        now = int(time.time() * 1000)
        if not self._edge_detected_at:
            self._edge_detected_at = now

        edge_age = now - self._edge_detected_at
        if edge_age > EDGE_EXPIRE_MS:
            self._edge_detected_at = 0
            return None

        return await self._execute(edge, edge_age, signal)

    # ── pre-flight ────────────────────────────────────────────────────────────

    def _pre_flight(self, market: MarketState, signal: GraphSignal) -> Optional[str]:
        r = self._risk
        if r.halted:
            return r.halt_reason
        if r.daily_pnl_pct <= -DAILY_CAP_RISK:
            r.halted = True
            r.halt_reason = "daily cap -2%"
            return r.halt_reason

        # ── Layer 1: MiroFish swarm gate ──────────────────────────────────────
        if MIROFISH_ENABLED and self._mirofish:
            ms = self._mirofish.signal
            if not ms.available:
                return "MiroFish unavailable"
            if ms.stale:
                return f"MiroFish signal stale ({ms.age_seconds/60:.1f}m)"
            if ms.confidence < MIROFISH_MIN_CONFIDENCE:
                return f"MiroFish low confidence ({ms.confidence:.0%})"
            if ms.bias == Bias.NEUTRAL:
                return "MiroFish neutral"
            # direction must match force-graph
            if signal.converged and ms.bias != signal.bias:
                return f"MiroFish/graph mismatch ({ms.bias.value} vs {signal.bias.value})"

        # ── Layer 2: force-graph gate ─────────────────────────────────────────
        if not signal.converged:
            return "graph not converged"
        if signal.confidence < 0.65:
            return "graph low confidence"
        if signal.separation < 1.5:
            return "clusters not separated"

        # ── Liquidity / spread ────────────────────────────────────────────────
        if signal.bias == Bias.BULL:
            liq = market.yes_ask_size * market.yes_ask
        else:
            liq = market.no_ask_size * market.no_ask
        if liq < MIN_LIQUIDITY:
            return "thin liquidity"
        spread = market.yes_ask - market.yes_bid
        if spread > MAX_SPREAD:
            return "spread too wide"
        return None

    # ── edge detection (Binance mark price vs Polymarket CLOB) ───────────────

    def _detect_edge(
        self,
        snap: BtcSnapshot,
        market: MarketState,
        signal: GraphSignal,
    ) -> Optional[dict]:
        """
        Core arbitrage: Binance futures mark price is the ground truth.
        Polymarket CLOB reprices with a delay — we exploit that gap.

        fair_yes = P(BTC closes above window_open) derived from mark momentum
        lag      = fair_yes - clob_yes_ask   (positive → YES is cheap)
        """
        fair_yes = _fair_yes_from_mark(snap)

        if signal.bias == Bias.BULL:
            clob_price = market.yes_ask
            lag = fair_yes - clob_price
            if lag < LAG_THRESHOLD:
                return None
            return {
                "side":        "YES",
                "token_id":    market.yes_token_id,
                "entry_price": clob_price,
                "fair_value":  fair_yes,
                "lag":         lag,
            }
        else:
            fair_no = 1.0 - fair_yes
            clob_price = market.no_ask
            lag = fair_no - clob_price
            if lag < LAG_THRESHOLD:
                return None
            return {
                "side":        "NO",
                "token_id":    market.no_token_id,
                "entry_price": clob_price,
                "fair_value":  fair_no,
                "lag":         lag,
            }

    # ── order execution ───────────────────────────────────────────────────────

    async def _execute(
        self,
        edge: dict,
        edge_age_ms: int,
        signal: GraphSignal,
    ) -> Optional[TradeRecord]:
        balance = self._risk.balance
        price   = edge["entry_price"]
        if price <= 0:
            return None
        size = round((balance * PER_TRADE_RISK) / price, 2)
        if size < 1.0:
            return None

        limit_price = round(min(price * (1 + SLIPPAGE_LIMIT), 0.99), 4)
        order_id = await self._clob.place_order(
            token_id=edge["token_id"],
            side="BUY",
            size=size,
            price=limit_price,
        )
        if not order_id:
            return None

        entry_time = int(time.time() * 1000)
        pos = OpenPosition(
            token_id=edge["token_id"],
            side=edge["side"],
            size=size,
            entry_price=price,
            entry_time_ms=entry_time,
            order_id=order_id,
        )
        pos._lag_at_entry  = edge["lag"]
        pos._edge_age_ms   = edge_age_ms
        self._clob.record_position(pos)
        self._active = pos
        self._edge_detected_at = 0
        return None

    # ── position monitoring ───────────────────────────────────────────────────

    async def _monitor_active(self, market: MarketState) -> Optional[TradeRecord]:
        pos = self._active
        now_ms = int(time.time() * 1000)
        hold_s = (now_ms - pos.entry_time_ms) / 1000

        mark = market.mid_yes if pos.side == "YES" else market.mid_no
        unrealised_pct = (mark - pos.entry_price) / (pos.entry_price + 1e-9)

        exit_reason: Optional[str] = None
        if unrealised_pct >= self.TARGET_PROFIT:
            exit_reason = f"target +{unrealised_pct:.2%}"
        elif unrealised_pct <= HARD_STOP:
            exit_reason = f"stop {unrealised_pct:.2%}"
        elif hold_s >= self.MAX_HOLD_SECONDS:
            exit_reason = "window expiry"

        if not exit_reason:
            return None

        exit_price = mark
        exit_time  = int(time.time() * 1000)
        pnl = (exit_price - pos.entry_price) * pos.size
        outcome = TradeOutcome.WIN if pnl > 0 else TradeOutcome.LOSS

        order_info = await self._clob.get_order(pos.order_id)
        status = order_info.get("status") if order_info else None
        if status in ("OPEN", "UNMATCHED"):
            await self._clob.cancel_order(pos.order_id)
        elif status == "MATCHED":
            sell_tid = (market.yes_token_id if pos.side == "YES"
                        else market.no_token_id)
            await self._clob.place_order(
                token_id=sell_tid, side="SELL",
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
            lag_at_entry=getattr(pos, "_lag_at_entry", 0.0),
            edge_age_ms=getattr(pos, "_edge_age_ms", 0),
        )
        self._risk.register_trade(pnl, outcome)
        self._history.append(record)
        return record


@dataclass
class MomentumPosition:
    condition_id: str
    token_id: str
    side: str           # "UP" or "DOWN"
    entry_price: float
    size: float
    entry_ts: float
    market_end_ts: float
    tag: str = ""       # adaptive-memory key, e.g. "momentum-UP"


class MomentumEngine:
    """
    Strategy C — momentum bet + active exit management.

    Entry: once per 5-min window, if BTC mark price moves ≥ MOMENTUM_MIN_MOVE
    from the candle open within the first MOMENTUM_ENTRY_SECONDS.

    Exit (whichever comes first):
      - Profit target: sell when current bid ≥ entry * (1 + PROFIT_TARGET)
      - Stop loss:     sell when current bid ≤ entry * (1 + STOP_LOSS)
      - Window close:  sell MOMENTUM_EXIT_BEFORE_CLOSE seconds before expiry
    """

    def __init__(self, clob: PolymarketClient, risk: RiskState) -> None:
        self._clob     = clob
        self._risk     = risk
        self._memory   = AdaptiveMemory()
        self._history: list[TradeRecord] = []
        self._last_condition_id: str = ""
        self._bet_placed_this_window: bool = False
        self._window_open_price: float = 0.0
        self._window_start_ts: float = 0.0
        self._open_pos: Optional[MomentumPosition] = None

    @property
    def history(self) -> list[TradeRecord]:
        return list(self._history)

    @property
    def memory(self) -> "AdaptiveMemory":
        return self._memory

    @property
    def open_position(self) -> Optional[MomentumPosition]:
        return self._open_pos

    async def evaluate(
        self,
        snap: BtcSnapshot,
        market: MarketState,
        market_end_ts: float = 0.0,
    ) -> Optional[str]:
        """Call every tick. Returns a status string on entry/exit, else None."""
        if not snap.klines:
            return None

        # ── monitor open position ─────────────────────────────────────────────
        if self._open_pos:
            result = await self._monitor(market, market_end_ts)
            if result:
                return result

        if self._risk.halted or self._risk.daily_pnl_pct <= -DAILY_CAP_RISK:
            return None

        current_candle = snap.klines[0]
        cid = market.condition_id

        # new window → reset
        if cid != self._last_condition_id:
            self._last_condition_id      = cid
            self._bet_placed_this_window = False
            self._window_open_price      = current_candle.open
            self._window_start_ts        = time.time()

        if self._bet_placed_this_window:
            return None

        ref = snap.mark_price if snap.mark_price > 0 else snap.price
        if self._window_open_price <= 0:
            return None

        move     = (ref - self._window_open_price) / self._window_open_price
        fair_yes = _fair_yes_from_mark(snap)        # chart-implied P(up)
        fair_no  = 1.0 - fair_yes
        elapsed  = time.time() - self._window_start_ts

        go_up: Optional[bool] = None
        kind    = ""        # "momentum" or "value" — stable across trades
        trigger = ""        # human-readable detail for the status line

        # ── path 1: early momentum bet ────────────────────────────────────────
        if elapsed <= MOMENTUM_ENTRY_SECONDS and abs(move) >= MOMENTUM_MIN_MOVE:
            go_up   = move > 0
            kind    = "momentum"
            trigger = f"momentum {move:+.3%}"

        # ── path 2: value bet — a side trading below chart fair value ──────────
        #    (active for the whole window, not just the first 60s)
        elif elapsed <= MOMENTUM_ENTRY_SECONDS:
            yes_disc = fair_yes - market.yes_ask    # how cheap YES is vs fair
            no_disc  = fair_no  - market.no_ask
            if yes_disc >= MOMENTUM_VALUE_EDGE and yes_disc >= no_disc:
                go_up   = True
                kind    = "value"
                trigger = f"value YES {market.yes_ask:.2f} vs fair {fair_yes:.2f}"
            elif no_disc >= MOMENTUM_VALUE_EDGE:
                go_up   = False
                kind    = "value"
                trigger = f"value NO {market.no_ask:.2f} vs fair {fair_no:.2f}"

        # ── path 3: directional fallback — fire on whatever direction BTC moved
        #    if we reach 180s into the window and still haven't bet
        elif elapsed >= 180:
            go_up   = move >= 0          # even flat → bet UP (small positive bias)
            kind    = "fallback"
            trigger = f"fallback {move:+.3%} @{elapsed:.0f}s"

        if go_up is None:
            return None

        token_id   = market.yes_token_id if go_up else market.no_token_id
        ask_price  = market.yes_ask      if go_up else market.no_ask
        side_label = "UP" if go_up else "DOWN"
        tag        = f"{kind}-{side_label}"   # e.g. "value-DOWN"

        # ── adaptive gate: skip tags that have been losing ────────────────────
        if not self._memory.allow(tag):
            self._bet_placed_this_window = True   # don't re-try this window
            wr = self._memory.win_rate_of(tag)
            return f"SKIP {tag} (learned: {wr:.0%} win rate, paused)"

        if ask_price <= 0 or ask_price >= 1:
            return None

        # size scaled by what the bot has learned about this tag
        mult        = self._memory.size_multiplier(tag)
        size_usd    = self._risk.balance * MOMENTUM_RISK_PER_TRADE * mult
        size        = round(size_usd / ask_price, 2)
        if size < 1.0:
            return None

        limit_price = round(min(ask_price * 1.005, 0.99), 4)
        order_id = await self._clob.place_order(
            token_id=token_id, side="BUY",
            size=size, price=limit_price,
        )

        self._bet_placed_this_window = True

        if order_id:
            self._open_pos = MomentumPosition(
                condition_id=cid,
                token_id=token_id,
                side=side_label,
                entry_price=ask_price,
                size=size,
                entry_ts=time.time(),
                market_end_ts=market_end_ts,
                tag=tag,
            )

        mult_note = f" x{mult:.2g}" if mult != 1.0 else ""
        outcome_note = "OK" if order_id else f"FAILED — {self._clob.last_error}"
        return (
            f"BET {side_label} [{trigger}] @ {ask_price:.3f}  ${size_usd:.2f}{mult_note}  "
            f"{outcome_note}"
        )

    async def _monitor(
        self, market: MarketState, market_end_ts: float
    ) -> Optional[str]:
        pos = self._open_pos
        if not pos:
            return None

        # current mid price for our token
        current_price = (
            (market.yes_bid + market.yes_ask) / 2
            if pos.side == "UP"
            else (market.no_bid + market.no_ask) / 2
        )
        sell_bid = market.yes_bid if pos.side == "UP" else market.no_bid

        pnl_pct = (current_price - pos.entry_price) / pos.entry_price

        seconds_left = (market_end_ts - time.time()) if market_end_ts else 999

        exit_reason: Optional[str] = None
        if pnl_pct >= MOMENTUM_PROFIT_TARGET:
            exit_reason = f"profit target +{pnl_pct:.1%}"
        elif pnl_pct <= MOMENTUM_STOP_LOSS:
            exit_reason = f"stop loss {pnl_pct:.1%}"
        elif seconds_left <= MOMENTUM_EXIT_BEFORE_CLOSE:
            exit_reason = f"window closing ({seconds_left:.0f}s left)"

        if not exit_reason:
            return None

        # place SELL at current bid
        sell_price = round(max(sell_bid * 0.995, 0.01), 4)
        await self._clob.place_order(
            token_id=pos.token_id,
            side="SELL",
            size=pos.size,
            price=sell_price,
        )

        pnl = (sell_price - pos.entry_price) * pos.size
        outcome = TradeOutcome.WIN if pnl > 0 else TradeOutcome.LOSS
        now_ms  = int(time.time() * 1000)
        record  = TradeRecord(
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=sell_price,
            size=pos.size,
            pnl=pnl,
            outcome=outcome,
            reason=exit_reason,
            entry_time_ms=int(pos.entry_ts * 1000),
            exit_time_ms=now_ms,
            hold_ms=now_ms - int(pos.entry_ts * 1000),
            lag_at_entry=0.0,
            edge_age_ms=0,
        )
        self._risk.register_trade(pnl, outcome)
        self._history.append(record)

        # ── learn from this trade ─────────────────────────────────────────────
        if pos.tag:
            self._memory.record(pos.tag, won=(outcome == TradeOutcome.WIN))

        self._open_pos = None

        return (
            f"MOMENTUM EXIT {pos.side} {outcome.value} "
            f"pnl={pnl:+.2f} ({pnl_pct:+.1%}) | {exit_reason}"
        )
