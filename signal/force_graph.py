"""
Mirofish-inspired force-graph signal engine.

Builds a weighted directed graph of 100 signal nodes / 180 edges.
Nodes represent distinct market signals; edges encode directional influence.
BULL and BEAR clusters are derived from community detection on edge weights.
A "convergence" event fires when one cluster dominates the other beyond
CONVERGENCE_THRESHOLD and at least MIN_SIGNAL_NODES are active.
"""
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import networkx as nx

from config import CONVERGENCE_THRESHOLD, MIN_SIGNAL_NODES
from feeds.binance_ws import BtcSnapshot
from feeds.indicators import IndicatorSet


class Bias(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"


@dataclass
class GraphSignal:
    bias: Bias
    confidence: float        # 0-1, cluster dominance ratio
    bull_weight: float       # total weight of BULL cluster
    bear_weight: float       # total weight of BEAR cluster
    active_nodes: int
    converged: bool


# ── Node catalogue ────────────────────────────────────────────────────────────
# Each node has a (label, default_bias) pair.
# Nodes are activated / weighted based on current market state.

_NODE_DEFS: list[tuple[str, Bias]] = [
    # RSI nodes
    ("rsi_oversold",      Bias.BULL),
    ("rsi_overbought",    Bias.BEAR),
    ("rsi_bull_zone",     Bias.BULL),
    ("rsi_bear_zone",     Bias.BEAR),
    ("rsi_divergence_up", Bias.BULL),
    ("rsi_divergence_dn", Bias.BEAR),

    # StochRSI nodes
    ("stoch_cross_up",    Bias.BULL),
    ("stoch_cross_dn",    Bias.BEAR),
    ("stoch_os",          Bias.BULL),
    ("stoch_ob",          Bias.BEAR),

    # EMA nodes
    ("ema9_above_21",     Bias.BULL),
    ("ema9_below_21",     Bias.BEAR),
    ("ema21_above_50",    Bias.BULL),
    ("ema21_below_50",    Bias.BEAR),
    ("price_above_ema9",  Bias.BULL),
    ("price_below_ema9",  Bias.BEAR),
    ("price_above_ema50", Bias.BULL),
    ("price_below_ema50", Bias.BEAR),

    # MACD nodes
    ("macd_hist_pos",     Bias.BULL),
    ("macd_hist_neg",     Bias.BEAR),
    ("macd_cross_up",     Bias.BULL),
    ("macd_cross_dn",     Bias.BEAR),

    # Bollinger nodes
    ("bb_lower_touch",    Bias.BULL),
    ("bb_upper_touch",    Bias.BEAR),
    ("bb_above_mid",      Bias.BULL),
    ("bb_below_mid",      Bias.BEAR),
    ("bb_squeeze",        Bias.NEUTRAL),
    ("bb_expansion",      Bias.NEUTRAL),

    # Volume / OBV nodes
    ("obv_accumulate",    Bias.BULL),
    ("obv_distribute",    Bias.BEAR),
    ("buy_pressure_hi",   Bias.BULL),
    ("buy_pressure_lo",   Bias.BEAR),
    ("vol_surge_bull",    Bias.BULL),
    ("vol_surge_bear",    Bias.BEAR),
    ("vol_dry_up",        Bias.NEUTRAL),

    # VWAP nodes
    ("price_above_vwap",  Bias.BULL),
    ("price_below_vwap",  Bias.BEAR),

    # Order-flow imbalance nodes
    ("ofi_positive",      Bias.BULL),
    ("ofi_negative",      Bias.BEAR),
    ("ofi_neutral",       Bias.NEUTRAL),

    # Exchange-flow proxy nodes (derived from taker buy/sell ratio)
    ("exchange_inflow",   Bias.BEAR),   # high inflow → sell pressure
    ("exchange_outflow",  Bias.BULL),   # outflow → accumulation
    ("flow_neutral",      Bias.NEUTRAL),

    # Spread / liquidity nodes
    ("spread_tight",      Bias.NEUTRAL),
    ("spread_wide",       Bias.BEAR),
    ("deep_bid",          Bias.BULL),
    ("deep_ask",          Bias.BEAR),

    # Momentum nodes
    ("momentum_accel_up", Bias.BULL),
    ("momentum_accel_dn", Bias.BEAR),
    ("momentum_flat",     Bias.NEUTRAL),

    # Candle pattern nodes
    ("candle_bull_body",  Bias.BULL),
    ("candle_bear_body",  Bias.BEAR),
    ("upper_wick",        Bias.BEAR),
    ("lower_wick",        Bias.BULL),
    ("doji",              Bias.NEUTRAL),

    # Time-window nodes (time remaining in 5-min candle)
    ("early_window",      Bias.NEUTRAL),
    ("late_window",       Bias.NEUTRAL),
    ("window_close",      Bias.NEUTRAL),

    # Polymarket lag-detection nodes
    ("poly_lag_bull",     Bias.BULL),
    ("poly_lag_bear",     Bias.BEAR),
    ("poly_aligned",      Bias.NEUTRAL),

    # Higher-order composite nodes
    ("trend_aligned_bull", Bias.BULL),
    ("trend_aligned_bear", Bias.BEAR),
    ("conflicting_signals", Bias.NEUTRAL),
    ("breakout_up",        Bias.BULL),
    ("breakout_dn",        Bias.BEAR),
    ("range_bound",        Bias.NEUTRAL),
    ("volatility_low",     Bias.NEUTRAL),
    ("volatility_high",    Bias.NEUTRAL),
    ("reversal_potential", Bias.NEUTRAL),

    # Sentiment proxy nodes
    ("sentiment_fear",    Bias.BEAR),
    ("sentiment_greed",   Bias.BULL),
    ("sentiment_neutral", Bias.NEUTRAL),

    # Price-level nodes
    ("near_resistance",   Bias.BEAR),
    ("near_support",      Bias.BULL),
    ("in_range",          Bias.NEUTRAL),

    # Multi-timeframe alignment nodes
    ("mtf_bull",          Bias.BULL),
    ("mtf_bear",          Bias.BEAR),
    ("mtf_mixed",         Bias.NEUTRAL),

    # Risk/reward nodes
    ("rr_favorable_bull", Bias.BULL),
    ("rr_favorable_bear", Bias.BEAR),
    ("rr_unfavorable",    Bias.NEUTRAL),

    # Filler neutral nodes to reach 100
    ("neutral_a",  Bias.NEUTRAL), ("neutral_b",  Bias.NEUTRAL),
    ("neutral_c",  Bias.NEUTRAL), ("neutral_d",  Bias.NEUTRAL),
    ("neutral_e",  Bias.NEUTRAL), ("neutral_f",  Bias.NEUTRAL),
    ("neutral_g",  Bias.NEUTRAL), ("neutral_h",  Bias.NEUTRAL),
    ("neutral_i",  Bias.NEUTRAL), ("neutral_j",  Bias.NEUTRAL),
    ("neutral_k",  Bias.NEUTRAL), ("neutral_l",  Bias.NEUTRAL),
    ("neutral_m",  Bias.NEUTRAL), ("neutral_n",  Bias.NEUTRAL),
    ("neutral_o",  Bias.NEUTRAL), ("neutral_p",  Bias.NEUTRAL),
    ("neutral_q",  Bias.NEUTRAL), ("neutral_r",  Bias.NEUTRAL),
]

assert len(_NODE_DEFS) == 100, f"Expected 100 nodes, got {len(_NODE_DEFS)}"

# ── Edge catalogue ─────────────────────────────────────────────────────────────
# (source_label, target_label, base_weight)
# Weight is further modulated at runtime based on signal strength.

_EDGE_DEFS: list[tuple[str, str, float]] = [
    # RSI → momentum
    ("rsi_oversold",      "momentum_accel_up", 0.9),
    ("rsi_overbought",    "momentum_accel_dn", 0.9),
    ("rsi_bull_zone",     "trend_aligned_bull", 0.7),
    ("rsi_bear_zone",     "trend_aligned_bear", 0.7),
    ("rsi_divergence_up", "reversal_potential", 0.8),
    ("rsi_divergence_dn", "reversal_potential", 0.8),

    # StochRSI → momentum
    ("stoch_cross_up",    "momentum_accel_up", 0.8),
    ("stoch_cross_dn",    "momentum_accel_dn", 0.8),
    ("stoch_os",          "reversal_potential", 0.6),
    ("stoch_ob",          "reversal_potential", 0.6),
    ("stoch_cross_up",    "rr_favorable_bull", 0.5),
    ("stoch_cross_dn",    "rr_favorable_bear", 0.5),

    # EMA relationships
    ("ema9_above_21",     "trend_aligned_bull", 0.85),
    ("ema9_below_21",     "trend_aligned_bear", 0.85),
    ("ema21_above_50",    "mtf_bull", 0.75),
    ("ema21_below_50",    "mtf_bear", 0.75),
    ("price_above_ema9",  "breakout_up", 0.6),
    ("price_below_ema9",  "breakout_dn", 0.6),
    ("price_above_ema50", "mtf_bull", 0.7),
    ("price_below_ema50", "mtf_bear", 0.7),

    # MACD
    ("macd_hist_pos",     "momentum_accel_up", 0.8),
    ("macd_hist_neg",     "momentum_accel_dn", 0.8),
    ("macd_cross_up",     "trend_aligned_bull", 0.9),
    ("macd_cross_dn",     "trend_aligned_bear", 0.9),
    ("macd_hist_pos",     "rr_favorable_bull", 0.6),
    ("macd_hist_neg",     "rr_favorable_bear", 0.6),

    # Bollinger → context
    ("bb_lower_touch",    "reversal_potential", 0.7),
    ("bb_upper_touch",    "reversal_potential", 0.7),
    ("bb_above_mid",      "sentiment_greed", 0.5),
    ("bb_below_mid",      "sentiment_fear", 0.5),
    ("bb_squeeze",        "volatility_low", 0.9),
    ("bb_expansion",      "volatility_high", 0.9),

    # Volume
    ("obv_accumulate",    "sentiment_greed", 0.7),
    ("obv_distribute",    "sentiment_fear", 0.7),
    ("buy_pressure_hi",   "breakout_up", 0.75),
    ("buy_pressure_lo",   "breakout_dn", 0.75),
    ("vol_surge_bull",    "momentum_accel_up", 0.85),
    ("vol_surge_bear",    "momentum_accel_dn", 0.85),
    ("vol_dry_up",        "range_bound", 0.6),
    ("obv_accumulate",    "near_support", 0.4),

    # VWAP
    ("price_above_vwap",  "trend_aligned_bull", 0.65),
    ("price_below_vwap",  "trend_aligned_bear", 0.65),
    ("price_above_vwap",  "sentiment_greed", 0.4),
    ("price_below_vwap",  "sentiment_fear", 0.4),

    # OFI
    ("ofi_positive",      "deep_bid", 0.8),
    ("ofi_negative",      "deep_ask", 0.8),
    ("ofi_positive",      "buy_pressure_hi", 0.7),
    ("ofi_negative",      "buy_pressure_lo", 0.7),

    # Exchange flow proxies
    ("exchange_inflow",   "sentiment_fear", 0.6),
    ("exchange_outflow",  "sentiment_greed", 0.6),
    ("exchange_inflow",   "breakout_dn", 0.5),
    ("exchange_outflow",  "breakout_up", 0.5),

    # Liquidity
    ("deep_bid",          "rr_favorable_bull", 0.7),
    ("deep_ask",          "rr_favorable_bear", 0.7),
    ("spread_tight",      "momentum_accel_up", 0.3),
    ("spread_wide",       "volatility_high", 0.5),

    # Polymarket lag
    ("poly_lag_bull",     "breakout_up", 0.95),
    ("poly_lag_bear",     "breakout_dn", 0.95),
    ("poly_lag_bull",     "rr_favorable_bull", 0.9),
    ("poly_lag_bear",     "rr_favorable_bear", 0.9),
    ("poly_aligned",      "range_bound", 0.3),

    # Composite aggregators
    ("trend_aligned_bull", "mtf_bull", 0.8),
    ("trend_aligned_bear", "mtf_bear", 0.8),
    ("momentum_accel_up",  "breakout_up", 0.85),
    ("momentum_accel_dn",  "breakout_dn", 0.85),
    ("breakout_up",        "rr_favorable_bull", 0.9),
    ("breakout_dn",        "rr_favorable_bear", 0.9),
    ("reversal_potential", "conflicting_signals", 0.5),
    ("conflicting_signals","rr_unfavorable", 0.6),
    ("range_bound",        "rr_unfavorable", 0.5),

    # Sentiment → bias
    ("sentiment_greed",   "mtf_bull", 0.6),
    ("sentiment_fear",    "mtf_bear", 0.6),
    ("sentiment_greed",   "near_support", 0.4),
    ("sentiment_fear",    "near_resistance", 0.4),

    # Cross-links for graph density
    ("rsi_bull_zone",     "price_above_vwap", 0.4),
    ("rsi_bear_zone",     "price_below_vwap", 0.4),
    ("ema9_above_21",     "price_above_vwap", 0.45),
    ("ema9_below_21",     "price_below_vwap", 0.45),
    ("macd_hist_pos",     "obv_accumulate", 0.5),
    ("macd_hist_neg",     "obv_distribute", 0.5),
    ("buy_pressure_hi",   "sentiment_greed", 0.5),
    ("buy_pressure_lo",   "sentiment_fear", 0.5),
    ("vol_surge_bull",    "obv_accumulate", 0.6),
    ("vol_surge_bear",    "obv_distribute", 0.6),
    ("deep_bid",          "near_support", 0.5),
    ("deep_ask",          "near_resistance", 0.5),
    ("mtf_bull",          "rr_favorable_bull", 0.7),
    ("mtf_bear",          "rr_favorable_bear", 0.7),
    ("near_support",      "reversal_potential", 0.4),
    ("near_resistance",   "reversal_potential", 0.4),
    ("stoch_os",          "near_support", 0.55),
    ("stoch_ob",          "near_resistance", 0.55),
    ("bb_lower_touch",    "near_support", 0.65),
    ("bb_upper_touch",    "near_resistance", 0.65),
    ("ofi_positive",      "trend_aligned_bull", 0.5),
    ("ofi_negative",      "trend_aligned_bear", 0.5),
    ("volatility_high",   "breakout_up", 0.35),
    ("volatility_high",   "breakout_dn", 0.35),
    ("volatility_low",    "range_bound", 0.55),
    ("candle_bull_body",  "momentum_accel_up", 0.65),
    ("candle_bear_body",  "momentum_accel_dn", 0.65),
    ("lower_wick",        "reversal_potential", 0.5),
    ("upper_wick",        "reversal_potential", 0.5),
    ("doji",              "conflicting_signals", 0.6),
    ("early_window",      "spread_tight", 0.3),
    ("late_window",       "momentum_accel_up", 0.2),
    ("window_close",      "conflicting_signals", 0.4),
    ("rr_favorable_bull", "trend_aligned_bull", 0.6),
    ("rr_favorable_bear", "trend_aligned_bear", 0.6),
    ("rr_unfavorable",    "conflicting_signals", 0.7),
    ("in_range",          "range_bound", 0.5),
    ("in_range",          "volatility_low", 0.4),
    ("mtf_bull",          "trend_aligned_bull", 0.65),
    ("mtf_bear",          "trend_aligned_bear", 0.65),

    # Additional cross-signal edges to reach 180
    ("rsi_oversold",      "reversal_potential", 0.6),
    ("rsi_overbought",    "reversal_potential", 0.6),
    ("rsi_bull_zone",     "obv_accumulate", 0.35),
    ("rsi_bear_zone",     "obv_distribute", 0.35),
    ("stoch_cross_up",    "obv_accumulate", 0.4),
    ("stoch_cross_dn",    "obv_distribute", 0.4),
    ("ema9_above_21",     "macd_hist_pos", 0.4),
    ("ema9_below_21",     "macd_hist_neg", 0.4),
    ("macd_cross_up",     "buy_pressure_hi", 0.5),
    ("macd_cross_dn",     "buy_pressure_lo", 0.5),
    ("bb_lower_touch",    "stoch_os", 0.45),
    ("bb_upper_touch",    "stoch_ob", 0.45),
    ("vol_surge_bull",    "buy_pressure_hi", 0.6),
    ("vol_surge_bear",    "buy_pressure_lo", 0.6),
    ("vol_dry_up",        "spread_wide", 0.4),
    ("ofi_positive",      "vol_surge_bull", 0.45),
    ("ofi_negative",      "vol_surge_bear", 0.45),
    ("exchange_inflow",   "deep_ask", 0.5),
    ("exchange_outflow",  "deep_bid", 0.5),
    ("deep_bid",          "momentum_accel_up", 0.45),
    ("deep_ask",          "momentum_accel_dn", 0.45),
    ("candle_bull_body",  "obv_accumulate", 0.4),
    ("candle_bear_body",  "obv_distribute", 0.4),
    ("lower_wick",        "near_support", 0.5),
    ("upper_wick",        "near_resistance", 0.5),
    ("doji",              "volatility_low", 0.4),
    ("early_window",      "ofi_neutral", 0.3),
    ("late_window",       "ofi_positive", 0.25),
    ("window_close",      "spread_wide", 0.35),
    ("poly_lag_bull",     "sentiment_greed", 0.6),
    ("poly_lag_bear",     "sentiment_fear", 0.6),
    ("poly_aligned",      "ofi_neutral", 0.3),
    ("trend_aligned_bull","buy_pressure_hi", 0.5),
    ("trend_aligned_bear","buy_pressure_lo", 0.5),
    ("momentum_accel_up", "obv_accumulate", 0.5),
    ("momentum_accel_dn", "obv_distribute", 0.5),
    ("breakout_up",       "vol_surge_bull", 0.55),
    ("breakout_dn",       "vol_surge_bear", 0.55),
    ("reversal_potential","near_support", 0.35),
    ("reversal_potential","near_resistance", 0.35),
    ("conflicting_signals","momentum_flat", 0.5),
    ("range_bound",       "volatility_low", 0.45),
    ("volatility_high",   "spread_wide", 0.5),
    ("volatility_low",    "spread_tight", 0.5),
    ("sentiment_greed",   "buy_pressure_hi", 0.45),
    ("sentiment_fear",    "buy_pressure_lo", 0.45),
    ("near_support",      "rr_favorable_bull", 0.5),
    ("near_resistance",   "rr_favorable_bear", 0.5),
    ("mtf_bull",          "buy_pressure_hi", 0.4),
    ("mtf_bear",          "buy_pressure_lo", 0.4),
    ("mtf_mixed",         "conflicting_signals", 0.55),
    ("rr_favorable_bull", "momentum_accel_up", 0.45),
    ("rr_favorable_bear", "momentum_accel_dn", 0.45),
    ("rr_unfavorable",    "momentum_flat", 0.5),
    ("price_above_vwap",  "sentiment_greed", 0.45),
    ("price_below_vwap",  "sentiment_fear", 0.45),
    ("bb_squeeze",        "momentum_flat", 0.5),
    ("bb_expansion",      "momentum_accel_up", 0.3),
    ("bb_expansion",      "momentum_accel_dn", 0.3),
    ("spread_tight",      "ofi_positive", 0.3),
    ("spread_wide",       "ofi_negative", 0.3),
    ("candle_bull_body",  "rr_favorable_bull", 0.4),
    ("candle_bear_body",  "rr_favorable_bear", 0.4),
    ("obv_accumulate",    "trend_aligned_bull", 0.45),
    ("obv_distribute",    "trend_aligned_bear", 0.45),
    ("exchange_inflow",   "vol_surge_bear", 0.4),
]

assert len(_EDGE_DEFS) == 180, f"Expected 180 edges, got {len(_EDGE_DEFS)}"


class ForceGraph:
    """
    Constructs the 100-node / 180-edge directed graph and evaluates
    cluster convergence given a market snapshot + indicator set.
    """

    def __init__(self) -> None:
        self._G = nx.DiGraph()
        self._node_bias: dict[str, Bias] = {}
        self._build_graph()

    def _build_graph(self) -> None:
        for label, bias in _NODE_DEFS:
            self._G.add_node(label, bias=bias, active=False, weight=0.0)
            self._node_bias[label] = bias
        for src, dst, w in _EDGE_DEFS:
            self._G.add_edge(src, dst, base_weight=w, effective_weight=w)

    def evaluate(
        self,
        snap: BtcSnapshot,
        ind: IndicatorSet,
        poly_yes_price: float,    # 0-1, Polymarket YES price
        poly_no_price: float,     # 0-1
        seconds_to_window_close: float,
    ) -> GraphSignal:
        self._activate_nodes(snap, ind, poly_yes_price, poly_no_price,
                             seconds_to_window_close)
        self._propagate_weights()
        return self._cluster_signal()

    # ── node activation ───────────────────────────────────────────────────────

    def _activate_nodes(
        self,
        snap: BtcSnapshot,
        ind: IndicatorSet,
        py: float,
        pn: float,
        ttc: float,
    ) -> None:
        p = snap.price
        G = self._G

        def activate(label: str, weight: float) -> None:
            G.nodes[label]["active"] = True
            G.nodes[label]["weight"] = max(G.nodes[label]["weight"], weight)

        # reset all
        for n in G.nodes:
            G.nodes[n]["active"] = False
            G.nodes[n]["weight"] = 0.0

        # RSI
        if ind.rsi_14 < 30:
            activate("rsi_oversold", (30 - ind.rsi_14) / 30)
        if ind.rsi_14 > 70:
            activate("rsi_overbought", (ind.rsi_14 - 70) / 30)
        if 50 < ind.rsi_14 <= 70:
            activate("rsi_bull_zone", (ind.rsi_14 - 50) / 20)
        if 30 <= ind.rsi_14 < 50:
            activate("rsi_bear_zone", (50 - ind.rsi_14) / 20)

        # StochRSI
        if ind.stoch_rsi_k > ind.stoch_rsi_d and ind.stoch_rsi_k < 80:
            activate("stoch_cross_up", min(1.0, (ind.stoch_rsi_k - ind.stoch_rsi_d) / 20))
        if ind.stoch_rsi_k < ind.stoch_rsi_d and ind.stoch_rsi_k > 20:
            activate("stoch_cross_dn", min(1.0, (ind.stoch_rsi_d - ind.stoch_rsi_k) / 20))
        if ind.stoch_rsi_k < 20:
            activate("stoch_os", (20 - ind.stoch_rsi_k) / 20)
        if ind.stoch_rsi_k > 80:
            activate("stoch_ob", (ind.stoch_rsi_k - 80) / 20)

        # EMAs
        if ind.ema_9 > ind.ema_21:
            activate("ema9_above_21", abs(ind.ema_9 - ind.ema_21) / ind.ema_21)
        else:
            activate("ema9_below_21", abs(ind.ema_9 - ind.ema_21) / ind.ema_21)
        if ind.ema_21 > ind.ema_50:
            activate("ema21_above_50", abs(ind.ema_21 - ind.ema_50) / ind.ema_50)
        else:
            activate("ema21_below_50", abs(ind.ema_21 - ind.ema_50) / ind.ema_50)
        if p > ind.ema_9:
            activate("price_above_ema9",  (p - ind.ema_9) / ind.ema_9)
        else:
            activate("price_below_ema9",  (ind.ema_9 - p) / ind.ema_9)
        if p > ind.ema_50:
            activate("price_above_ema50", (p - ind.ema_50) / ind.ema_50)
        else:
            activate("price_below_ema50", (ind.ema_50 - p) / ind.ema_50)

        # MACD
        if ind.macd_hist > 0:
            activate("macd_hist_pos", min(1.0, ind.macd_hist / p * 10000))
        else:
            activate("macd_hist_neg", min(1.0, abs(ind.macd_hist) / p * 10000))
        # MACD cross: use cross_up/dn nodes when histogram changes sign
        # (simplified: use sign of macd_line vs signal)
        if ind.macd_line > ind.macd_signal:
            activate("macd_cross_up", 0.6)
        else:
            activate("macd_cross_dn", 0.6)

        # Bollinger
        spread = ind.bb_upper - ind.bb_lower
        if p < ind.bb_lower * 1.002:
            activate("bb_lower_touch", min(1.0, (ind.bb_lower - p) / spread + 0.3))
        if p > ind.bb_upper * 0.998:
            activate("bb_upper_touch", min(1.0, (p - ind.bb_upper) / spread + 0.3))
        if p > ind.bb_mid:
            activate("bb_above_mid", (p - ind.bb_mid) / (ind.bb_upper - ind.bb_mid + 1e-9))
        else:
            activate("bb_below_mid", (ind.bb_mid - p) / (ind.bb_mid - ind.bb_lower + 1e-9))
        if ind.bb_width < 0.015:
            activate("bb_squeeze", 0.8)
        if ind.bb_width > 0.04:
            activate("bb_expansion", 0.8)

        # OBV / volume
        if ind.obv > 0.05:
            activate("obv_accumulate", min(1.0, ind.obv * 2))
        elif ind.obv < -0.05:
            activate("obv_distribute", min(1.0, abs(ind.obv) * 2))
        if ind.buy_sell_ratio > 0.55:
            activate("buy_pressure_hi", (ind.buy_sell_ratio - 0.5) * 2)
        elif ind.buy_sell_ratio < 0.45:
            activate("buy_pressure_lo", (0.5 - ind.buy_sell_ratio) * 2)

        # Volume surge (use taker buy vs sell on last kline as proxy)
        if snap.klines:
            last_k = snap.klines[0]
            avg_vol = sum(k.volume for k in snap.klines[:10]) / min(10, len(snap.klines))
            if last_k.volume > avg_vol * 1.5:
                if last_k.taker_buy_volume > last_k.taker_sell_volume:
                    activate("vol_surge_bull", min(1.0, last_k.volume / avg_vol - 1))
                else:
                    activate("vol_surge_bear", min(1.0, last_k.volume / avg_vol - 1))
            elif last_k.volume < avg_vol * 0.5:
                activate("vol_dry_up", 0.7)

        # VWAP
        if p > ind.vwap:
            activate("price_above_vwap", (p - ind.vwap) / ind.vwap)
        else:
            activate("price_below_vwap", (ind.vwap - p) / ind.vwap)

        # OFI
        if snap.order_flow_imbalance > 0.1:
            activate("ofi_positive", snap.order_flow_imbalance)
        elif snap.order_flow_imbalance < -0.1:
            activate("ofi_negative", abs(snap.order_flow_imbalance))
        else:
            activate("ofi_neutral", 0.5)

        # Exchange-flow proxy (taker-buy ratio as outflow/inflow signal)
        if ind.buy_sell_ratio < 0.4:
            activate("exchange_inflow", (0.4 - ind.buy_sell_ratio) * 2)
        elif ind.buy_sell_ratio > 0.6:
            activate("exchange_outflow", (ind.buy_sell_ratio - 0.6) * 2)
        else:
            activate("flow_neutral", 0.5)

        # Spread / liquidity
        spread_pct = (snap.ask - snap.bid) / p
        if spread_pct < 0.0005:
            activate("spread_tight", 0.8)
        elif spread_pct > 0.002:
            activate("spread_wide", 0.8)
        if snap.bid_qty > snap.ask_qty * 1.3:
            activate("deep_bid", min(1.0, snap.bid_qty / snap.ask_qty - 1))
        elif snap.ask_qty > snap.bid_qty * 1.3:
            activate("deep_ask", min(1.0, snap.ask_qty / snap.bid_qty - 1))

        # Candle patterns (last closed candle)
        if len(snap.klines) > 1:
            ck = snap.klines[1]
            body = ck.close - ck.open
            total_range = ck.high - ck.low or 1
            upper_wick = ck.high - max(ck.open, ck.close)
            lower_wick = min(ck.open, ck.close) - ck.low
            body_ratio = abs(body) / total_range
            if body > 0 and body_ratio > 0.5:
                activate("candle_bull_body", body_ratio)
            elif body < 0 and body_ratio > 0.5:
                activate("candle_bear_body", body_ratio)
            if upper_wick / total_range > 0.3:
                activate("upper_wick", upper_wick / total_range)
            if lower_wick / total_range > 0.3:
                activate("lower_wick", lower_wick / total_range)
            if body_ratio < 0.15:
                activate("doji", 0.7)

        # Time-window nodes
        if ttc > 240:
            activate("early_window", 0.6)
        elif ttc > 60:
            activate("late_window", 0.6)
        else:
            activate("window_close", min(1.0, 1 - ttc / 60))

        # Polymarket lag detection
        # Theoretical fair value: YES price should ≈ P(BTC up in 5 min)
        # We use bull_score as a rough fair-value proxy
        implied_yes_fair = ind.bull_score
        lag = implied_yes_fair - py
        if lag > 0.03:    # YES underpriced relative to signals
            activate("poly_lag_bull", min(1.0, lag * 10))
        elif lag < -0.03: # YES overpriced / NO underpriced
            activate("poly_lag_bear", min(1.0, abs(lag) * 10))
        else:
            activate("poly_aligned", 0.5)

        # Momentum
        if ind.bull_score > 0.65:
            activate("momentum_accel_up", ind.bull_score)
        elif ind.bear_score > 0.65:
            activate("momentum_accel_dn", ind.bear_score)
        else:
            activate("momentum_flat", 0.5)

        # Multi-timeframe composites
        bull_ema = ind.ema_9 > ind.ema_21 > ind.ema_50
        bear_ema = ind.ema_9 < ind.ema_21 < ind.ema_50
        if bull_ema:
            activate("mtf_bull", 0.8)
        elif bear_ema:
            activate("mtf_bear", 0.8)
        else:
            activate("mtf_mixed", 0.6)

        # Volatility context
        if ind.bb_width < 0.01:
            activate("volatility_low", 0.8)
        elif ind.bb_width > 0.03:
            activate("volatility_high", 0.8)

    # ── weight propagation ────────────────────────────────────────────────────

    def _propagate_weights(self) -> None:
        """
        One-pass message-passing: active source nodes multiply their weight
        by the edge base_weight and add to the target's effective weight.
        """
        G = self._G
        for n in G.nodes:
            G.nodes[n]["prop_weight"] = G.nodes[n]["weight"]

        for src, dst, data in G.edges(data=True):
            src_node = G.nodes[src]
            if src_node["active"] and src_node["weight"] > 0:
                contribution = src_node["weight"] * data["base_weight"]
                G.nodes[dst]["prop_weight"] = (
                    G.nodes[dst].get("prop_weight", 0) + contribution
                )
                G.nodes[dst]["active"] = True

    # ── cluster scoring ───────────────────────────────────────────────────────

    def _cluster_signal(self) -> GraphSignal:
        G = self._G
        bull_weight = 0.0
        bear_weight = 0.0
        active_nodes = 0

        for n, data in G.nodes(data=True):
            w = data.get("prop_weight", 0.0)
            if not data["active"] or w == 0:
                continue
            active_nodes += 1
            bias = data["bias"]
            if bias == Bias.BULL:
                bull_weight += w
            elif bias == Bias.BEAR:
                bear_weight += w

        total = bull_weight + bear_weight
        if total == 0 or active_nodes < MIN_SIGNAL_NODES:
            return GraphSignal(
                bias=Bias.NEUTRAL, confidence=0.0,
                bull_weight=bull_weight, bear_weight=bear_weight,
                active_nodes=active_nodes, converged=False,
            )

        bull_ratio = bull_weight / total
        bear_ratio = bear_weight / total

        if bull_ratio >= CONVERGENCE_THRESHOLD:
            bias = Bias.BULL
            confidence = bull_ratio
        elif bear_ratio >= CONVERGENCE_THRESHOLD:
            bias = Bias.BEAR
            confidence = bear_ratio
        else:
            bias = Bias.NEUTRAL
            confidence = max(bull_ratio, bear_ratio)

        converged = bias != Bias.NEUTRAL

        return GraphSignal(
            bias=bias,
            confidence=confidence,
            bull_weight=bull_weight,
            bear_weight=bear_weight,
            active_nodes=active_nodes,
            converged=converged,
        )
