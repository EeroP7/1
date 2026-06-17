"""
AI analyst — full due-diligence screen for each pick.

For every pick the analyst researches four dimensions:
  1. Leadership     — CEO/CFO stability, insider buying, credibility signals
  2. Narrative      — is the price move backed by a real story or unexplained?
  3. Macro/sector   — headwinds: rates, tariffs, regulation, cycle position
  4. Event risk     — earnings, FDA, court, lock-up, M&A

Verdicts (can ONLY reduce risk, never add it):
  VETO    → drop the pick entirely
  CAUTION → halve the position weight
  CLEAR   → trade as the model intended

All scores are journaled separately from the model's signal so the overlay's
value can be measured independently after the fact.

Requires ANTHROPIC_API_KEY in the environment.  Without it, every pick passes
through as CLEAR (flagged "unscreened").
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from news.scanner import NewsItem

logger = logging.getLogger(__name__)

MODEL_ID = "claude-opus-4-8"


# ---------------------------------------------------------------------------
# Structured output schema
# ---------------------------------------------------------------------------

class DueDiligence(BaseModel):
    verdict: str            # "VETO" | "CAUTION" | "CLEAR"
    reason: str             # one line ≤ 20 words, goes straight into journal
    # subscores 0–3: 0=red flag, 1=concern, 2=neutral, 3=positive
    leadership_score: int
    narrative_score: int
    macro_score: int
    event_risk_score: int   # 3=no events, 0=imminent binary event
    earnings_within_10d: bool
    key_risks: list[str]    # up to 3 bullet points, journaled for human review


@dataclass
class ScreenResult:
    ticker: str
    verdict: str
    reason: str
    earnings_risk: bool
    screened: bool
    leadership_score: int = 2
    narrative_score: int = 2
    macro_score: int = 2
    event_risk_score: int = 3
    key_risks: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior equity analyst performing rapid due diligence
for a systematic momentum strategy. The quant model has already selected its picks
based on price signals. Your job is to surface NON-PRICE risks the model cannot see.

You will be given:
- The ticker and company name
- Recent news headlines and summaries (last 7 days)
- The reason the model picked it (momentum / trend signals)

Score each of four dimensions from 0–3:
  leadership_score:  3=stable respected management, 2=neutral, 1=recent changes or concerns, 0=scandal/departure/credibility issue
  narrative_score:   3=clear fundamental catalyst backing the move, 2=neutral, 1=move looks unexplained or crowded, 0=price move contradicts fundamentals
  macro_score:       3=sector tailwinds, 2=neutral, 1=visible headwind (rates/tariffs/regulation), 0=severe macro headwind
  event_risk_score:  3=no known events, 2=minor events, 1=significant event within 30d, 0=binary event within 10d (earnings/FDA/court/lockup)

Then give:
  verdict:
    "VETO"    — event_risk_score=0 OR leadership_score=0 OR (two or more scores are 0–1 AND narrative is negative)
    "CAUTION" — one score is 0–1 OR earnings suspected within 10–30 days
    "CLEAR"   — everything else. Most picks should be CLEAR.
  reason: one sentence ≤ 20 words for the trade journal.
  earnings_within_10d: true only if you have clear evidence of earnings in next 10 days.
  key_risks: up to 3 specific risks worth monitoring (empty list if CLEAR with no concerns).

CRITICAL RULES:
- You can ONLY reduce risk (VETO or CAUTION). You may NEVER suggest buying more.
- Negative headlines alone are NOT a veto. Momentum buys quality names in pullbacks.
- Be calibrated: issue VETO sparingly. A wrong VETO throws away real model edge.
- key_risks should be specific ("CEO sold $40M shares last week"), not generic ("market risk")."""


# ---------------------------------------------------------------------------
# Main screening function
# ---------------------------------------------------------------------------

