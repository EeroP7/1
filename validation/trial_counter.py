"""
Trial counter — honest tracking of strategy variants explored.

The Deflated Sharpe Ratio must be told how many distinct strategies were
tried during development so it can penalise selection bias correctly.
Under-reporting n_trials inflates DSR and gives false confidence.

This module maintains a human-readable log of every variant ever backtested
in this project, and exports the count for use in validation.

⚠️  Adding a strategy variant to the log is NOT optional — it is a
methodological requirement.  An artificially low trial count produces a
falsely optimistic DSR that may permit trading a strategy that is pure luck.

Current count covers:
  Session 1 (initial build): 1  raw momentum baseline
  Session 2 (strategy review):
    - vol targeting on baseline
    - regime filter on baseline
    - residual momentum
    - combined (res + vol + regime) on baseline
  Session 3 (full stack):
    - residual + risk parity
    - residual + vol target
    - residual + regime filter
    - residual + risk parity + vol target
    - residual + risk parity + vol target + regime
  Param sweeps in run_picks.py:
    - rebalance: D / W / M (3 values)
    - top-n: 5 / 10 (2 values)
    - dsr-threshold: 0.95 / 0.85 (2 values)
    → 3×2×2 = 12 param combos × 2 feature modes = 24 combos
  Total discrete strategy variants: 10 + 24 = 34
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_TRIAL_LOG_PATH = Path(__file__).parent.parent / "experiments" / "trial_log.json"

# Canonical list of every strategy variant ever backtested.
# ADD AN ENTRY every time you run a new backtest — never remove entries.
_TRIALS: list[dict] = [
    # --- Session 1: initial strategy ---
    {"id": 1,  "desc": "raw momentum baseline, top-5, monthly, inv-vol"},
    # --- Session 2: first overlay comparison ---
    {"id": 2,  "desc": "raw momentum + vol targeting (15% ann.)"},
    {"id": 3,  "desc": "raw momentum + regime filter (200d MA)"},
    {"id": 4,  "desc": "residual momentum, top-5, monthly"},
    {"id": 5,  "desc": "residual + vol target + regime (combined baseline)"},
    # --- Session 3: residual stack ---
    {"id": 6,  "desc": "residual + risk parity weighting"},
    {"id": 7,  "desc": "residual + vol target"},
    {"id": 8,  "desc": "residual + regime filter"},
    {"id": 9,  "desc": "residual + risk parity + vol target"},
    {"id": 10, "desc": "residual + risk parity + vol target + regime"},
    # --- Parameter sweep (rebalance × top-n × dsr-threshold × feature mode) ---
    {"id": 11, "desc": "param sweep: rebalance=D, top-n=5, dsr=0.95, raw"},
    {"id": 12, "desc": "param sweep: rebalance=D, top-n=5, dsr=0.95, residual"},
    {"id": 13, "desc": "param sweep: rebalance=D, top-n=5, dsr=0.85, raw"},
    {"id": 14, "desc": "param sweep: rebalance=D, top-n=5, dsr=0.85, residual"},
    {"id": 15, "desc": "param sweep: rebalance=D, top-n=10, dsr=0.95, raw"},
    {"id": 16, "desc": "param sweep: rebalance=D, top-n=10, dsr=0.95, residual"},
    {"id": 17, "desc": "param sweep: rebalance=D, top-n=10, dsr=0.85, raw"},
    {"id": 18, "desc": "param sweep: rebalance=D, top-n=10, dsr=0.85, residual"},
    {"id": 19, "desc": "param sweep: rebalance=W, top-n=5, dsr=0.95, raw"},
    {"id": 20, "desc": "param sweep: rebalance=W, top-n=5, dsr=0.95, residual"},
    {"id": 21, "desc": "param sweep: rebalance=W, top-n=5, dsr=0.85, raw"},
    {"id": 22, "desc": "param sweep: rebalance=W, top-n=5, dsr=0.85, residual"},
    {"id": 23, "desc": "param sweep: rebalance=W, top-n=10, dsr=0.95, raw"},
    {"id": 24, "desc": "param sweep: rebalance=W, top-n=10, dsr=0.95, residual"},
    {"id": 25, "desc": "param sweep: rebalance=W, top-n=10, dsr=0.85, raw"},
    {"id": 26, "desc": "param sweep: rebalance=W, top-n=10, dsr=0.85, residual"},
    {"id": 27, "desc": "param sweep: rebalance=M, top-n=5, dsr=0.95, raw"},
    {"id": 28, "desc": "param sweep: rebalance=M, top-n=5, dsr=0.95, residual"},
    {"id": 29, "desc": "param sweep: rebalance=M, top-n=5, dsr=0.85, raw"},
    {"id": 30, "desc": "param sweep: rebalance=M, top-n=5, dsr=0.85, residual"},
    {"id": 31, "desc": "param sweep: rebalance=M, top-n=10, dsr=0.95, raw"},
    {"id": 32, "desc": "param sweep: rebalance=M, top-n=10, dsr=0.95, residual"},
    {"id": 33, "desc": "param sweep: rebalance=M, top-n=10, dsr=0.85, raw"},
    {"id": 34, "desc": "param sweep: rebalance=M, top-n=10, dsr=0.85, residual"},
]


def n_trials() -> int:
    """Return the count of all strategy variants ever backtested."""
    return len(_TRIALS)


def log_trial(desc: str) -> int:
    """
    Register a new strategy variant and return the updated trial count.
    Call this every time you backtest something new — even if you don't adopt it.
    """
    next_id = max(t["id"] for t in _TRIALS) + 1
    _TRIALS.append({"id": next_id, "desc": desc})
    logger.warning(
        "New trial registered (id=%d, total=%d): %s",
        next_id, len(_TRIALS), desc
    )
    # persist to disk so the log survives across sessions
    _TRIAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TRIAL_LOG_PATH.write_text(json.dumps(_TRIALS, indent=2))
    return len(_TRIALS)
