"""
Polymarket BTC UP/DOWN 5MIN scalper — main entry point.

Signal stack (all three must agree before trading):
  1. MiroFish swarm     — macro direction from social simulation
  2. Force-graph        — micro cluster convergence from physics simulation
  3. Binance mark price — CLOB lag detection (the actual arbitrage edge)

  BinanceFeed ──→ Indicators ──→ ForceGraph ──→ ExecutionEngine
       │                              │                │
       │          MirofishClient ─────┘                │
       │          (refreshes every 15 min)             │
       └──────────────────────────────────────→ PolymarketClient

Run:
  python main.py

Stop cleanly with Ctrl-C.
"""
import asyncio
import signal
import time

from config import MIROFISH_ENABLED, STARTING_BALANCE
from execution.engine import ExecutionEngine
from feeds.binance_ws import BinanceFeed
from feeds.indicators import compute as compute_indicators
from polymarket.clob_client import PolymarketClient
from signal.force_graph import ForceGraph
from terminal.display import Dashboard

TICK_INTERVAL_MS = 100   # evaluate every 100ms
MARKET_POLL_MS   = 200   # refresh Polymarket CLOB every 200ms


def _seconds_to_5min_close() -> float:
    return 300 - (time.time() % 300)


async def main() -> None:
    # ── initialise core components ────────────────────────────────────────────
    feed   = BinanceFeed()
    graph  = ForceGraph()
    clob   = PolymarketClient()
    engine = ExecutionEngine(clob)

    print("Starting Binance feed (spot + futures + aggTrade)…")
    await feed.start()
    await feed.wait_ready()
    print("Binance feed ready.")

    # ── MiroFish ──────────────────────────────────────────────────────────────
    mirofish = None
    if MIROFISH_ENABLED:
        from mirofish.client import MirofishClient
        mirofish = MirofishClient()
        engine.set_mirofish(mirofish)
        print("MiroFish enabled — will connect to localhost:5001")

    print("Discovering Polymarket BTC UP/DOWN 5MIN market…")
    found = await clob.discover_market()
    status = "Polymarket market found" if found else "market not found — dry run"

    market_state = None
    last_market_poll = 0.0
    mirofish_started = False

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

            # 1. Refresh Polymarket CLOB (throttled)
            now = time.time()
            if found and (now - last_market_poll) * 1000 >= MARKET_POLL_MS:
                market_state = await clob.get_market_state()
                last_market_poll = now

            # 2. Binance snapshot
            snap = await feed.get_snapshot()
            if not snap or not snap.klines:
                dash.update(None, None, market_state, None, None,
                            engine.risk, engine.history, "waiting for Binance…")
                await asyncio.sleep(0.05)
                continue

            # 3. Indicators
            ind = compute_indicators(snap.klines, snap.effective_price)

            # 4. Start MiroFish background simulation once we have real data
            if mirofish and not mirofish_started:
                await mirofish.start(snap, ind)
                mirofish_started = True
                status = "MiroFish simulation started…"
            elif mirofish:
                await mirofish.update_context(snap, ind)

            # 5. Force-graph signal
            yes_price = market_state.mid_yes if market_state else 0.5
            no_price  = market_state.mid_no  if market_state else 0.5
            ttc = _seconds_to_5min_close()
            sig = graph.evaluate(snap, ind, yes_price, no_price, ttc)

            # 6. Execute (three-layer gate inside engine)
            if market_state and not engine.risk.halted:
                record = await engine.evaluate_and_trade(snap, ind, market_state, sig)
                if record:
                    status = (
                        f"{record.outcome.value} {record.side} "
                        f"{record.pnl:+.2f}  lag={record.lag_at_entry:.3f}  "
                        f"age={record.edge_age_ms}ms | {record.reason}"
                    )

            # 7. Dashboard
            mf_sig = mirofish.signal if mirofish else None
            dash.update(snap, ind, market_state, sig, mf_sig,
                        engine.risk, engine.history, status)

            # 8. Pace
            elapsed_ms = (time.monotonic() - tick_start) * 1000
            sleep_ms   = max(0.0, TICK_INTERVAL_MS - elapsed_ms)
            await asyncio.sleep(sleep_ms / 1000)

    # ── shutdown ──────────────────────────────────────────────────────────────
    if mirofish:
        await mirofish.stop()
    await feed.stop()

    print("\nBot stopped cleanly.")
    r = engine.risk
    print(f"  Balance : ${r.balance:,.2f}  (started ${STARTING_BALANCE:,.2f})")
    print(f"  Day P&L : {r.daily_pnl_pct:+.2%}  ({r.daily_pnl:+.2f})")
    print(f"  Trades  : {r.trades_today}  W:{r.wins}  L:{r.losses}")


if __name__ == "__main__":
    asyncio.run(main())
