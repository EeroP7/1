"""
Mirofish force-graph engine.

Maps 100 signal nodes across 180 edges and runs a Barnes-Hut force
simulation to detect BEAR/BULL cluster convergence.  When the two
clusters are well-separated, the dominant cluster drives the trade
direction with a confidence score.

Node layout
-----------
 0-09   price momentum   (multi-timeframe returns)
10-19   volume           (surge, VWAP dev, buy/sell ratio)
20-34   technicals       (RSI, MACD, BB, Stoch, ATR, OBV, CCI)
35-54   order-flow       (bid/ask imbalance, large-order flags)
55-69   exchange flows   (CryptoQuant inflow/outflow proxies)
70-79   derivatives      (funding rate, OI, liquidations)
80-89   market structure (trend strength, S/R proximity)
90-99   cross-asset      (DXY, gold, equity futures proxies)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np


# ── edge wiring ──────────────────────────────────────────────────────────────

def _build_edges(n_nodes: int, n_edges: int, rng: np.random.Generator) -> np.ndarray:
    """
    Return (n_edges, 2) array of node-index pairs.  Intra-group edges
    are denser; a sparse set of cross-group edges lets signals bleed.
    """
    groups = [
        list(range(0, 10)),
        list(range(10, 20)),
        list(range(20, 35)),
        list(range(35, 55)),
        list(range(55, 70)),
        list(range(70, 80)),
        list(range(80, 90)),
        list(range(90, 100)),
    ]

    edges: set[Tuple[int, int]] = set()

    # Intra-group edges (tight correlation within signal families)
    for g in groups:
        g_arr = np.array(g)
        while len(edges) < int(n_edges * 0.72):
            a, b = rng.choice(g_arr, size=2, replace=False)
            if a != b:
                edges.add((min(a, b), max(a, b)))
            if len(g_arr) <= 1:
                break

    # Cross-group edges (inter-signal coupling)
    all_idx = np.arange(n_nodes)
    while len(edges) < n_edges:
        a, b = rng.choice(all_idx, size=2, replace=False)
        edges.add((min(a, b), max(a, b)))

    arr = np.array(list(edges)[:n_edges], dtype=np.int32)
    return arr


# ── node sentiment → initial positions ───────────────────────────────────────

def _init_positions(sentiments: np.ndarray, noise: float = 0.05) -> np.ndarray:
    """
    Place nodes on a unit circle biased by sentiment.
    Bullish nodes start in the upper half, bearish in the lower half.
    """
    n = len(sentiments)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pos = np.stack([np.cos(angles), np.sin(angles)], axis=1).astype(np.float64)
    # Sentiment shifts y: +1 → top, -1 → bottom
    pos[:, 1] += sentiments * 0.4
    rng = np.random.default_rng()
    pos += rng.normal(0, noise, pos.shape)
    return pos


# ── force simulation ──────────────────────────────────────────────────────────

def _simulate(
    pos: np.ndarray,
    edges: np.ndarray,
    sentiments: np.ndarray,
    iterations: int,
    k_attr: float = 0.12,
    k_rep: float = 0.08,
    k_sent: float = 0.06,
    damping: float = 0.82,
) -> np.ndarray:
    """
    Barnes-Hut-style force simulation (simplified O(n²) for n=100).

    Forces:
      - Attractive along edges (spring, rest length 0)
      - Repulsive between all node pairs (Coulomb)
      - Sentiment gravity: each node pulled toward y = sentiment value
    """
    vel = np.zeros_like(pos)

    for _ in range(iterations):
        force = np.zeros_like(pos)

        # Repulsion: every pair
        diff = pos[:, None, :] - pos[None, :, :]        # (n,n,2)
        dist_sq = np.sum(diff ** 2, axis=2) + 1e-6       # (n,n)
        np.fill_diagonal(dist_sq, np.inf)
        rep = diff / dist_sq[:, :, None]                  # (n,n,2)
        force += k_rep * rep.sum(axis=1)

        # Attraction along edges
        a_idx, b_idx = edges[:, 0], edges[:, 1]
        delta = pos[b_idx] - pos[a_idx]                  # (e,2)
        force[a_idx] += k_attr * delta
        force[b_idx] -= k_attr * delta

        # Sentiment gravity (pull each node toward y = sentiment)
        target_y = sentiments
        force[:, 1] += k_sent * (target_y - pos[:, 1])

        vel = damping * vel + force
        pos = pos + vel

    return pos


# ── cluster detection ─────────────────────────────────────────────────────────

@dataclass
class MirofishResult:
    direction: str          # "BULL", "BEAR", or "NEUTRAL"
    confidence: float       # 0.0 – 1.0
    bull_centroid: np.ndarray = field(default_factory=lambda: np.zeros(2))
    bear_centroid: np.ndarray = field(default_factory=lambda: np.zeros(2))
    separation: float = 0.0
    latency_ms: float = 0.0


def _detect_clusters(pos: np.ndarray, sentiments: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Split nodes into BULL (sentiment > 0) and BEAR (sentiment < 0) sets.
    Return (bull_centroid, bear_centroid, separation).
    """
    bull_mask = sentiments > 0
    bear_mask = sentiments < 0

    bull_c = pos[bull_mask].mean(axis=0) if bull_mask.any() else np.zeros(2)
    bear_c = pos[bear_mask].mean(axis=0) if bear_mask.any() else np.zeros(2)

    # Intra-cluster spread (lower = more converged)
    bull_spread = pos[bull_mask].std() if bull_mask.any() else 1.0
    bear_spread = pos[bear_mask].std() if bear_mask.any() else 1.0
    avg_spread = (bull_spread + bear_spread) / 2.0 + 1e-6

    inter = float(np.linalg.norm(bull_c - bear_c))
    separation = inter / avg_spread
    return bull_c, bear_c, separation


