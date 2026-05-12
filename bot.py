"""
Main bot loop.

Orchestrates:
  Binance feed → Signal aggregator → Mirofish engine
  → Lag detector → Risk manager → Order manager → CLOB

Tick rate: 250ms (configurable).  Each tick:
  1. Read spot price + kline state from Binance
  2. Aggregate 100 sentiment signals
  3. Run Mirofish force-graph simulation
  4. Poll Polymarket CLOB snapshot
  5. Detect lag opportunity
  6. Execute if edge > threshold AND risk allows
  7. Log state
"""

from __future__ import annotations

import asyncio
import signal as os_signal
import time

import structlog

from config import Config
from data.binance_ws import BinanceFeed
from data.cryptoquant import CryptoQuantFeed
from data.polymarket_clob import PolymarketCLOB
from engine.lag_detector import LagDetector
from engine.mirofish import MirofishEngine
from engine.signal_aggregator import SignalAggregator
from execution.order_manager import OrderManager
from execution.risk_manager import RiskManager

log = structlog.get_logger()


class GraviaBot:
    """Polymarket BTC UP/DOWN 5MIN CLOB-lag arbitrage bot."""

    def __init__(self, config: Config, portfolio_usdc: float = 1000.0) -> None:
        self._cfg = config
        self._running = False

        self._binance = BinanceFeed(config.BINANCE_SYMBOL)
        self._cryptoquant = CryptoQuantFeed(config.CRYPTOQUANT_API_KEY)
        self._clob = PolymarketCLOB(
            host=config.POLYMARKET_HOST,
            condition_up=config.MARKET_CONDITION_UP,
            condition_down=config.MARKET_CONDITION_DOWN,
            api_key=config.POLYMARKET_API_KEY,
            api_secret=config.POLYMARKET_API_SECRET,
            api_passphrase=config.POLYMARKET_API_PASSPHRASE,
            private_key=config.POLYMARKET_PRIVATE_KEY,
            dry_run=config.DRY_RUN,
        )

        self._mirofish = MirofishEngine(
            n_nodes=config.MIROFISH_NODES,
            n_edges=config.MIROFISH_EDGES,
            iterations=config.MIROFISH_ITERATIONS,
            conv_thresh=config.CONVERGENCE_THRESHOLD,
        )
        self._aggregator = SignalAggregator(self._binance, self._cryptoquant)
        self._lag_detector = LagDetector(config.LAG_THRESHOLD)
        self._risk = RiskManager(
            portfolio_usdc=portfolio_usdc,
            per_trade_risk=config.PER_TRADE_RISK,
            daily_cap=config.DAILY_CAP,
            hard_stop=config.HARD_STOP,
        )
        self._orders = OrderManager(self._clob, self._risk)

        self._tick_count = 0
        self._last_day_reset = time.strftime("%Y-%m-%d")

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        log.info(
            "bot_starting",
            dry_run=self._cfg.DRY_RUN,
            lag_threshold=self._cfg.LAG_THRESHOLD,
            daily_cap=self._cfg.DAILY_CAP,
        )
        await asyncio.gather(
            self._binance.start(),
            self._cryptoquant.start(),
            self._clob.start(),
        )
        self._running = True
        log.info("feeds_ready")
        await self._loop()

    async def stop(self) -> None:
        self._running = False
        await asyncio.gather(
            self._binance.stop(),
            self._cryptoquant.stop(),
            self._clob.stop(),
        )
        log.info("bot_stopped", risk=self._risk.summary())

    # ── main loop ─────────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        interval = self._cfg.TICK_INTERVAL_MS / 1000

        while self._running:
            tick_start = time.perf_counter()
            try:
                await self._tick()
            except Exception as exc:
                log.exception("tick_error", error=str(exc))

            elapsed = time.perf_counter() - tick_start
            sleep_for = max(0.0, interval - elapsed)
            await asyncio.sleep(sleep_for)

    async def _tick(self) -> None:
        self._tick_count += 1
        self._maybe_reset_daily()

        spot = self._binance.state.spot_price
        if spot <= 0:
            return   # feed not yet ready

        # 1. Update lag detector with current spot
        self._lag_detector.update_spot(spot)

        # 2. Aggregate signals → sentiment array
        agg = self._aggregator.aggregate()

        # 3. Run Mirofish
        miro = self._mirofish.run(agg.sentiments)

        # 4. Poll CLOB
        snapshot = await self._clob.get_snapshot()
        if snapshot is None:
            return

        # 5. Detect lag
        signal = self._lag_detector.detect(
            clob_up_price=snapshot.raw_up_price,
            spot_price=spot,
            mirofish_direction=miro.direction,
            mirofish_confidence=miro.confidence,
        )

        # 6. Execute if edge found
        if signal and signal.has_edge and miro.confidence >= self._cfg.MIN_CONFIDENCE:
            await self._orders.execute(signal)

        # 7. Periodic status log (every 40 ticks ≈ 10s)
        if self._tick_count % 40 == 0:
            log.info(
                "status",
                tick=self._tick_count,
                spot=f"${spot:,.2f}",
                clob_up=f"{snapshot.raw_up_price:.3f}",
                mirofish=miro.direction,
                miro_conf=f"{miro.confidence:.2f}",
                miro_sep=f"{miro.separation:.2f}",
                miro_ms=f"{miro.latency_ms:.1f}ms",
                open_positions=self._orders.open_count,
                risk=self._risk.summary(),
            )

    def _maybe_reset_daily(self) -> None:
        today = time.strftime("%Y-%m-%d")
        if today != self._last_day_reset:
            self._risk.reset_daily()
            self._last_day_reset = today
            log.info("daily_reset", date=today)


# ── entry ─────────────────────────────────────────────────────────────────────

async def main(portfolio_usdc: float = 1000.0) -> None:
    cfg = Config()
    bot = GraviaBot(cfg, portfolio_usdc=portfolio_usdc)

    loop = asyncio.get_running_loop()

    def _shutdown(sig: int) -> None:
        log.info("shutdown_signal", sig=sig)
        asyncio.create_task(bot.stop())

    for sig in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig)

    await bot.start()
