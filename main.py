"""
Polymarket dual-strategy bot.

Strategy A — BTC UP/DOWN 5MIN arbitrage
  Binance futures mark price lag vs Polymarket CLOB,
  confirmed by MiroFish swarm + force-graph physics simulation.

Strategy B — Leaderboard copy trading
  Polls top-20 Polymarket wallets by all-time PNL every 15s,
  mirrors new BUY trades with scaled size.

Both strategies share one RiskState (daily cap applies across both).

Run:  python main.py
Stop: Ctrl-C
"""
import asyncio
import logging
import signal
import time

from config import (
    MIROFISH_ENABLED, COPY_ENABLED, STARTING_BALANCE, MOMENTUM_ENABLED,
)
from copytrading.engine import CopyEngine
from copytrading.tracker import WalletTracker
from execution.engine import ExecutionEngine, MomentumEngine, RiskState
from feeds.binance_ws import BinanceFeed
from feeds.indicators import compute as compute_indicators
from polymarket.clob_client import PolymarketClient
from forcegraph.force_graph import ForceGraph
from terminal.display import Dashboard

logging.basicConfig(level=logging.WARNING)

TICK_INTERVAL_MS = 100
MARKET_POLL_MS   = 200


def _seconds_to_5min_close() -> float:
    return 300 - (time.time() % 300)


async def main() -> None:
    # ── shared components ─────────────────────────────────────────────────────
    clob       = PolymarketClient()
    shared_risk = RiskState(balance=STARTING_BALANCE)

    # ── Strategy A: BTC arbitrage ─────────────────────────────────────────────
    feed   = BinanceFeed()
    graph  = ForceGraph()
    arb_engine      = ExecutionEngine(clob, shared_risk)
    momentum_engine = MomentumEngine(clob, shared_risk) if MOMENTUM_ENABLED else None

    print("Starting Binance feed…")
    await feed.start()
    await feed.wait_ready()
    print("Binance feed ready.")

    # ── MiroFish ──────────────────────────────────────────────────────────────
    mirofish = None
    if MIROFISH_ENABLED:
        from mirofish.client import MirofishClient
        mirofish = MirofishClient()
        arb_engine.set_mirofish(mirofish)
        print("MiroFish enabled — connecting to localhost:5001")

    # ── Strategy B: copy trading ──────────────────────────────────────────────
    copy_tracker = None
    copy_engine  = None
    if COPY_ENABLED:
        signal_queue = asyncio.Queue()
        copy_tracker = WalletTracker(signal_queue)
        copy_engine  = CopyEngine(clob, shared_risk, signal_queue)
        await copy_tracker.start()
        await copy_engine.start()
        print(f"Copy trading enabled — tracking top wallets")

    # ── Polymarket market discovery ───────────────────────────────────────────
    print("Discovering Polymarket Bitcoin Up-or-Down market…")
    found  = await clob.discover_market()
    status = (f"market: {clob.market_question[:48]}" if found
              else "BTC market not found yet — copy only")

    market_state     = None
    last_market_poll = 0.0
    last_discover    = time.time()
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

            # re-discover when market missing or its window has rolled over
            now = time.time()
            if (not found or clob.market_ended()) and now - last_discover >= 20:
                found = await clob.discover_market()
                last_discover = now
                if found:
                    market_state = None
                    status = f"market: {clob.market_question[:48]}"

            # CLOB poll (throttled)
            if found and (now - last_market_poll) * 1000 >= MARKET_POLL_MS:
                market_state = await clob.get_market_state()
                last_market_poll = now

            # Binance snapshot
            snap = await feed.get_snapshot()
            if not snap or not snap.klines:
                dash.update(None, None, market_state, None, None,
                            shared_risk, arb_engine.history,
                            copy_tracker, copy_engine, "waiting for Binance…")
                await asyncio.sleep(0.05)
                continue

            # Indicators
            ind = compute_indicators(snap.klines, snap.effective_price)

            # Start MiroFish once data is live
            if mirofish and not mirofish_started:
                await mirofish.start(snap, ind)
                mirofish_started = True
                status = "MiroFish simulation started…"
            elif mirofish:
                await mirofish.update_context(snap, ind)

            # Force-graph signal
            yes_price = market_state.mid_yes if market_state else 0.5
            no_price  = market_state.mid_no  if market_state else 0.5
            ttc = _seconds_to_5min_close()
            sig = graph.evaluate(snap, ind, yes_price, no_price, ttc)

            # Strategy A: arb
            if market_state and not shared_risk.halted:
                record = await arb_engine.evaluate_and_trade(snap, ind, market_state, sig)
                if record:
                    status = (
                        f"ARB {record.outcome.value} {record.side} "
                        f"{record.pnl:+.2f}  lag={record.lag_at_entry:.3f} | {record.reason}"
                    )

            # Strategy C: momentum bet once per window
            if momentum_engine and market_state and not shared_risk.halted:
                ms = await momentum_engine.evaluate(snap, market_state)
                if ms:
                    status = ms

            # Dashboard
            mf_sig = mirofish.signal if mirofish else None
            dash.update(snap, ind, market_state, sig, mf_sig,
                        shared_risk, arb_engine.history,
                        copy_tracker, copy_engine, status)

            # Pace
            elapsed_ms = (time.monotonic() - tick_start) * 1000
            await asyncio.sleep(max(0.0, TICK_INTERVAL_MS - elapsed_ms) / 1000)

    # ── shutdown ──────────────────────────────────────────────────────────────
    if copy_tracker:
        await copy_tracker.stop()
    if copy_engine:
        await copy_engine.stop()
    if mirofish:
        await mirofish.stop()
    await feed.stop()

    print("\nBot stopped.")
    r = shared_risk
    total_trades = r.trades_today
    print(f"  Balance : ${r.balance:,.2f}  (started ${STARTING_BALANCE:,.2f})")
    print(f"  Day P&L : {r.daily_pnl_pct:+.2%}  ({r.daily_pnl:+.2f})")
    print(f"  Trades  : {total_trades}  W:{r.wins}  L:{r.losses}")


if __name__ == "__main__":
    asyncio.run(main())
