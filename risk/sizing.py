"""
Position sizing and risk controls for the basket.

Rules applied in order:
  1. Inverse-vol weighting (or equal weight if mode='equal').
  2. Max weight per name (default 15%).
  3. Max sector weight (default 30%).
  4. Normalize to sum = 1 (or total_exposure if < 1 for cash buffer).
  5. ATR-based stop level per pick.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from data.universe import PriceData
    from data.universe import get_sector

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    max_weight: float = 0.15           # max fraction of portfolio per name
    sector_cap: float = 0.30           # max fraction per GICS sector
    total_exposure: float = 1.0        # fraction of NAV to deploy (< 1 = cash buffer)
    atr_stop_multiplier: float = 2.0   # stop = entry - N * ATR
    atr_window: int = 14
    weight_mode: str = "inv_vol"       # "inv_vol", "risk_parity", or "equal"
    vol_window: int = 21               # days for vol estimation
    vol_target: float = 0.0            # annualized; 0 = disabled. When set,
                                       # total exposure is scaled down so the
                                       # basket's trailing vol ≈ this target.
    vol_target_lookback: int = 21


@dataclass
class SizedPick:
    ticker: str
    rank: int
    score: float
    entry_ref: float        # reference entry price (prior close or open estimate)
    stop: float             # ATR-based stop level
    atr: float
    weight: float           # suggested portfolio weight (0-1)
    sector: str


def _inv_vol_weights(
    tickers: list[str],
    close: pd.DataFrame,
    vol_window: int,
) -> dict[str, float]:
    """1/vol weights, using rolling std of recent returns."""
    recent = close[tickers].pct_change().tail(vol_window + 1)
    vols = recent.std()
    inv_vol = 1.0 / vols.replace(0, np.nan)
    inv_vol = inv_vol.dropna()
    total = inv_vol.sum()
    if total == 0:
        n = len(tickers)
        return {t: 1.0 / n for t in tickers}
    return (inv_vol / total).to_dict()


def _risk_parity_weights(
    tickers: list[str],
    close: pd.DataFrame,
    lookback: int = 63,
) -> dict[str, float]:
    """Correlation-aware weights: w_i ∝ 1 / (σ_i · Σ_j ρ_ij).

    A name that is both volatile and highly correlated with the rest of the
    basket gets less capital, so one hot sector can't dominate portfolio risk.
    """
    rets = close[tickers].pct_change().tail(lookback).dropna(how="all")
    if len(rets) < 10:
        return _inv_vol_weights(tickers, close, 21)
    vols = rets.std()
    corr = rets.corr().clip(lower=0)
    corr_sum = corr.sum()
    raw = (1.0 / (vols * corr_sum).replace(0, np.nan)).dropna()
    total = raw.sum()
    if total == 0 or not np.isfinite(total):
        return _inv_vol_weights(tickers, close, 21)
    return (raw / total).to_dict()


def vol_target_scale(
    weights: dict[str, float],
    close: pd.DataFrame,
    target: float,
    lookback: int = 21,
) -> float:
    """Exposure multiplier in (0, 1] so basket trailing vol ≈ target (ann.).

    Long-only, no leverage: never scales above 1.  Uses trailing realized vol
    of the weighted basket — data through yesterday only, no look-ahead.
    """
    if target <= 0:
        return 1.0
    tickers = [t for t in weights if t in close.columns]
    if not tickers:
        return 1.0
    rets = close[tickers].pct_change().tail(lookback + 1).dropna(how="all")
    if len(rets) < 5:
        return 1.0
    w = pd.Series({t: weights[t] for t in tickers})
    basket = (rets[tickers] * w).sum(axis=1)
    realized = float(basket.std() * np.sqrt(252))
    if not np.isfinite(realized) or realized <= 0:
        return 1.0
    return float(min(1.0, target / realized))


def apply_sector_cap(
    weights: dict[str, float],
    sector_cap: float,
    get_sector_fn,
) -> dict[str, float]:
    """Scale down sectors exceeding the cap, redistribute proportionally.

    Tickers with sector "Unknown" (not in the sector map) are exempt from the
    cap — they aren't a real sector, so lumping them into one capped bucket
    would wrongly squeeze broad-universe portfolios.
    """
    sector_total: dict[str, float] = {}
    for ticker, w in weights.items():
        s = get_sector_fn(ticker)
        sector_total[s] = sector_total.get(s, 0) + w

    scale: dict[str, float] = {
        s: 1.0 if s == "Unknown" or total <= 0 else min(1.0, sector_cap / total)
        for s, total in sector_total.items()
    }

    scaled = {t: w * scale[get_sector_fn(t)] for t, w in weights.items()}
    total = sum(scaled.values())
    return {t: w / total for t, w in scaled.items()} if total > 0 else scaled


def size_picks(
    ranked_tickers: list[tuple[str, float]],  # (ticker, score) sorted best first
    prices: "PriceData",
    atr_df: pd.DataFrame,
    config: RiskConfig | None = None,
) -> list[SizedPick]:
    """
    Take a ranked list and return SizedPick objects with weights and stops.
    """
    from data.universe import get_sector

    if config is None:
        config = RiskConfig()

    tickers = [t for t, _ in ranked_tickers]
    scores = {t: s for t, s in ranked_tickers}

    close = prices.close
    last_close = close.iloc[-1]
    last_atr = atr_df.iloc[-1]

    # --- initial weights ---
    if config.weight_mode == "inv_vol":
        weights = _inv_vol_weights(tickers, close, config.vol_window)
    elif config.weight_mode == "risk_parity":
        weights = _risk_parity_weights(tickers, close)
    else:
        n = len(tickers)
        weights = {t: 1.0 / n for t in tickers}

    # --- apply max-weight cap iteratively until stable ---
    for _ in range(20):
        capped = {t: min(w, config.max_weight) for t, w in weights.items()}
        total = sum(capped.values())
        if total <= 0:
            break
        weights = {t: w / total for t, w in capped.items()}
        if all(w <= config.max_weight + 1e-9 for w in weights.values()):
            break

    # --- sector cap ---
    weights = apply_sector_cap(weights, config.sector_cap, get_sector)

    # --- re-apply max weight after sector renormalization ---
    for _ in range(20):
        capped = {t: min(w, config.max_weight) for t, w in weights.items()}
        total = sum(capped.values())
        if total <= 0:
            break
        weights = {t: w / total for t, w in capped.items()}
        if all(w <= config.max_weight + 1e-9 for w in weights.values()):
            break

    # --- vol targeting: shrink exposure when the basket is running hot ---
    exposure = config.total_exposure
    if config.vol_target > 0:
        scale = vol_target_scale(weights, close, config.vol_target,
                                 config.vol_target_lookback)
        exposure *= scale
        if scale < 1.0:
            logger.info("Vol target %.0f%%: scaling exposure to %.0f%%",
                        config.vol_target * 100, exposure * 100)

    # --- scale to total exposure ---
    weights = {t: w * exposure for t, w in weights.items()}

    # --- build SizedPick objects ---
    picks: list[SizedPick] = []
    for rank, (ticker, score) in enumerate(ranked_tickers, start=1):
        entry = float(last_close.get(ticker, np.nan))
        atr_val = float(last_atr.get(ticker, np.nan))
        stop = entry - config.atr_stop_multiplier * atr_val if np.isfinite(atr_val) else np.nan
        sector = get_sector(ticker)

        picks.append(SizedPick(
            ticker=ticker,
            rank=rank,
            score=round(score, 4),
            entry_ref=round(entry, 2),
            stop=round(stop, 2) if np.isfinite(stop) else float("nan"),
            atr=round(atr_val, 2) if np.isfinite(atr_val) else float("nan"),
            weight=round(weights.get(ticker, 0), 4),
            sector=sector,
        ))

    return picks