def screen_picks(
    news_by_ticker: "dict[str, list[NewsItem]]",
    model_rationale: dict[str, str] | None = None,
    earnings_flags: dict[str, str] | None = None,
) -> dict[str, ScreenResult]:
    """Full due-diligence screen for each ticker. Returns {ticker: ScreenResult}.

    earnings_flags: {ticker: earnings_flag_string} from output.picks._earnings_flag.
    If a ticker has an imminent earnings flag, it is auto-CAUTION'd even without an API key.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    earnings_flags = earnings_flags or {}

    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set — AI due diligence SKIPPED. "
            "All picks pass through unscreened (earnings flags still applied)."
        )
        results = {}
        for t in news_by_ticker:
            flag = earnings_flags.get(t, "")
            if "EARNINGS" in flag:
                results[t] = ScreenResult(
                    t, "CAUTION", f"earnings imminent: {flag}", True, screened=False,
                    event_risk_score=0,
                )
                logger.warning("Auto-CAUTION %s — %s", t, flag)
            else:
                results[t] = ScreenResult(t, "CLEAR", "unscreened (no API key)", False, screened=False)
        return results

    import anthropic
    client = anthropic.Anthropic()
    results: dict[str, ScreenResult] = {}

    for ticker, items in news_by_ticker.items():
        rationale = (model_rationale or {}).get(ticker, "momentum/trend signals")
        earnings_note = earnings_flags.get(ticker, "no earnings within 10 days")

        headlines_block = ""
        if items:
            headlines_block = "\n".join(
                f"- [{n.created_at[:10]}] {n.headline}"
                + (f"\n  Summary: {n.summary[:300]}" if n.summary else "")
                for n in items[:15]
            )
        else:
            headlines_block = "(no recent news found)"

        user_msg = (
            f"Ticker: {ticker}\n"
            f"Why the model picked it: {rationale}\n"
            f"Earnings calendar: {earnings_note}\n\n"
            f"Recent news (last 7 days):\n{headlines_block}"
        )

        try:
            response = client.messages.parse(
                model=MODEL_ID,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
                output_format=DueDiligence,
            )
            d = response.parsed_output
            verdict = d.verdict if d.verdict in ("VETO", "CAUTION", "CLEAR") else "CLEAR"
            results[ticker] = ScreenResult(
                ticker=ticker,
                verdict=verdict,
                reason=d.reason,
                earnings_risk=d.earnings_within_10d,
                screened=True,
                leadership_score=d.leadership_score,
                narrative_score=d.narrative_score,
                macro_score=d.macro_score,
                event_risk_score=d.event_risk_score,
                key_risks=d.key_risks[:3],
            )
            _log_result(ticker, results[ticker])

        except Exception as exc:
            logger.warning("Due diligence failed for %s (%s) — passing through.", ticker, exc)
            results[ticker] = ScreenResult(
                ticker, "CLEAR", f"screening error: {type(exc).__name__}", False, screened=False
            )

    return results


def _log_result(ticker: str, r: ScreenResult) -> None:
    scores = f"L={r.leadership_score} N={r.narrative_score} M={r.macro_score} E={r.event_risk_score}"
    logger.info("Due diligence %s: %s [%s] — %s", ticker, r.verdict, scores, r.reason)
    for risk in r.key_risks:
        logger.info("  ⚠  %s: %s", ticker, risk)


# ---------------------------------------------------------------------------
# Apply verdicts to sized picks
# ---------------------------------------------------------------------------

def apply_screening(
    sized_picks: list,
    screens: dict[str, ScreenResult],
) -> tuple[list, list]:
    """
    Apply verdicts to sized picks.

    VETO  → remove pick (capital stays in cash, never redistributed)
    CAUTION → halve weight
    CLEAR → unchanged

    Returns (kept_picks, vetoed_picks).
    """
    kept, vetoed = [], []
    for pick in sized_picks:
        screen = screens.get(pick.ticker)
        if screen is None or screen.verdict == "CLEAR":
            kept.append(pick)
        elif screen.verdict == "CAUTION":
            pick.weight = round(pick.weight / 2, 4)
            kept.append(pick)
        else:
            vetoed.append(pick)
    return kept, vetoed
