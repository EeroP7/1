"""
BTC trading Gymnasium environment.

The agent observes a rolling window of 60 feature vectors (candles) plus
its current position and unrealised P&L, then chooses an action each bar.

Actions
-------
  0 = HOLD    keep current position
  1 = BUY     enter / stay long (100% of capital)
  2 = SELL    exit to cash (flat)

Reward
------
  Step reward = log portfolio return for this bar
  Shaped with a small Sharpe-ratio bonus over a rolling window to
  discourage thrashing and reward consistency.

Episode
-------
  Starts at a random offset in the training data.
  Ends after `episode_bars` steps or when data runs out.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from train.features import build_features

TRANSACTION_COST = 0.001   # 0.1% per trade (Binance taker fee)
WINDOW = 60                # observation look-back in bars


class BTCTradingEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        df: pd.DataFrame,
        episode_bars: int = 2016,     # ~1 week of 5M candles
        window: int = WINDOW,
        initial_capital: float = 10_000.0,
        transaction_cost: float = TRANSACTION_COST,
    ) -> None:
        super().__init__()
        self._raw_df = df.reset_index(drop=True)
        self._features = build_features(df).reset_index(drop=True)
        self._closes = self._raw_df["close"].values.astype(np.float64)

        # Align: features may have fewer rows (NaN drop)
        feat_start = len(self._raw_df) - len(self._features)
        self._closes = self._closes[feat_start:]
        self._feat_arr = self._features.values.astype(np.float32)

        self._episode_bars = episode_bars
        self._window = window
        self._initial_capital = initial_capital
        self._tc = transaction_cost

        n_features = self._feat_arr.shape[1]
        # Observation: flattened window + [position, unrealised_pnl]
        obs_size = window * n_features + 2
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_size,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(3)   # 0=HOLD, 1=BUY, 2=SELL

        self._step = 0
        self._start_idx = 0
        self._position = 0        # 0=flat, 1=long
        self._entry_price = 0.0
        self._portfolio = initial_capital
        self._reward_history: list[float] = []

    # ── gym API ───────────────────────────────────────────────────────────────

    def reset(
        self, *, seed: Optional[int] = None, options: Optional[dict] = None
    ) -> Tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        max_start = len(self._feat_arr) - self._episode_bars - self._window - 1
        if max_start <= 0:
            self._start_idx = 0
        else:
            self._start_idx = self.np_random.integers(0, max_start)
        self._step = 0
        self._position = 0
        self._entry_price = 0.0
        self._portfolio = self._initial_capital
        self._reward_history = []
        return self._obs(), {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, dict]:
        idx = self._start_idx + self._window + self._step
        prev_close = self._closes[idx - 1]
        curr_close = self._closes[idx]

        prev_portfolio = self._portfolio
        cost = 0.0

        # ── apply action ──────────────────────────────────────────────────────
        if action == 1 and self._position == 0:     # BUY
            self._position = 1
            self._entry_price = curr_close
            cost = self._tc * self._portfolio

        elif action == 2 and self._position == 1:   # SELL
            pnl_pct = (curr_close - self._entry_price) / self._entry_price
            self._portfolio *= (1 + pnl_pct)
            cost = self._tc * self._portfolio
            self._portfolio -= cost
            self._position = 0
            self._entry_price = 0.0

        # ── mark-to-market while long ─────────────────────────────────────────
        if self._position == 1:
            bar_ret = (curr_close - prev_close) / prev_close
            self._portfolio *= (1 + bar_ret)

        self._portfolio -= cost

        # ── reward: log return + Sharpe shaping ───────────────────────────────
        log_ret = np.log(self._portfolio / (prev_portfolio + 1e-10))
        self._reward_history.append(log_ret)
        reward = float(log_ret)

        # Rolling Sharpe bonus (every 20 steps)
        if len(self._reward_history) >= 20:
            r_arr = np.array(self._reward_history[-20:])
            sharpe = r_arr.mean() / (r_arr.std() + 1e-8) * np.sqrt(20)
            reward += 0.01 * float(sharpe)

        self._step += 1
        done = self._step >= self._episode_bars or (idx + 1) >= len(self._closes)

        unrealised = (
            (curr_close - self._entry_price) / self._entry_price
            if self._position == 1 else 0.0
        )
        info = {
            "portfolio": self._portfolio,
            "position": self._position,
            "unrealised_pnl": unrealised,
        }
        return self._obs(), reward, done, False, info

    def _obs(self) -> np.ndarray:
        idx = self._start_idx + self._window + self._step
        window_feats = self._feat_arr[idx - self._window: idx].flatten()
        extras = np.array(
            [
                float(self._position),
                float(
                    (self._closes[idx - 1] - self._entry_price) / (self._entry_price + 1e-10)
                    if self._position == 1
                    else 0.0
                ),
            ],
            dtype=np.float32,
        )
        return np.concatenate([window_feats, extras])
