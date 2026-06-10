"""
Deflated Sharpe Ratio (DSR) — Bailey & Lopez de Prado (2014).

The DSR answers: given that we searched over N_trials parameter combinations
and picked the best, what is the probability that the true Sharpe of the
selected strategy is positive?

A DSR >= 0.95 (the default threshold) is required before the ranker is
permitted to trade.

References:
  Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting and Non-Normality.
  Journal of Portfolio Management, 40(5), 94-107.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

EULER_MASCHERONI = 0.5772156649


@dataclass
class ValidationResult:
    sharpe_annualized: float
    probabilistic_sharpe: float     # PSR(SR* = 0)
    deflated_sharpe: float          # DSR — the threshold-checked value
    expected_max_sharpe: float      # E[max SR] under N_trials
    n_trials: int
    n_obs: int
    skewness: float
    kurtosis: float
    passes: bool
    threshold: float
    message: str

    def __str__(self) -> str:
        status = "✅ PASS" if self.passes else "❌ FAIL"
        return (
            f"{status} | DSR={self.deflated_sharpe:.3f} (threshold={self.threshold}) | "
            f"Ann.SR={self.sharpe_annualized:.3f} | "
            f"E[max SR]={self.expected_max_sharpe:.3f} over {self.n_trials} trials | "
            f"n_obs={self.n_obs}"
        )


def annualized_sharpe(returns: pd.Series | np.ndarray, periods_per_year: int = 252) -> float:
    r = np.asarray(returns)
    r = r[~np.isnan(r)]
    if len(r) < 2:
        return 0.0
    mean = np.mean(r)
    std = np.std(r, ddof=1)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(periods_per_year)


def _expected_max_sharpe(n_trials: int, n_obs: int) -> float:
    """
    E[max SR | N_trials] using Bailey-Lopez de Prado formula.
    Equation (7) in the paper.
    """
    if n_trials <= 1:
        return 0.0
    # approximation valid for large N_trials
    e_max = (
        (1 - EULER_MASCHERONI) * stats.norm.ppf(1 - 1.0 / n_trials)
        + EULER_MASCHERONI * stats.norm.ppf(1 - 1.0 / (n_trials * math.e))
    )
    # scale by sqrt(n_obs) for the sample SR distribution
    return e_max / math.sqrt(n_obs) if n_obs > 0 else e_max


def probabilistic_sharpe_ratio(
    returns: pd.Series | np.ndarray,
    sr_benchmark: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """
    P(SR > sr_benchmark) given the in-sample return series.
    Accounts for non-normality via skewness and kurtosis.
    """
    r = np.asarray(returns)
    r = r[~np.isnan(r)]
    n = len(r)
    if n < 4:
        return 0.0

    sr = annualized_sharpe(r, periods_per_year)
    sr_daily = sr / math.sqrt(periods_per_year)
    sr_bench_daily = sr_benchmark / math.sqrt(periods_per_year)

    skew = float(pd.Series(r).skew())
    kurt = float(pd.Series(r).kurtosis())   # excess kurtosis

    # variance of sample Sharpe estimator (Lo 2002 adjusted for non-normality)
    var_sr = (1 - skew * sr_daily + ((kurt + 2) / 4) * sr_daily**2) / (n - 1)
    if var_sr <= 0:
        return float(sr_daily > sr_bench_daily)

    z = (sr_daily - sr_bench_daily) / math.sqrt(var_sr)
    return float(stats.norm.cdf(z))


def deflated_sharpe_ratio(
    returns: pd.Series | np.ndarray,
    n_trials: int,
    periods_per_year: int = 252,
    threshold: float = 0.95,
) -> ValidationResult:
    """
    Compute the Deflated Sharpe Ratio.

    Parameters
    ----------
    returns : daily OOS return series (portfolio level).
    n_trials : number of parameter combinations tried during fitting.
    periods_per_year : 252 for daily.
    threshold : DSR must exceed this to permit live/paper trading.
    """
    r = np.asarray(returns)
    r = r[~np.isnan(r)]
    n = len(r)

    sr_ann = annualized_sharpe(r, periods_per_year)
    skew = float(pd.Series(r).skew()) if n >= 4 else 0.0
    kurt = float(pd.Series(r).kurtosis()) if n >= 4 else 0.0

    sr_star_daily = _expected_max_sharpe(n_trials, n)
    sr_star_ann = sr_star_daily * math.sqrt(periods_per_year)

    psr = probabilistic_sharpe_ratio(r, sr_benchmark=sr_star_ann, periods_per_year=periods_per_year)

    passes = psr >= threshold
    message = (
        f"DSR={psr:.4f} {'≥' if passes else '<'} {threshold}. "
        + ("Strategy validated for paper trading." if passes
           else "Strategy NOT validated — do not trade until DSR clears threshold.")
    )

    logger.info(message)

    return ValidationResult(
        sharpe_annualized=sr_ann,
        probabilistic_sharpe=probabilistic_sharpe_ratio(r, 0.0, periods_per_year),
        deflated_sharpe=psr,
        expected_max_sharpe=sr_star_ann,
        n_trials=n_trials,
        n_obs=n,
        skewness=skew,
        kurtosis=kurt,
        passes=passes,
        threshold=threshold,
        message=message,
    )
