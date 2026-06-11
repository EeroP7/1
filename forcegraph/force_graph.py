"""
Mirofish force-graph signal engine.

Implements a physics-based force-directed graph simulation:
  - 100 signal nodes, each with a 2D position in the layout space
  - 180 directed edges modelled as springs (Hooke's law attraction)
  - All node pairs repel (Coulomb-like force)
  - Nodes are activated and weighted by the current market snapshot
  - The physics simulation runs N_ITER steps with a cooling schedule
  - BULL and BEAR clusters emerge organically from the layout
  - Convergence fires when clusters are spatially well-separated and
    one cluster dominates by weight

No networkx required — pure numpy.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

from config import CONVERGENCE_THRESHOLD, MIN_SIGNAL_NODES
from feeds.binance_ws import BtcSnapshot
from feeds.indicators import IndicatorSet


class Bias(str, Enum):
    BULL    = "BULL"
    BEAR    = "BEAR"
    NEUTRAL = "NEUTRAL"


@dataclass
class GraphSignal:
    bias: Bias
    confidence: float         # cluster weight ratio (0-1)
    bull_weight: float
    bear_weight: float
    active_nodes: int
    converged: bool
    separation: float         # inter-cluster distance / avg intra-cluster spread
    mark_price_lag: float     # |mark_price - clob_implied| / mark_price


# ── Node catalogue (100 nodes) ────────────────────────────────────────────────

_NODE_DEFS: list[tuple[str, Bias]] = [
    # RSI
    ("rsi_oversold",      Bias.BULL), ("rsi_overbought",    Bias.BEAR),
    ("rsi_bull_zone",     Bias.BULL), ("rsi_bear_zone",     Bias.BEAR),
    ("rsi_divergence_up", Bias.BULL), ("rsi_divergence_dn", Bias.BEAR),

    # StochRSI
    ("stoch_cross_up",    Bias.BULL), ("stoch_cross_dn",    Bias.BEAR),
    ("stoch_os",          Bias.BULL), ("stoch_ob",          Bias.BEAR),

    # EMA
    ("ema9_above_21",     Bias.BULL), ("ema9_below_21",     Bias.BEAR),
    ("ema21_above_50",    Bias.BULL), ("ema21_below_50",    Bias.BEAR),
    ("price_above_ema9",  Bias.BULL), ("price_below_ema9",  Bias.BEAR),
    ("price_above_ema50", Bias.BULL), ("price_below_ema50", Bias.BEAR),

    # MACD
    ("macd_hist_pos",     Bias.BULL), ("macd_hist_neg",     Bias.BEAR),
    ("macd_cross_up",     Bias.BULL), ("macd_cross_dn",     Bias.BEAR),

    # Bollinger
    ("bb_lower_touch",    Bias.BULL), ("bb_upper_touch",    Bias.BEAR),
    ("bb_above_mid",      Bias.BULL), ("bb_below_mid",      Bias.BEAR),
    ("bb_squeeze",        Bias.NEUTRAL), ("bb_expansion",   Bias.NEUTRAL),

    # OBV / volume
    ("obv_accumulate",    Bias.BULL), ("obv_distribute",    Bias.BEAR),
    ("buy_pressure_hi",   Bias.BULL), ("buy_pressure_lo",   Bias.BEAR),
    ("vol_surge_bull",    Bias.BULL), ("vol_surge_bear",    Bias.BEAR),
    ("vol_dry_up",        Bias.NEUTRAL),

    # VWAP
    ("price_above_vwap",  Bias.BULL), ("price_below_vwap",  Bias.BEAR),

    # Order flow imbalance
    ("ofi_positive",      Bias.BULL), ("ofi_negative",      Bias.BEAR),
    ("ofi_neutral",       Bias.NEUTRAL),

    # Exchange flow proxy (aggTrade-derived)
    ("exchange_inflow",   Bias.BEAR), ("exchange_outflow",  Bias.BULL),
    ("flow_neutral",      Bias.NEUTRAL),

    # aggTrade momentum (Binance aggTrade stream)
    ("agg_buy_surge",     Bias.BULL), ("agg_sell_surge",    Bias.BEAR),
    ("agg_flow_balanced", Bias.NEUTRAL),

    # Futures mark price nodes (Binance perpetual futures)
    ("mark_above_spot",   Bias.BULL), ("mark_below_spot",   Bias.BEAR),
    ("mark_premium_hi",   Bias.BULL), ("mark_discount_hi",  Bias.BEAR),
    ("funding_positive",  Bias.BEAR), ("funding_negative",  Bias.BULL),
    ("funding_neutral",   Bias.NEUTRAL),

    # Depth / liquidity
    ("spread_tight",      Bias.NEUTRAL), ("spread_wide",    Bias.BEAR),
    ("deep_bid",          Bias.BULL),    ("deep_ask",       Bias.BEAR),
    ("depth_bid_wall",    Bias.BULL),    ("depth_ask_wall", Bias.BEAR),

    # Momentum
    ("momentum_accel_up", Bias.BULL), ("momentum_accel_dn", Bias.BEAR),
    ("momentum_flat",     Bias.NEUTRAL),

    # Candle patterns
    ("candle_bull_body",  Bias.BULL), ("candle_bear_body",  Bias.BEAR),
    ("upper_wick",        Bias.BEAR), ("lower_wick",        Bias.BULL),
    ("doji",              Bias.NEUTRAL),

    # Time-window
    ("early_window",      Bias.NEUTRAL), ("late_window",    Bias.NEUTRAL),
    ("window_close",      Bias.NEUTRAL),

    # Polymarket CLOB lag nodes (key arbitrage signal)
    ("poly_lag_bull",     Bias.BULL), ("poly_lag_bear",     Bias.BEAR),
    ("poly_aligned",      Bias.NEUTRAL),
    ("clob_mark_lag_bull",Bias.BULL), ("clob_mark_lag_bear",Bias.BEAR),

    # Composite
    ("trend_aligned_bull",Bias.BULL), ("trend_aligned_bear",Bias.BEAR),
    ("conflicting_signals",Bias.NEUTRAL),
    ("breakout_up",       Bias.BULL), ("breakout_dn",       Bias.BEAR),
    ("range_bound",       Bias.NEUTRAL),
    ("volatility_low",    Bias.NEUTRAL), ("volatility_high", Bias.NEUTRAL),
    ("reversal_potential",Bias.NEUTRAL),

    # Sentiment proxy
    ("sentiment_fear",    Bias.BEAR), ("sentiment_greed",   Bias.BULL),
    ("sentiment_neutral", Bias.NEUTRAL),

    # Price level
    ("near_resistance",   Bias.BEAR), ("near_support",      Bias.BULL),
    ("in_range",          Bias.NEUTRAL),

    # Multi-timeframe
    ("mtf_bull",          Bias.BULL), ("mtf_bear",          Bias.BEAR),
    ("mtf_mixed",         Bias.NEUTRAL),

    # R/R
    ("rr_favorable_bull", Bias.BULL), ("rr_favorable_bear", Bias.BEAR),
    ("rr_unfavorable",    Bias.NEUTRAL),

    # Extra signal nodes
    ("mark_momentum_up",  Bias.BULL), ("mark_momentum_dn",  Bias.BEAR),
    ("depth_imbalance",   Bias.NEUTRAL), ("window_mid",     Bias.NEUTRAL),
]

assert len(_NODE_DEFS) == 100, f"Expected 100 nodes, got {len(_NODE_DEFS)}"


# ── Edge catalogue (180 edges) ────────────────────────────────────────────────
# (source, target, spring_strength)  — higher weight = stronger spring pull

_EDGE_DEFS: list[tuple[str, str, float]] = [
    # RSI → momentum / trend
    ("rsi_oversold",       "momentum_accel_up",  0.90),
    ("rsi_overbought",     "momentum_accel_dn",  0.90),
    ("rsi_bull_zone",      "trend_aligned_bull", 0.70),
    ("rsi_bear_zone",      "trend_aligned_bear", 0.70),
    ("rsi_divergence_up",  "reversal_potential", 0.80),
    ("rsi_divergence_dn",  "reversal_potential", 0.80),

    # StochRSI
    ("stoch_cross_up",     "momentum_accel_up",  0.80),
    ("stoch_cross_dn",     "momentum_accel_dn",  0.80),
    ("stoch_os",           "reversal_potential", 0.60),
    ("stoch_ob",           "reversal_potential", 0.60),
    ("stoch_cross_up",     "rr_favorable_bull",  0.50),
    ("stoch_cross_dn",     "rr_favorable_bear",  0.50),

    # EMA
    ("ema9_above_21",      "trend_aligned_bull", 0.85),
    ("ema9_below_21",      "trend_aligned_bear", 0.85),
    ("ema21_above_50",     "mtf_bull",           0.75),
    ("ema21_below_50",     "mtf_bear",           0.75),
    ("price_above_ema9",   "breakout_up",        0.60),
    ("price_below_ema9",   "breakout_dn",        0.60),
    ("price_above_ema50",  "mtf_bull",           0.70),
    ("price_below_ema50",  "mtf_bear",           0.70),

    # MACD
    ("macd_hist_pos",      "momentum_accel_up",  0.80),
    ("macd_hist_neg",      "momentum_accel_dn",  0.80),
    ("macd_cross_up",      "trend_aligned_bull", 0.90),
    ("macd_cross_dn",      "trend_aligned_bear", 0.90),
    ("macd_hist_pos",      "rr_favorable_bull",  0.60),
    ("macd_hist_neg",      "rr_favorable_bear",  0.60),

    # Bollinger
    ("bb_lower_touch",     "reversal_potential", 0.70),
    ("bb_upper_touch",     "reversal_potential", 0.70),
    ("bb_above_mid",       "sentiment_greed",    0.50),
    ("bb_below_mid",       "sentiment_fear",     0.50),
    ("bb_squeeze",         "volatility_low",     0.90),
    ("bb_expansion",       "volatility_high",    0.90),

    # OBV / volume
    ("obv_accumulate",     "sentiment_greed",    0.70),
    ("obv_distribute",     "sentiment_fear",     0.70),
    ("buy_pressure_hi",    "breakout_up",        0.75),
    ("buy_pressure_lo",    "breakout_dn",        0.75),
    ("vol_surge_bull",     "momentum_accel_up",  0.85),
    ("vol_surge_bear",     "momentum_accel_dn",  0.85),
    ("vol_dry_up",         "range_bound",        0.60),

    # VWAP
    ("price_above_vwap",   "trend_aligned_bull", 0.65),
    ("price_below_vwap",   "trend_aligned_bear", 0.65),
    ("price_above_vwap",   "sentiment_greed",    0.40),
    ("price_below_vwap",   "sentiment_fear",     0.40),

    # OFI
    ("ofi_positive",       "deep_bid",           0.80),
    ("ofi_negative",       "deep_ask",           0.80),
    ("ofi_positive",       "buy_pressure_hi",    0.70),
    ("ofi_negative",       "buy_pressure_lo",    0.70),

    # Exchange flow
    ("exchange_inflow",    "sentiment_fear",     0.60),
    ("exchange_outflow",   "sentiment_greed",    0.60),
    ("exchange_inflow",    "breakout_dn",        0.50),
    ("exchange_outflow",   "breakout_up",        0.50),

    # aggTrade momentum (new: Binance aggTrade stream)
    ("agg_buy_surge",      "momentum_accel_up",  0.88),
    ("agg_sell_surge",     "momentum_accel_dn",  0.88),
    ("agg_buy_surge",      "buy_pressure_hi",    0.75),
    ("agg_sell_surge",     "buy_pressure_lo",    0.75),
    ("agg_buy_surge",      "sentiment_greed",    0.60),
    ("agg_sell_surge",     "sentiment_fear",     0.60),
    ("agg_flow_balanced",  "range_bound",        0.50),

    # Futures mark price → arbitrage signal (new: futures stream)
    ("mark_above_spot",    "sentiment_greed",    0.65),
    ("mark_below_spot",    "sentiment_fear",     0.65),
    ("mark_premium_hi",    "breakout_up",        0.70),
    ("mark_discount_hi",   "breakout_dn",        0.70),
    ("funding_negative",   "momentum_accel_up",  0.72),
    ("funding_positive",   "momentum_accel_dn",  0.72),
    ("mark_above_spot",    "trend_aligned_bull", 0.60),
    ("mark_below_spot",    "trend_aligned_bear", 0.60),

    # CLOB vs mark price lag (core arbitrage nodes)
    ("clob_mark_lag_bull", "breakout_up",        0.98),
    ("clob_mark_lag_bear", "breakout_dn",        0.98),
    ("clob_mark_lag_bull", "rr_favorable_bull",  0.95),
    ("clob_mark_lag_bear", "rr_favorable_bear",  0.95),
    ("clob_mark_lag_bull", "poly_lag_bull",      0.90),
    ("clob_mark_lag_bear", "poly_lag_bear",      0.90),

    # Polymarket lag nodes
    ("poly_lag_bull",      "breakout_up",        0.95),
    ("poly_lag_bear",      "breakout_dn",        0.95),
    ("poly_lag_bull",      "rr_favorable_bull",  0.90),
    ("poly_lag_bear",      "rr_favorable_bear",  0.90),

    # Depth / liquidity
    ("deep_bid",           "rr_favorable_bull",  0.70),
    ("deep_ask",           "rr_favorable_bear",  0.70),
    ("depth_bid_wall",     "near_support",       0.75),
    ("depth_ask_wall",     "near_resistance",    0.75),
    ("spread_tight",       "momentum_accel_up",  0.30),
    ("spread_wide",        "volatility_high",    0.50),

    # Candle patterns
    ("candle_bull_body",   "momentum_accel_up",  0.65),
    ("candle_bear_body",   "momentum_accel_dn",  0.65),
    ("lower_wick",         "reversal_potential", 0.50),
    ("upper_wick",         "reversal_potential", 0.50),
    ("doji",               "conflicting_signals",0.60),

    # Time window
    ("early_window",       "spread_tight",       0.30),
    ("late_window",        "momentum_accel_up",  0.20),
    ("window_close",       "conflicting_signals",0.40),

    # Composite aggregators
    ("trend_aligned_bull", "mtf_bull",           0.80),
    ("trend_aligned_bear", "mtf_bear",           0.80),
    ("momentum_accel_up",  "breakout_up",        0.85),
    ("momentum_accel_dn",  "breakout_dn",        0.85),
    ("breakout_up",        "rr_favorable_bull",  0.90),
    ("breakout_dn",        "rr_favorable_bear",  0.90),
    ("reversal_potential", "conflicting_signals",0.50),
    ("conflicting_signals","rr_unfavorable",     0.60),
    ("range_bound",        "rr_unfavorable",     0.50),

    # Sentiment → bias
    ("sentiment_greed",    "mtf_bull",           0.60),
    ("sentiment_fear",     "mtf_bear",           0.60),
    ("sentiment_greed",    "near_support",       0.40),
    ("sentiment_fear",     "near_resistance",    0.40),

    # Cross-links for topology density
    ("rsi_bull_zone",      "price_above_vwap",   0.40),
    ("rsi_bear_zone",      "price_below_vwap",   0.40),
    ("ema9_above_21",      "price_above_vwap",   0.45),
    ("ema9_below_21",      "price_below_vwap",   0.45),
    ("macd_hist_pos",      "obv_accumulate",     0.50),
    ("macd_hist_neg",      "obv_distribute",     0.50),
    ("buy_pressure_hi",    "sentiment_greed",    0.50),
    ("buy_pressure_lo",    "sentiment_fear",     0.50),
    ("vol_surge_bull",     "obv_accumulate",     0.60),
    ("vol_surge_bear",     "obv_distribute",     0.60),
    ("deep_bid",           "near_support",       0.50),
    ("deep_ask",           "near_resistance",    0.50),
    ("mtf_bull",           "rr_favorable_bull",  0.70),
    ("mtf_bear",           "rr_favorable_bear",  0.70),
    ("near_support",       "reversal_potential", 0.40),
    ("near_resistance",    "reversal_potential", 0.40),
    ("stoch_os",           "near_support",       0.55),
    ("stoch_ob",           "near_resistance",    0.55),
    ("bb_lower_touch",     "near_support",       0.65),
    ("bb_upper_touch",     "near_resistance",    0.65),
    ("ofi_positive",       "trend_aligned_bull", 0.50),
    ("ofi_negative",       "trend_aligned_bear", 0.50),
    ("volatility_high",    "breakout_up",        0.35),
    ("volatility_high",    "breakout_dn",        0.35),
    ("volatility_low",     "range_bound",        0.55),
    ("rr_favorable_bull",  "trend_aligned_bull", 0.60),
    ("rr_favorable_bear",  "trend_aligned_bear", 0.60),
    ("rr_unfavorable",     "conflicting_signals",0.70),
    ("mtf_bull",           "trend_aligned_bull", 0.65),
    ("mtf_bear",           "trend_aligned_bear", 0.65),
    ("obv_accumulate",     "trend_aligned_bull", 0.45),
    ("obv_distribute",     "trend_aligned_bear", 0.45),
    ("candle_bull_body",   "rr_favorable_bull",  0.40),
    ("candle_bear_body",   "rr_favorable_bear",  0.40),
    ("exchange_inflow",    "vol_surge_bear",     0.40),
    ("funding_positive",   "near_resistance",    0.45),
    ("funding_negative",   "near_support",       0.45),
    ("mark_premium_hi",    "agg_buy_surge",      0.55),
    ("mark_discount_hi",   "agg_sell_surge",     0.55),
    ("agg_buy_surge",      "obv_accumulate",     0.50),
    ("agg_sell_surge",     "obv_distribute",     0.50),
    ("depth_bid_wall",     "momentum_accel_up",  0.50),
    ("depth_ask_wall",     "momentum_accel_dn",  0.50),
    ("clob_mark_lag_bull", "agg_buy_surge",      0.60),
    ("clob_mark_lag_bear", "agg_sell_surge",     0.60),
    ("in_range",           "range_bound",        0.50),
    ("bb_squeeze",         "momentum_flat",      0.50),
    ("momentum_flat",      "range_bound",        0.45),
    ("sentiment_neutral",  "range_bound",        0.35),
    ("flow_neutral",       "ofi_neutral",        0.40),
    ("poly_aligned",       "range_bound",        0.30),

    # New node connections + density edges to reach 180
    ("mark_momentum_up",   "trend_aligned_bull", 0.85),
    ("mark_momentum_dn",   "trend_aligned_bear", 0.85),
    ("mark_momentum_up",   "breakout_up",        0.80),
    ("mark_momentum_dn",   "breakout_dn",        0.80),
    ("mark_momentum_up",   "agg_buy_surge",      0.65),
    ("mark_momentum_dn",   "agg_sell_surge",     0.65),
    ("depth_imbalance",    "ofi_positive",       0.50),
    ("depth_imbalance",    "deep_bid",           0.45),
    ("window_mid",         "range_bound",        0.35),
    ("window_mid",         "momentum_flat",      0.35),
    ("clob_mark_lag_bull", "mark_momentum_up",   0.75),
    ("clob_mark_lag_bear", "mark_momentum_dn",   0.75),
    ("mark_above_spot",    "mark_momentum_up",   0.70),
    ("mark_below_spot",    "mark_momentum_dn",   0.70),
    ("funding_negative",   "mark_momentum_up",   0.55),
    ("funding_positive",   "mark_momentum_dn",   0.55),
    ("agg_buy_surge",      "mark_momentum_up",   0.50),
    ("agg_sell_surge",     "mark_momentum_dn",   0.50),
    ("mark_momentum_up",   "sentiment_greed",    0.55),
    ("mark_momentum_dn",   "sentiment_fear",     0.55),
    ("depth_bid_wall",     "depth_imbalance",    0.45),
    ("deep_bid",           "depth_imbalance",    0.40),
    ("depth_imbalance",    "spread_tight",       0.30),
    ("mark_momentum_up",   "mtf_bull",           0.50),
    ("mark_momentum_dn",   "mtf_bear",           0.50),
    ("depth_imbalance",    "volatility_low",     0.30),
]

assert len(_EDGE_DEFS) == 180, f"Expected 180 edges, got {len(_EDGE_DEFS)}"


# ── Physics constants ─────────────────────────────────────────────────────────

K_REPULSION  = 800.0    # Coulomb repulsion strength
K_SPRING     = 0.12     # edge spring (Hooke) strength
K_GRAVITY    = 0.04     # gravity toward origin (prevents drift)
REST_LENGTH  = 10.0     # natural spring length (pixels)
VELOCITY_DECAY = 0.85   # velocity damping per step
N_ITER       = 60       # simulation steps per evaluation
ALPHA_INIT   = 1.0      # initial cooling factor
ALPHA_DECAY  = 0.025    # cooling decrement per iteration


class ForceGraph:
    """
    Mirofish-style force-directed graph.

    Maintains persistent node positions between calls so the simulation
    runs from the previous equilibrium rather than from scratch — this
    makes it fast enough for 100ms ticks.
    """

    def __init__(self) -> None:
        self._n = len(_NODE_DEFS)
        self._labels = [label for label, _ in _NODE_DEFS]
        self._biases = [bias  for _, bias  in _NODE_DEFS]
        self._label_idx = {l: i for i, l in enumerate(self._labels)}

        # Pre-compute edge arrays for vectorised spring step
        self._src_idx = np.array([self._label_idx[s] for s, _, _ in _EDGE_DEFS], dtype=np.int32)
        self._dst_idx = np.array([self._label_idx[d] for _, d, _ in _EDGE_DEFS], dtype=np.int32)
        self._edge_w  = np.array([w               for _, _, w in _EDGE_DEFS], dtype=np.float64)

        # Initial positions: evenly spaced on a circle (stable starting layout)
        angles = np.linspace(0, 2 * np.pi, self._n, endpoint=False)
        r = 25.0
        self._pos = np.column_stack([r * np.cos(angles), r * np.sin(angles)])
        self._vel = np.zeros((self._n, 2))

        # Bias sign: BULL → +1, BEAR → -1, NEUTRAL → 0
        self._bias_sign = np.array([
            1.0 if b == Bias.BULL else -1.0 if b == Bias.BEAR else 0.0
            for b in self._biases
        ])

    # ── public ────────────────────────────────────────────────────────────────

    def evaluate(
        self,
        snap: BtcSnapshot,
        ind: IndicatorSet,
        poly_yes_price: float,
        poly_no_price: float,
        seconds_to_window_close: float,
    ) -> GraphSignal:
        weights = self._compute_weights(snap, ind, poly_yes_price,
                                        poly_no_price, seconds_to_window_close)
        active_nodes = int(np.sum(weights > 0))
        self._simulate(weights)
        return self._classify(weights, active_nodes, snap, poly_yes_price)

    # ── weight assignment ─────────────────────────────────────────────────────

    def _compute_weights(
        self,
        snap: BtcSnapshot,
        ind: IndicatorSet,
        py: float,
        pn: float,
        ttc: float,
    ) -> np.ndarray:
        w = np.zeros(self._n)
        p = snap.effective_price   # uses mark_price when available
        mark = snap.mark_price
        spot = snap.price

        def set_w(label: str, val: float) -> None:
            idx = self._label_idx.get(label)
            if idx is not None:
                w[idx] = max(w[idx], min(abs(val), 1.0))

        # RSI
        if ind.rsi_14 < 30:
            set_w("rsi_oversold",      (30 - ind.rsi_14) / 30)
        if ind.rsi_14 > 70:
            set_w("rsi_overbought",    (ind.rsi_14 - 70) / 30)
        if 50 < ind.rsi_14 <= 70:
            set_w("rsi_bull_zone",     (ind.rsi_14 - 50) / 20)
        if 30 <= ind.rsi_14 < 50:
            set_w("rsi_bear_zone",     (50 - ind.rsi_14) / 20)

        # StochRSI
        k_d_diff = ind.stoch_rsi_k - ind.stoch_rsi_d
        if k_d_diff > 0 and ind.stoch_rsi_k < 80:
            set_w("stoch_cross_up",    min(1.0, k_d_diff / 20))
        if k_d_diff < 0 and ind.stoch_rsi_k > 20:
            set_w("stoch_cross_dn",    min(1.0, -k_d_diff / 20))
        if ind.stoch_rsi_k < 20:
            set_w("stoch_os",          (20 - ind.stoch_rsi_k) / 20)
        if ind.stoch_rsi_k > 80:
            set_w("stoch_ob",          (ind.stoch_rsi_k - 80) / 20)

        # EMAs
        for above, below, ref_a, ref_b in [
            ("ema9_above_21",  "ema9_below_21",  ind.ema_9,  ind.ema_21),
            ("ema21_above_50", "ema21_below_50", ind.ema_21, ind.ema_50),
            ("price_above_ema9",  "price_below_ema9",  p, ind.ema_9),
            ("price_above_ema50", "price_below_ema50", p, ind.ema_50),
        ]:
            diff = abs(ref_a - ref_b) / (ref_b if ref_b else 1)
            set_w(above if ref_a > ref_b else below, diff)

        # MACD
        set_w("macd_hist_pos" if ind.macd_hist > 0 else "macd_hist_neg",
               min(1.0, abs(ind.macd_hist) / (p * 1e-4 + 1e-9)))
        set_w("macd_cross_up" if ind.macd_line > ind.macd_signal else "macd_cross_dn", 0.6)

        # Bollinger
        bb_range = ind.bb_upper - ind.bb_lower
        if p < ind.bb_lower * 1.002:
            set_w("bb_lower_touch", min(1.0, (ind.bb_lower - p) / (bb_range + 1e-9) + 0.3))
        if p > ind.bb_upper * 0.998:
            set_w("bb_upper_touch", min(1.0, (p - ind.bb_upper) / (bb_range + 1e-9) + 0.3))
        set_w("bb_above_mid" if p > ind.bb_mid else "bb_below_mid",
               abs(p - ind.bb_mid) / (bb_range / 2 + 1e-9))
        if ind.bb_width < 0.015:
            set_w("bb_squeeze", min(1.0, 0.015 / (ind.bb_width + 1e-9) - 1))
        if ind.bb_width > 0.04:
            set_w("bb_expansion", min(1.0, ind.bb_width / 0.04 - 1))

        # OBV
        if abs(ind.obv) > 0.05:
            set_w("obv_accumulate" if ind.obv > 0 else "obv_distribute", min(1.0, abs(ind.obv) * 2))

        # Buy pressure
        bsr = ind.buy_sell_ratio
        if bsr > 0.55:
            set_w("buy_pressure_hi", (bsr - 0.5) * 2)
        elif bsr < 0.45:
            set_w("buy_pressure_lo", (0.5 - bsr) * 2)

        # Volume surge
        if snap.klines:
            avg_vol = sum(k.volume for k in snap.klines[:10]) / min(10, len(snap.klines))
            last_k = snap.klines[0]
            ratio = last_k.volume / (avg_vol + 1e-9)
            if ratio > 1.5:
                lbl = "vol_surge_bull" if last_k.taker_buy_volume > last_k.taker_sell_volume else "vol_surge_bear"
                set_w(lbl, min(1.0, ratio - 1))
            elif ratio < 0.5:
                set_w("vol_dry_up", 0.7)

        # VWAP
        set_w("price_above_vwap" if p > ind.vwap else "price_below_vwap",
               abs(p - ind.vwap) / (ind.vwap + 1e-9))

        # OFI
        ofi = snap.order_flow_imbalance
        if abs(ofi) > 0.1:
            set_w("ofi_positive" if ofi > 0 else "ofi_negative", abs(ofi))
        else:
            set_w("ofi_neutral", 0.5)

        # aggTrade flow (NEW: Binance aggTrade stream)
        fr = snap.flow_ratio
        if fr > 0.62:
            set_w("agg_buy_surge",    (fr - 0.5) * 2)
        elif fr < 0.38:
            set_w("agg_sell_surge",   (0.5 - fr) * 2)
        else:
            set_w("agg_flow_balanced", 0.5)
        # map to old exchange flow for graph connectivity
        if bsr < 0.4:
            set_w("exchange_inflow",  (0.4 - bsr) * 2)
        elif bsr > 0.6:
            set_w("exchange_outflow", (bsr - 0.6) * 2)
        else:
            set_w("flow_neutral", 0.5)

        # Futures mark price (NEW: futures stream)
        if mark > 0 and spot > 0:
            premium = (mark - spot) / spot
            if premium > 0.0005:
                set_w("mark_above_spot",  min(1.0, premium * 500))
            elif premium < -0.0005:
                set_w("mark_below_spot",  min(1.0, -premium * 500))
            if abs(premium) > 0.002:
                set_w("mark_premium_hi" if premium > 0 else "mark_discount_hi",
                       min(1.0, abs(premium) * 250))
            fr_val = snap.funding_rate
            if abs(fr_val) > 0.0001:
                set_w("funding_positive" if fr_val > 0 else "funding_negative",
                       min(1.0, abs(fr_val) * 5000))
            else:
                set_w("funding_neutral", 0.5)

        # Depth order-book walls (NEW: depth stream)
        if snap.bids and snap.asks:
            bid_wall = max(b.qty for b in snap.bids)
            ask_wall = max(a.qty for a in snap.asks)
            if bid_wall > ask_wall * 2:
                set_w("depth_bid_wall", min(1.0, bid_wall / (ask_wall + 1e-9) - 1) * 0.5)
            elif ask_wall > bid_wall * 2:
                set_w("depth_ask_wall", min(1.0, ask_wall / (bid_wall + 1e-9) - 1) * 0.5)
            if snap.bid_qty > snap.ask_qty * 1.3:
                set_w("deep_bid", min(1.0, snap.bid_qty / (snap.ask_qty + 1e-9) - 1))
            elif snap.ask_qty > snap.bid_qty * 1.3:
                set_w("deep_ask", min(1.0, snap.ask_qty / (snap.bid_qty + 1e-9) - 1))

        # Spread
        spread_pct = (snap.ask - snap.bid) / (p + 1e-9)
        if spread_pct < 0.0005:
            set_w("spread_tight", 0.8)
        elif spread_pct > 0.002:
            set_w("spread_wide",  0.8)

        # Candle patterns
        if len(snap.klines) > 1:
            ck = snap.klines[1]
            body = ck.close - ck.open
            total = ck.high - ck.low + 1e-9
            body_r = abs(body) / total
            upper_w = (ck.high - max(ck.open, ck.close)) / total
            lower_w = (min(ck.open, ck.close) - ck.low) / total
            if body_r > 0.5:
                set_w("candle_bull_body" if body > 0 else "candle_bear_body", body_r)
            if upper_w > 0.3:
                set_w("upper_wick", upper_w)
            if lower_w > 0.3:
                set_w("lower_wick", lower_w)
            if body_r < 0.15:
                set_w("doji", 0.7)

        # Time window
        if ttc > 240:
            set_w("early_window", 0.6)
        elif ttc > 60:
            set_w("late_window", 0.6)
        else:
            set_w("window_close", min(1.0, 1 - ttc / 60))

        # Polymarket CLOB lag vs indicator signal
        implied_yes = ind.bull_score
        if implied_yes - py > 0.03:
            set_w("poly_lag_bull", min(1.0, (implied_yes - py) * 10))
        elif py - implied_yes > 0.03:
            set_w("poly_lag_bear", min(1.0, (py - implied_yes) * 10))
        else:
            set_w("poly_aligned", 0.5)

        # CLOB vs mark price lag (the real arbitrage: futures mark vs CLOB)
        if mark > 0:
            # YES fair value from mark price momentum in the current window
            # approximated as: higher mark vs last kline open → higher P(up)
            if snap.klines:
                window_open = snap.klines[-1].open if snap.klines else mark
                mark_move = (mark - window_open) / (window_open + 1e-9)
                # simple logistic: 0.5 + 0.5 * tanh(move / 0.005)
                import math
                fair_yes_mark = 0.5 + 0.5 * math.tanh(mark_move / 0.005)
                lag_mark = fair_yes_mark - py
                if lag_mark > 0.03:
                    set_w("clob_mark_lag_bull", min(1.0, lag_mark * 15))
                elif lag_mark < -0.03:
                    set_w("clob_mark_lag_bear", min(1.0, -lag_mark * 15))

        # Momentum
        if ind.bull_score > 0.65:
            set_w("momentum_accel_up", ind.bull_score)
        elif ind.bear_score > 0.65:
            set_w("momentum_accel_dn", ind.bear_score)
        else:
            set_w("momentum_flat", 0.5)

        # Multi-TF
        bull_ema = ind.ema_9 > ind.ema_21 > ind.ema_50
        bear_ema = ind.ema_9 < ind.ema_21 < ind.ema_50
        if bull_ema:
            set_w("mtf_bull", 0.8)
        elif bear_ema:
            set_w("mtf_bear", 0.8)
        else:
            set_w("mtf_mixed", 0.6)

        if ind.bb_width < 0.01:
            set_w("volatility_low", 0.8)
        elif ind.bb_width > 0.03:
            set_w("volatility_high", 0.8)

        return w

    # ── physics simulation ────────────────────────────────────────────────────

    def _simulate(self, weights: np.ndarray) -> None:
        """
        Run N_ITER steps of force-directed layout from current positions.
        Node mass is inversely proportional to activation weight (lighter
        active nodes move faster to cluster with their peers).
        """
        pos = self._pos
        vel = self._vel
        mass = np.where(weights > 0, 1.0 / (weights + 0.1), 2.0)  # active = lighter
        alpha = ALPHA_INIT

        for _ in range(N_ITER):
            # ── Repulsion (vectorised Coulomb) ────────────────────────────
            diff = pos[:, np.newaxis, :] - pos[np.newaxis, :, :]   # (n,n,2)
            dist_sq = np.sum(diff ** 2, axis=2) + 0.1              # (n,n)
            np.fill_diagonal(dist_sq, 1e9)
            f_mag = K_REPULSION / dist_sq                           # (n,n)
            rep_force = np.sum(f_mag[:, :, np.newaxis] * diff, axis=1)  # (n,2)

            # ── Spring attraction (edges) ─────────────────────────────────
            spr_force = np.zeros_like(pos)
            d_vec  = pos[self._dst_idx] - pos[self._src_idx]        # (E,2)
            d_dist = np.sqrt(np.sum(d_vec ** 2, axis=1)) + 1e-6    # (E,)
            stretch = d_dist - REST_LENGTH                           # (E,)
            f_spr  = (K_SPRING * self._edge_w * stretch)[:, np.newaxis] * (d_vec / d_dist[:, np.newaxis])
            np.add.at(spr_force, self._src_idx,  f_spr)
            np.add.at(spr_force, self._dst_idx, -f_spr)

            # ── Gravity toward origin ─────────────────────────────────────
            grav_force = -K_GRAVITY * pos

            total_force = (rep_force + spr_force + grav_force) / mass[:, np.newaxis]

            vel = vel * VELOCITY_DECAY + total_force * alpha
            pos = pos + vel
            alpha = max(alpha - ALPHA_DECAY, 0.01)

        self._pos = pos
        self._vel = vel

    # ── cluster classification ────────────────────────────────────────────────

    def _classify(
        self,
        weights: np.ndarray,
        active_nodes: int,
        snap: BtcSnapshot,
        poly_yes_price: float,
    ) -> GraphSignal:
        if active_nodes < MIN_SIGNAL_NODES:
            return GraphSignal(
                bias=Bias.NEUTRAL, confidence=0.0,
                bull_weight=0.0, bear_weight=0.0,
                active_nodes=active_nodes, converged=False,
                separation=0.0, mark_price_lag=0.0,
            )

        pos = self._pos
        signs = self._bias_sign

        # Initialise cluster centres from known-biased nodes
        bull_mask = (signs > 0) & (weights > 0)
        bear_mask = (signs < 0) & (weights > 0)
        if not np.any(bull_mask) or not np.any(bear_mask):
            return GraphSignal(
                bias=Bias.NEUTRAL, confidence=0.5,
                bull_weight=0.0, bear_weight=0.0,
                active_nodes=active_nodes, converged=False,
                separation=0.0, mark_price_lag=0.0,
            )

        c_bull = np.mean(pos[bull_mask], axis=0)
        c_bear = np.mean(pos[bear_mask], axis=0)

        # Assign every active node to nearest cluster
        d_bull = np.sqrt(np.sum((pos - c_bull) ** 2, axis=1))
        d_bear = np.sqrt(np.sum((pos - c_bear) ** 2, axis=1))
        in_bull = d_bull <= d_bear

        # Weighted cluster scores (only active nodes count)
        aw = weights * (weights > 0)
        bull_weight = float(np.sum(aw[in_bull]))
        bear_weight = float(np.sum(aw[~in_bull]))
        total = bull_weight + bear_weight or 1e-9

        bull_ratio = bull_weight / total
        bear_ratio = bear_weight / total

        # Cluster separation quality
        inter_dist = float(np.sqrt(np.sum((c_bull - c_bear) ** 2)))
        bull_spread = float(np.mean(d_bull[bull_mask])) if np.any(bull_mask) else 1.0
        bear_spread = float(np.mean(d_bear[bear_mask])) if np.any(bear_mask) else 1.0
        separation = inter_dist / ((bull_spread + bear_spread) / 2 + 1e-6)

        # Determine bias
        if bull_ratio >= CONVERGENCE_THRESHOLD:
            bias, confidence = Bias.BULL, bull_ratio
        elif bear_ratio >= CONVERGENCE_THRESHOLD:
            bias, confidence = Bias.BEAR, bear_ratio
        else:
            bias, confidence = Bias.NEUTRAL, max(bull_ratio, bear_ratio)

        converged = bias != Bias.NEUTRAL and separation > 1.5

        # Mark-price lag for dashboard
        mark = snap.mark_price
        if mark > 0 and snap.klines:
            import math
            window_open = snap.klines[-1].open
            mark_move = (mark - window_open) / (window_open + 1e-9)
            fair_yes = 0.5 + 0.5 * math.tanh(mark_move / 0.005)
            mark_lag = abs(fair_yes - poly_yes_price)
        else:
            mark_lag = 0.0

        return GraphSignal(
            bias=bias, confidence=confidence,
            bull_weight=bull_weight, bear_weight=bear_weight,
            active_nodes=active_nodes, converged=converged,
            separation=separation, mark_price_lag=mark_lag,
        )
