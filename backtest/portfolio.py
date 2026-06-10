"""
Portfolio-level walk-forward backtester.

Methodology:
  - Divide the price history into expanding train windows and fixed-length OOS windows.
  - In each fold: fit the ranker on training data, run OOS period holding top-N names,
    rebalance at the configured frequency, charge costs on turnover.
  - Concatenate OOS periods → full OOS equity curve → pass to DSR validation.

No look-ahead: rank on data through close of day t, act at t+1 open.

⚠️  SURVIVORSHIP BIAS: see data/universe.py — this backtester inherits that
caveat and prints it prominently in every report.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from data.universe import PriceData
    from strategy.cross_sectional import CrossSectionalRanker
    from validation.overfitting import ValidationResult

logger = logging.getLogger(__name__)

SURVIVORSHIP_WARNING = (
    "⚠️  SURVIVORSHIP BIAS WARNING: Universe is current-only.  "
    "Delisted / bankrupt / merged names are excluded.  "
    "All performance figures are OPTIMISTIC upper bounds."
)


@dataclass
class BacktestConfig:
    n_top: int = 10
    rebalance_freq: str = "W"           # 'D' daily, 'W' weekly, 'M' monthly
    cost_per_side: float = 0.001        # 10 bps one-way
    min_train_days: int = 252           # minimum in-sample days per fold
    oos_days: int = 63                  # OOS window length per fold (≈ 1 quarter)
    weight_mode: str = "inv_vol"        # "inv_vol" or "equal"
    vol_window: int = 21


@dataclass
class BacktestResult:
    oos_returns: pd.Series              # daily OOS portfolio returns
    equity_curve: pd.Series             # cumulative
    sharpe_annualized: float
    max_drawdown: float
    turnover_avg: float                 # avg fraction of portfolio turned over per rebalance
    n_folds: int
    config: BacktestConfig
    survivorship_warning: str = SURVIVORSHIP_WARNING

    def summary(self) -> str:
        return (
            f"\n{'='*60}\n"
            f"BACKTEST SUMMARY\n"
            f"{self.survivorship_warning}\n"
            f"{'='*60}\n"
            f"OOS Sharpe (ann.)  : {self.sharpe_annualized:.3f}\n"
            f"Max Drawdown       : {self.max_drawdown:.1%}\n"
            f"Avg Turnover/rebal : {self.turnover_avg:.1%}\n"
            f"Walk-forward folds : {self.n_folds}\n"
            f"OOS days           : {len(self.oos_returns)}\n"
            f"{'='*60}\n"
        )


def _rebalance_dates(index: pd.DatetimeIndex, freq: str) -> pd.DatetimeIndex:
    """Return dates in `index` that fall on rebalance boundaries."""
    dummy = pd.Series(1, index=index)
    freq = "ME" if freq == "M" else freq
    resampled = dummy.resample(freq).last()
    return resampled.index.intersection(index)


def _equal_weights(tickers: list[str]) -> dict[str, float]:
    n = len(tickers)
    return {t: 1.0 / n for t in tickers} if n > 0 else {}


def _inv_vol_weights(
    tickers: list[str], close: pd.DataFrame, vol_window: int
) -> dict[str, float]:
    recent = close[tickers].pct_change().tail(vol_window + 1)
    vols = recent.std()
    inv = (1.0 / vols.replace(0, np.nan)).dropna()
    total = inv.sum()
    if total == 0:
        return _equal_weights(tickers)
    return (inv / total).to_dict()


def _portfolio_return(
    weights: dict[str, float],
    returns_row: pd.Series,
) -> float:
    """Weighted portfolio return for a single period."""
    total = 0.0
    for ticker, w in weights.items():
        r = returns_row.get(ticker, np.nan)
        if np.isfinite(r):
            total += w * r
    return total


def _turnover(old_weights: dict[str, float], new_weights: dict[str, float]) -> float:
    """Sum of absolute weight changes — half-turn (one-way)."""
    all_tickers = set(old_weights) | set(new_weights)
    return sum(abs(new_weights.get(t, 0) - old_weights.get(t, 0)) for t in all_tickers) / 2


def run_backtest(
    prices: "PriceData",
    ranker: "CrossSectionalRanker",
    features: dict[str, pd.DataFrame],
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """
    Walk-forward portfolio backtest.

    Train the ranker on expanding windows, collect OOS returns each fold,
    charge transaction costs on turnover at each rebalance.
    """
    from features.library import compute_features, compute_forward_returns

    if config is None:
        config = BacktestConfig(n_top=ranker.config.n_top)

    close = prices.close
    open_ = prices.open

    # Ensure DatetimeIndex
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index)
        open_.index = pd.to_datetime(open_.index)
        for feat_df in features.values():
            feat_df.index = pd.to_datetime(feat_df.index)

    dates = close.index
    total_days = len(dates)

    if total_days < config.min_train_days + config.oos_days:
        raise ValueError(
            f"Not enough data: have {total_days} days, need at least "
            f"{config.min_train_days + config.oos_days}."
        )

    forward_returns = compute_forward_returns(close, horizon=1)

    all_oos_returns: list[pd.Series] = []
    fold = 0

    train_end_idx = config.min_train_days - 1

    while train_end_idx + config.oos_days < total_days:
        fold += 1
        train_end = dates[train_end_idx]
        oos_start_idx = train_end_idx + 1
        oos_end_idx = min(train_end_idx + config.oos_days, total_days - 1)
        oos_dates = dates[oos_start_idx : oos_end_idx + 1]

        logger.debug(
            "Fold %d: train through %s, OOS %s–%s",
            fold, train_end, oos_dates[0], oos_dates[-1],
        )

        # Fit on training data
        ranker.fit(
            features=features,
            forward_returns=forward_returns,
            in_sample_end=train_end,
        )

        # Simulate OOS trading
        oos_returns = _simulate_oos(
            prices=prices,
            ranker=ranker,
            oos_dates=oos_dates,
            config=config,
        )
        all_oos_returns.append(oos_returns)
        train_end_idx = oos_end_idx  # expand training window

    if not all_oos_returns:
        raise RuntimeError("No OOS folds generated.")

    oos = pd.concat(all_oos_returns).sort_index()
    equity = (1 + oos).cumprod()
    sharpe = _annualized_sharpe(oos)
    mdd = _max_drawdown(equity)
    avg_turnover = float(np.mean([r.attrs.get("avg_turnover", 0) for r in all_oos_returns]))

    result = BacktestResult(
        oos_returns=oos,
        equity_curve=equity,
        sharpe_annualized=sharpe,
        max_drawdown=mdd,
        turnover_avg=avg_turnover,
        n_folds=fold,
        config=config,
    )
    logger.info(result.summary())
    return result


def _simulate_oos(
    prices: "PriceData",
    ranker: "CrossSectionalRanker",
    oos_dates: pd.DatetimeIndex,
    config: BacktestConfig,
) -> pd.Series:
    """Simulate one OOS window, returning daily portfolio return series."""
    close = prices.close
    open_ = prices.open

    rebal_dates = set(_rebalance_dates(oos_dates, config.rebalance_freq))

    current_weights: dict[str, float] = {}
    daily_returns: dict[pd.Timestamp, float] = {}
    turnovers: list[float] = []

    daily_returns_close = close.pct_change()

    for date in oos_dates:
        if date in rebal_dates or not current_weights:
            picks = ranker.select_top_n(date)
            tickers = [t for t, _ in picks]

            if config.weight_mode == "inv_vol":
                new_weights = _inv_vol_weights(tickers, close.loc[:date], config.vol_window)
            else:
                new_weights = _equal_weights(tickers)

            to = _turnover(current_weights, new_weights)
            turnovers.append(to)
            current_weights = new_weights

        if date in daily_returns_close.index:
            ret_row = daily_returns_close.loc[date]
            gross = _portfolio_return(current_weights, ret_row)
            # charge cost only on rebalance days
            cost = config.cost_per_side * turnovers[-1] if (date in rebal_dates and turnovers) else 0.0
            daily_returns[date] = gross - cost

    series = pd.Series(daily_returns)
    series.attrs["avg_turnover"] = float(np.mean(turnovers)) if turnovers else 0.0
    return series


def _annualized_sharpe(returns: pd.Series, periods: int = 252) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * np.sqrt(periods))


def _max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    return float(drawdown.min())


def run_validation(
    backtest_result: BacktestResult,
    n_trials: int,
    dsr_threshold: float = 0.95,
) -> "ValidationResult":
    """Compute DSR from backtest OOS returns and return ValidationResult."""
    from validation.overfitting import deflated_sharpe_ratio

    result = deflated_sharpe_ratio(
        returns=backtest_result.oos_returns,
        n_trials=n_trials,
        threshold=dsr_threshold,
    )
    print(f"\n{SURVIVORSHIP_WARNING}\n{result}\n")
    return result
