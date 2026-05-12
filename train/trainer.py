"""
Training pipeline.

Downloads historical BTC candles → builds train/test environments →
trains a PPO agent → saves model to models/btc_ppo_<timestamp>.zip

Usage:
    python -m train.trainer                  # 1 year of data, 500k steps
    python -m train.trainer --days 730 --steps 2000000
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import (
    BaseCallback,
    CheckpointCallback,
    EvalCallback,
)
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from train.data_loader import download_candles, train_test_split
from train.env import BTCTradingEnv

MODELS_DIR = Path("models")


class PortfolioLogCallback(BaseCallback):
    """Logs portfolio value and win rate to tensorboard every N episodes."""

    def __init__(self, verbose: int = 0) -> None:
        super().__init__(verbose)
        self._ep_portfolios: list[float] = []

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        for info in infos:
            if "portfolio" in info:
                self._ep_portfolios.append(info["portfolio"])
        if len(self._ep_portfolios) >= 10:
            mean_port = np.mean(self._ep_portfolios[-10:])
            self.logger.record("train/mean_portfolio", mean_port)
            self._ep_portfolios = self._ep_portfolios[-100:]
        return True


def make_env(df, episode_bars: int = 2016):
    def _init():
        return BTCTradingEnv(df, episode_bars=episode_bars)
    return _init


def train(
    days: int = 365,
    total_steps: int = 500_000,
    episode_bars: int = 2016,
    n_envs: int = 4,
) -> Path:
    MODELS_DIR.mkdir(exist_ok=True)

    # ── data ─────────────────────────────────────────────────────────────────
    df = asyncio.run(download_candles(days=days))
    train_df, test_df = train_test_split(df)
    print(f"Train: {len(train_df):,} bars | Test: {len(test_df):,} bars")

    # ── environments ─────────────────────────────────────────────────────────
    train_env = make_vec_env(make_env(train_df, episode_bars), n_envs=n_envs)
    train_env = VecNormalize(train_env, norm_obs=True, norm_reward=True, clip_obs=10.0)

    eval_env = DummyVecEnv([make_env(test_df, episode_bars)])
    eval_env = VecNormalize(eval_env, norm_obs=True, norm_reward=False, clip_obs=10.0,
                            training=False)

    # ── model ─────────────────────────────────────────────────────────────────
    # Policy network: two hidden layers of 256 units each
    policy_kwargs = dict(net_arch=[256, 256])
    model = PPO(
        "MlpPolicy",
        train_env,
        n_steps=2048,
        batch_size=256,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.005,          # encourage exploration
        learning_rate=3e-4,
        policy_kwargs=policy_kwargs,
        tensorboard_log="models/tb_logs",
        verbose=1,
    )

    # ── callbacks ─────────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    checkpoint_cb = CheckpointCallback(
        save_freq=50_000,
        save_path=str(MODELS_DIR / "checkpoints"),
        name_prefix=f"btc_ppo_{ts}",
    )
    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=str(MODELS_DIR),
        log_path=str(MODELS_DIR / "eval_logs"),
        eval_freq=25_000,
        n_eval_episodes=10,
        deterministic=True,
    )
    log_cb = PortfolioLogCallback()

    # ── train ─────────────────────────────────────────────────────────────────
    print(f"\nTraining PPO for {total_steps:,} steps across {n_envs} parallel envs...")
    model.learn(
        total_timesteps=total_steps,
        callback=[checkpoint_cb, eval_cb, log_cb],
        progress_bar=True,
    )

    # ── save ─────────────────────────────────────────────────────────────────
    model_path = MODELS_DIR / f"btc_ppo_{ts}.zip"
    norm_path = MODELS_DIR / f"btc_ppo_{ts}_vecnorm.pkl"
    model.save(str(model_path))
    train_env.save(str(norm_path))
    print(f"\nModel saved → {model_path}")
    print(f"VecNormalize → {norm_path}")
    return model_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--steps", type=int, default=500_000)
    parser.add_argument("--episode-bars", type=int, default=2016)
    parser.add_argument("--envs", type=int, default=4)
    args = parser.parse_args()
    train(args.days, args.steps, args.episode_bars, args.envs)
