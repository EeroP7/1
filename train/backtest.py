"""
Walk-forward backtester.

Loads a trained PPO model and runs it on held-out test data.
Prints performance metrics and saves an equity curve plot.

Usage:
    python -m train.backtest --model models/best_model.zip \
                              --norm  models/btc_ppo_*_vecnorm.pkl
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from train.data_loader import download_candles, train_test_split
from train.env import BTCTradingEnv


def run_backtest(
    model_path: str,
    norm_path: str | None,
    days: int = 365,
    initial_capital: float = 10_000.0,
) -> dict:
    df = asyncio.run(download_candles(days=days))
    _, test_df = train_test_split(df)

    env = BTCTradingEnv(test_df, episode_bars=len(test_df) - 61, initial_capital=initial_capital)
    vec_env = DummyVecEnv([lambda: env])

    if norm_path and Path(norm_path).exists():
        vec_env = VecNormalize.load(norm_path, vec_env)
        vec_env.training = False
        vec_env.norm_reward = False

    model = PPO.load(model_path, env=vec_env)

    obs = vec_env.reset()
    portfolios = [initial_capital]
    actions_taken = []
    done = False

    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, info = vec_env.step(action)
        portfolios.append(info[0]["portfolio"])
        actions_taken.append(int(action[0]))
        done = bool(terminated[0])

    portfolios = np.array(portfolios)
    returns = np.diff(portfolios) / portfolios[:-1]

    total_return = (portfolios[-1] / portfolios[0] - 1) * 100
    sharpe = returns.mean() / (returns.std() + 1e-10) * np.sqrt(252 * 288)  # annualised
    max_dd = _max_drawdown(portfolios)
    buy_hold = (test_df["close"].iloc[-1] / test_df["close"].iloc[60] - 1) * 100

    metrics = {
        "total_return_pct": round(total_return, 2),
        "buy_hold_pct": round(buy_hold, 2),
        "sharpe_annualised": round(sharpe, 3),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "final_portfolio": round(portfolios[-1], 2),
        "n_buys": actions_taken.count(1),
        "n_sells": actions_taken.count(2),
    }

    _print_metrics(metrics)
    _plot(portfolios, test_df, actions_taken)
    return metrics


def _max_drawdown(portfolio: np.ndarray) -> float:
    peak = np.maximum.accumulate(portfolio)
    dd = (portfolio - peak) / (peak + 1e-10)
    return float(dd.min())


def _print_metrics(m: dict) -> None:
    print("\n── Backtest Results ─────────────────────────────────")
    print(f"  Total return:      {m['total_return_pct']:+.2f}%")
    print(f"  Buy & hold:        {m['buy_hold_pct']:+.2f}%")
    print(f"  Sharpe (annual):   {m['sharpe_annualised']:.3f}")
    print(f"  Max drawdown:      {m['max_drawdown_pct']:.2f}%")
    print(f"  Final portfolio:   ${m['final_portfolio']:,.2f}")
    print(f"  Trades (buy/sell): {m['n_buys']} / {m['n_sells']}")
    print("─────────────────────────────────────────────────────\n")


def _plot(portfolios: np.ndarray, test_df: pd.DataFrame, actions: list) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    ax1.plot(portfolios, label="Agent portfolio", color="steelblue", linewidth=1.2)
    bh_start = portfolios[0]
    closes = test_df["close"].values[60: 60 + len(portfolios)]
    bh = bh_start * closes / closes[0]
    ax1.plot(bh[: len(portfolios)], label="Buy & hold", color="orange",
             linewidth=1.0, linestyle="--")
    ax1.set_ylabel("Portfolio ($)")
    ax1.legend()
    ax1.set_title("RL Agent vs Buy & Hold — BTC 5M")

    ax2.plot(closes[: len(actions)], color="grey", linewidth=0.8, label="BTC price")
    buy_idx = [i for i, a in enumerate(actions) if a == 1]
    sell_idx = [i for i, a in enumerate(actions) if a == 2]
    ax2.scatter(buy_idx, closes[buy_idx], marker="^", color="green", s=30, zorder=5, label="BUY")
    ax2.scatter(sell_idx, closes[sell_idx], marker="v", color="red", s=30, zorder=5, label="SELL")
    ax2.set_ylabel("BTC/USDT")
    ax2.set_xlabel("Bar")
    ax2.legend()

    plt.tight_layout()
    out = Path("models/backtest_equity.png")
    plt.savefig(out, dpi=150)
    print(f"Equity curve saved → {out}")
    plt.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/best_model.zip")
    parser.add_argument("--norm", default=None)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--capital", type=float, default=10_000.0)
    args = parser.parse_args()
    run_backtest(args.model, args.norm, args.days, args.capital)
