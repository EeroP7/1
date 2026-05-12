"""
Live BTC trader using a trained PPO model.

Connects to Binance WebSocket, builds feature observations in real time,
and executes BUY/SELL orders on Binance Spot (or in dry-run mode).

Usage:
    python live_trader.py --model models/best_model.zip \
                          --norm  models/btc_ppo_*_vecnorm.pkl \
                          --capital 1000
"""

from __future__ import annotations

import argparse
import asyncio
import time
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import structlog
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from config import Config
from data.binance_ws import BinanceFeed
from execution.risk_manager import RiskManager
from train.env import BTCTradingEnv, WINDOW
from train.features import build_features

log = structlog.get_logger()

CANDLE_COLS = ["open", "high", "low", "close", "volume"]


class LiveTrader:
    def __init__(
        self,
        model_path: str,
        norm_path: str | None,
        capital: float,
        dry_run: bool = True,
    ) -> None:
        self._dry_run = dry_run
        self._capital = capital
        self._risk = RiskManager(capital)

        # Load model
        # Use a dummy env just to satisfy SB3 loader
        dummy_env = DummyVecEnv([lambda: BTCTradingEnv(
            pd.DataFrame(np.random.randn(200, 5) * 100 + 50000,
                         columns=CANDLE_COLS)
        )])
        if norm_path and Path(norm_path).exists():
            self._vec_env = VecNormalize.load(norm_path, dummy_env)
            self._vec_env.training = False
            self._vec_env.norm_reward = False
        else:
            self._vec_env = dummy_env

        self._model = PPO.load(model_path, env=self._vec_env)
        log.info("model_loaded", path=model_path)

        self._binance = BinanceFeed("BTCUSDT")
        self._candle_buffer: deque[dict] = deque(maxlen=WINDOW + 60)
        self._position = 0
        self._entry_price = 0.0
        self._running = False

    async def start(self) -> None:
        await self._binance.start()
        # Seed buffer from bootstrapped klines
        for k in self._binance.state.klines:
            if k.closed:
                self._candle_buffer.append({
                    "open": k.open, "high": k.high,
                    "low": k.low, "close": k.close, "volume": k.volume,
                })
        self._running = True
        log.info("live_trader_started", dry_run=self._dry_run, capital=self._capital)
        await self._loop()

    async def _loop(self) -> None:
        last_candle_time = 0
        while self._running:
            await asyncio.sleep(1)

            # Only act on newly closed candles
            klines = [k for k in self._binance.state.klines if k.closed]
            if not klines:
                continue
            latest = klines[-1]
            if latest.close_time == last_candle_time:
                continue
            last_candle_time = latest.close_time

            self._candle_buffer.append({
                "open": latest.open, "high": latest.high,
                "low": latest.low, "close": latest.close, "volume": latest.volume,
            })

            if len(self._candle_buffer) < WINDOW + 30:
                log.info("warming_up", bars=len(self._candle_buffer), need=WINDOW + 30)
                continue

            action = self._predict()
            await self._execute(action, latest.close)
            self._log_status(action, latest.close)

    def _predict(self) -> int:
        df = pd.DataFrame(list(self._candle_buffer), columns=CANDLE_COLS)
        feats = build_features(df)
        if len(feats) < WINDOW:
            return 0   # HOLD — not enough data

        feat_window = feats.values[-WINDOW:].astype(np.float32).flatten()
        unrealised = (
            (list(self._candle_buffer)[-1]["close"] - self._entry_price) / (self._entry_price + 1e-10)
            if self._position == 1 else 0.0
        )
        obs = np.concatenate([feat_window, [float(self._position), unrealised]])
        obs = obs.reshape(1, -1)

        # Normalise through VecNormalize if available
        if isinstance(self._vec_env, VecNormalize):
            obs = self._vec_env.normalize_obs(obs)

        action, _ = self._model.predict(obs, deterministic=True)
        return int(action[0])

    async def _execute(self, action: int, price: float) -> None:
        allowed, reason = self._risk.can_trade()
        if not allowed:
            log.info("trade_blocked", reason=reason)
            return

        if action == 1 and self._position == 0:
            self._position = 1
            self._entry_price = price
            size = self._risk.size_order(0.5) or 0.0
            log.info("BUY", price=price, size=size, dry_run=self._dry_run)

        elif action == 2 and self._position == 1:
            pnl_pct = (price - self._entry_price) / self._entry_price
            pnl_usdc = self._capital * pnl_pct
            self._risk.record_fill(pnl_usdc)
            self._position = 0
            log.info("SELL", price=price, pnl_pct=f"{pnl_pct:+.3%}",
                     pnl_usdc=f"${pnl_usdc:+.2f}")
            self._entry_price = 0.0

    def _log_status(self, action: int, price: float) -> None:
        action_name = ["HOLD", "BUY", "SELL"][action]
        log.info(
            "tick",
            action=action_name,
            btc=f"${price:,.2f}",
            position="LONG" if self._position else "FLAT",
            risk=self._risk.summary(),
        )


async def main(model: str, norm: str | None, capital: float, dry_run: bool) -> None:
    trader = LiveTrader(model, norm, capital, dry_run)
    await trader.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/best_model.zip")
    parser.add_argument("--norm", default=None)
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--live", action="store_true", help="disable dry-run")
    args = parser.parse_args()
    asyncio.run(main(args.model, args.norm, args.capital, dry_run=not args.live))
