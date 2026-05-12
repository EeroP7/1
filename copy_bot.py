"""
Copy trading bot.

Fetches top Polymarket wallets, monitors their trades in real time,
and mirrors them proportionally on our account.

Can run standalone or alongside the arbitrage bot (they share the
RiskManager so daily caps are respected across both strategies).

Usage:
    python copy_bot.py --capital 1000 --top 20
    python copy_bot.py --capital 1000 --pin 0xGraviaWalletAddress --top 10
    python copy_bot.py --capital 1000 --only-pinned --pin 0xWallet1 --pin 0xWallet2
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal as os_signal
import time

import structlog
from dotenv import load_dotenv

from config import Config
from copy_trader.copy_executor import CopyExecutor
from copy_trader.leaderboard import Leaderboard
from copy_trader.wallet_monitor import WalletMonitor
from data.polymarket_clob import PolymarketCLOB
from execution.risk_manager import RiskManager

load_dotenv()
log = structlog.get_logger()


class CopyBot:
    def __init__(
        self,
        config: Config,
        portfolio_usdc: float,
        top_n: int = 20,
        pinned_addresses: list[str] | None = None,
        only_pinned: bool = False,
        scale_factor: float = 0.5,
        min_wallet_profit: float = 5_000.0,    # only follow wallets with >$5K profit
        poll_interval: int = 30,
    ) -> None:
        self._cfg = config
        self._only_pinned = only_pinned
        self._min_profit = min_wallet_profit

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
        self._risk = RiskManager(
            portfolio_usdc=portfolio_usdc,
            per_trade_risk=config.PER_TRADE_RISK,
            daily_cap=config.DAILY_CAP,
            hard_stop=config.HARD_STOP,
        )
        self._executor = CopyExecutor(
            clob=self._clob,
            risk=self._risk,
            scale_factor=scale_factor,
        )
        self._monitor = WalletMonitor(
            on_trade=self._executor.on_trade,
            poll_interval=poll_interval,
            min_trade_size_usdc=50.0,
        )
        self._leaderboard = Leaderboard(
            top_n=0 if only_pinned else top_n,
            pinned_addresses=pinned_addresses or [],
            refresh_interval=3600,
        )
        self._running = False

    async def start(self) -> None:
        log.info(
            "copy_bot_starting",
            dry_run=self._cfg.DRY_RUN,
            only_pinned=self._only_pinned,
        )
        await asyncio.gather(
            self._clob.start(),
            self._leaderboard.start(),
            self._monitor.start(),
            self._executor.start(),
        )
        self._running = True

        # Initial wallet sync
        await self._sync_wallets()

        # Periodic resync loop
        asyncio.create_task(self._resync_loop())

        log.info("copy_bot_ready", watching=self._monitor.watched_count)
        await self._status_loop()

    async def stop(self) -> None:
        self._running = False
        await asyncio.gather(
            self._clob.stop(),
            self._leaderboard.stop(),
            self._monitor.stop(),
            self._executor.stop(),
        )
        log.info("copy_bot_stopped", risk=self._risk.summary())

    async def _sync_wallets(self) -> None:
        wallets = await self._leaderboard.get_wallets()
        added = 0
        for w in wallets:
            if self._only_pinned and w.rank != 0:
                continue
            if w.profit_usdc < self._min_profit and w.rank != 0:
                continue
            if not w.address:
                continue
            self._monitor.watch(w.address, w.name)
            added += 1
        log.info("wallets_synced", added=added, total=self._monitor.watched_count)

    async def _resync_loop(self) -> None:
        while self._running:
            await asyncio.sleep(3600)
            await self._sync_wallets()

    async def _status_loop(self) -> None:
        while self._running:
            await asyncio.sleep(60)
            log.info(
                "copy_status",
                watching=self._monitor.watched_count,
                executor=self._executor.summary(),
                risk=self._risk.summary(),
            )


async def main(
    capital: float,
    top_n: int,
    pinned: list[str],
    only_pinned: bool,
    scale: float,
) -> None:
    cfg = Config()
    bot = CopyBot(
        config=cfg,
        portfolio_usdc=capital,
        top_n=top_n,
        pinned_addresses=pinned,
        only_pinned=only_pinned,
        scale_factor=scale,
    )

    loop = asyncio.get_running_loop()

    def _shutdown(sig: int) -> None:
        log.info("shutdown", sig=sig)
        asyncio.create_task(bot.stop())

    for sig in (os_signal.SIGINT, os_signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig)

    await bot.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capital", type=float, default=1000.0,
                        help="Portfolio size in USDC")
    parser.add_argument("--top", type=int, default=20,
                        help="Number of top leaderboard wallets to follow")
    parser.add_argument("--pin", action="append", default=[],
                        dest="pinned", metavar="ADDRESS",
                        help="Always-follow wallet address (repeatable)")
    parser.add_argument("--only-pinned", action="store_true",
                        help="Follow pinned wallets only, ignore leaderboard")
    parser.add_argument("--scale", type=float, default=0.5,
                        help="Copy scale factor (0.5 = 50%% of their size)")
    args = parser.parse_args()
    asyncio.run(main(args.capital, args.top, args.pinned, args.only_pinned, args.scale))
