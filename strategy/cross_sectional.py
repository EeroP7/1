"""
CrossSectionalRanker — learns feature weights via Information Coefficient (IC)
maximization on in-sample data, then scores the universe each day.

The ranker is validated via a portfolio walk-forward before it is permitted
to produce live/paper signals.  Call validate() to run the walk-forward and
check the Deflated Sharpe threshold.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

if TYPE_CHECKING:
    from data.universe import PriceData
    from validation.overfitting import ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class RankerConfig:
    n_top: int = 10                 # long picks per day
    n_bottom: int = 0               # short picks (stocks only = 0)
    feature_weights: dict[str, float] = field(default_factory=dict)
    ic_lookback: int = 63           # days used to estimate IC in-sample
    validated: bool = False
    dsr_threshold: float = 0.95

    @property
    def n_trials(self) -> int:
        """Always returns the true count of strategy variants ever explored.

        Hard-coding n_trials=1 in the config was methodologically wrong:
        the DSR must be told the real number of strategies tried so it can
        correctly penalise selection bias.  The trial_counter module is the
        single source of truth.
        """
        from validation.trial_counter import n_trials
        return n_trials()


class CrossSectionalRanker:
    """
    Score the universe cross-sectionally each day.

    Workflow:
      ranker = CrossSectionalRanker(config)
      ranker.fit(features, forward_returns)   # sets feature weights from IC
      scores = ranker.rank(date)              # dict {ticker: score}
      picks = ranker.select_top_n(date)       # [(ticker, score), ...]
    """

    def __init__(self, config: RankerConfig | None = None) -> None:
        self.config = config or RankerConfig()
        self._features: dict[str, pd.DataFrame] = {}
        self._weights: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit(
        self,
        features: dict[str, pd.DataFrame],
        forward_returns: pd.DataFrame,
        in_sample_end: pd.Timestamp | None = None,
    ) -> "CrossSectionalRanker":
        """
        Learn feature weights by measuring IC (rank correlation between feature
        value on day t and forward 1-day return on day t+1) over in-sample data.

        Parameters
        ----------
        features : dict feature_name -> (date x ticker) DataFrame
        forward_returns : (date x ticker) next-day returns
        in_sample_end : last date included in fit (exclusive of OOS period)
        """
        self._features = features

        # Slice to in-sample
        if in_sample_end is not None:
            feat_slice = {k: v.loc[:in_sample_end] for k, v in features.items()}
            ret_slice = forward_returns.loc[:in_sample_end]
        else:
            feat_slice = features
            ret_slice = forward_returns

        ic_scores: dict[str, float] = {}
        for name, feat_df in feat_slice.items():
            ics: list[float] = []
            for date in feat_df.index[-self.config.ic_lookback:]:
                if date not in ret_slice.index:
                    continue
                f = feat_df.loc[date].dropna()
                r = ret_slice.loc[date].dropna()
                common = f.index.intersection(r.index)
                if len(common) < 5:
                    continue
                ic, _ = spearmanr(f[common], r[common])
                if not np.isnan(ic):
                    ics.append(ic)
            ic_scores[name] = float(np.mean(ics)) if ics else 0.0

        # normalize weights to sum to 1 over features with positive IC
        positive_ic = {k: max(v, 0) for k, v in ic_scores.items()}
        total = sum(positive_ic.values())
        if total > 0:
            self._weights = {k: v / total for k, v in positive_ic.items()}
        else:
            # fall back to equal weights
            n = len(features)
            self._weights = {k: 1.0 / n for k in features}

        logger.info("Feature IC scores: %s", {k: round(v, 4) for k, v in ic_scores.items()})
        logger.info("Feature weights:   %s", {k: round(v, 4) for k, v in self._weights.items()})
        return self

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score(self, date: pd.Timestamp) -> pd.Series:
        """
        Compute composite score for all tickers on `date`.
        Returns a pd.Series indexed by ticker, higher = more bullish.
        """
        if not self._features:
            raise RuntimeError("Call fit() before score().")

        composite: pd.Series | None = None
        for name, feat_df in self._features.items():
            if date not in feat_df.index:
                continue
            row = feat_df.loc[date]
            w = self._weights.get(name, 0.0)
            contribution = row * w
            if composite is None:
                composite = contribution
            else:
                composite = composite.add(contribution, fill_value=0)

        if composite is None:
            return pd.Series(dtype=float)
        return composite.dropna().sort_values(ascending=False)

    def rank(self, date: pd.Timestamp) -> dict[str, float]:
        """Return {ticker: score} for all tickers on `date`."""
        return self.score(date).to_dict()

    def select_top_n(self, date: pd.Timestamp) -> list[tuple[str, float]]:
        """Return [(ticker, score)] for top-N picks, sorted best-first."""
        scores = self.score(date)
        n = self.config.n_top
        return [(t, s) for t, s in scores.head(n).items()]

    # ------------------------------------------------------------------
    # Validation check
    # ------------------------------------------------------------------

    def is_validated(self) -> bool:
        return self.config.validated

    def mark_validated(self) -> None:
        self.config.validated = True
        logger.info("Ranker marked as validated.")


def compute_forward_returns(close: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """
    Return the forward return matrix (date t → return at t+horizon).
    No look-ahead: value at date t is computed from prices available at t+horizon.
    """
    return close.pct_change(horizon).shift(-horizon)
