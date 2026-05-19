"""
Polymarket BTC UP/DOWN 5MIN scalper — main entry point.

Architecture:
  BinanceFeed  ──── ticks ──→  ForceGraph  ──→  ExecutionEngine
      │                             ↑                   │
      └── BtcSnapshot ──────── Indicators               │
                                                         ↓
  PolymarketClient ← market state ────────── order placement

Run:
  python main.py

Stop cleanly with Ctrl-C.
"""
import asyncio
import math
import signal
import sys
import time

from feeds.binance_ws import BinanceFeed
from feeds.indicators import compute as compute_indicators
from polymarket.clob_client import PolymarketClient
from signal.force_graph import ForceGraph
from execution.engine import ExecutionEngine
from terminal.display import Dashboard
from config import STARTING_BALANCE


TICK_INTERVAL_MS = 100   # evaluate every 100ms
MARKET_POLL_MS   = 200   # refresh Polymarket CLOB every 200ms


def _seconds_to_5min_close() -> float:
    """Seconds remaining until the next 5-minute boundary."""
    ts = time.time()
    return 300 - (ts % 300)


async def main() -> None:
    # ── initialise components ─────────────────────────────────────────────────
    feed   = BinanceFeed()
    graph  = ForceGraph()
    clob   = PolymarketClient()
    engine = ExecutionEngine(clob)

    print("Starting Binance feed…")
    await feed.start()
    await feed.wait_ready()
    print("Feed ready. Discovering Polymarket market…")

    found = await clob.discover_market()
    status = "market found" if found else "market not found — running dry"

    market_state = None
    last_market_poll = 0.0

    stop_event = asyncio.Event()

    def _handle_signal(*_):
        stop_event.set()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT,  _handle_signal)
    loop.add_signal_handler(signal.SIGTERM, _handle_signal)

    # ── main loop ─────────────────────────────────────────────────────────────
    with Dashboard() as dash:
        while not stop_event.is_set():
            tick_start = time.monotonic()

            # 1. Fetch latest market state (throttled)
            now = time.time()
            if found and (now - last_market_poll) * 1000 >= MARKET_POLL_MS:
                market_state = await clob.get_market_state()
                last_market_poll = now

            # 2. Snapshot from Binance
            snap = await feed.get_snapshot()
            if not snap or not snap.klines:
                dash.update(None, None, market_state, None,
                            engine.risk, engine.history, "waiting for data…")
                await asyncio.sleep(0.05)
                continue

            # 3. Compute technical indicators
            ind = compute_indicators(snap.klines, snap.price)

            # 4. Evaluate force-graph signal
            yes_price = market_state.mid_yes if market_state else 0.5
            no_price  = market_state.mid_no  if market_state else 0.5
            ttc = _seconds_to_5min_close()
            sig = graph.evaluate(snap, ind, yes_price, no_price, ttc)

            # 5. Execution decision
            if market_state and not engine.risk.halted:
                record = await engine.evaluate_and_trade(snap, ind, market_state, sig)
                if record:
                    status = (
                        f"{record.outcome.value} {record.side} "
                        f"{record.pnl:+.2f} | {record.reason}"
                    )

            # 6. Refresh display
            dash.update(snap, ind, market_state, sig,
                        engine.risk, engine.history, status)

            # 7. Pace the loop
            elapsed_ms = (time.monotonic() - tick_start) * 1000
            sleep_ms   = max(0.0, TICK_INTERVAL_MS - elapsed_ms)
            await asyncio.sleep(sleep_ms / 1000)

    # ── shutdown ──────────────────────────────────────────────────────────────
    await feed.stop()
    print("\nBot stopped cleanly.")
    r = engine.risk
    print(f"  Balance : ${r.balance:,.2f}  (started ${STARTING_BALANCE:,.2f})")
    print(f"  Day P&L : {r.daily_pnl_pct:+.2%}  ({r.daily_pnl:+.2f})")
    print(f"  Trades  : {r.trades_today}  W:{r.wins}  L:{r.losses}")


if __name__ == "__main__":
    asyncio.run(main())