# ── public API ────────────────────────────────────────────────────────────────

class MirofishEngine:
    """
    Stateful force-graph engine.  Call `run(sentiments)` every tick.

    Parameters
    ----------
    n_nodes     : total nodes (default 100)
    n_edges     : total edges (default 180)
    iterations  : force-sim steps per call (default 60)
    conv_thresh : separation score required to emit BULL/BEAR (default 0.68)
    seed        : reproducible edge wiring
    """

    def __init__(
        self,
        n_nodes: int = 100,
        n_edges: int = 180,
        iterations: int = 60,
        conv_thresh: float = 0.68,
        seed: int = 42,
    ) -> None:
        self.n_nodes = n_nodes
        self.n_edges = n_edges
        self.iterations = iterations
        self.conv_thresh = conv_thresh
        rng = np.random.default_rng(seed)
        self._edges = _build_edges(n_nodes, n_edges, rng)

    def run(self, sentiments: np.ndarray) -> MirofishResult:
        """
        Parameters
        ----------
        sentiments : float array of shape (n_nodes,), values in [-1, +1].
                     Positive = bullish signal, negative = bearish signal.

        Returns
        -------
        MirofishResult with direction, confidence, and cluster geometry.
        """
        assert len(sentiments) == self.n_nodes, (
            f"Expected {self.n_nodes} sentiments, got {len(sentiments)}"
        )

        t0 = time.perf_counter()

        pos = _init_positions(sentiments)
        pos = _simulate(pos, self._edges, sentiments, self.iterations)
        bull_c, bear_c, separation = _detect_clusters(pos, sentiments)

        latency_ms = (time.perf_counter() - t0) * 1000

        if separation < self.conv_thresh:
            return MirofishResult(
                direction="NEUTRAL",
                confidence=separation / self.conv_thresh,
                bull_centroid=bull_c,
                bear_centroid=bear_c,
                separation=separation,
                latency_ms=latency_ms,
            )

        # Dominant cluster: whichever centroid is higher on y-axis after simulation
        bull_score = float(bull_c[1])
        bear_score = float(-bear_c[1])

        if bull_score > bear_score:
            direction = "BULL"
            raw_conf = bull_score / (bull_score + bear_score + 1e-6)
        else:
            direction = "BEAR"
            raw_conf = bear_score / (bull_score + bear_score + 1e-6)

        # Blend with separation score for final confidence
        confidence = float(np.clip(raw_conf * (separation / (separation + 1)), 0.0, 1.0))

        return MirofishResult(
            direction=direction,
            confidence=confidence,
            bull_centroid=bull_c,
            bear_centroid=bear_c,
            separation=separation,
            latency_ms=latency_ms,
        )
