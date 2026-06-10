"""
AI news analyst — screens each pick's recent news via the Claude API.

The analyst can ONLY reduce risk, never add it:
    VETO    → drop the pick entirely (binary event imminent, scandal, earnings)
    CAUTION → halve the position weight
    CLEAR   → trade as the model intended

It never picks stocks, never increases weights, and never overrides the DSR
gate.  Its verdicts and rationale are journaled separately from the model's
so the overlay's value can be scored independently.

Requires ANTHROPIC_API_KEY in the environment.  Without it, screening is
skipped and every pick passes through as CLEAR (flagged "unscreened").
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from news.scanner import NewsItem

logger = logging.getLogger(__name__)

MODEL_ID = "claude-opus-4-8"


class Screening(BaseModel):
    verdict: str          # "VETO" | "CAUTION" | "CLEAR"
    reason: str           # one line, journaled
    earnings_risk: bool   # earnings/binary event within ~10 days suspected


@dataclass
class ScreenResult:
    ticker: str
    verdict: str
    reason: str
    earnings_risk: bool
    screened: bool        # False = no API key / API failure, passed through


SYSTEM_PROMPT = """You are a risk screener for a systematic momentum stock-picking model.
The model has already selected its picks; your ONLY job is to flag risks the
price-based model cannot see. You may never express bullishness or suggest
increasing a position.

For the given stock and its recent news headlines, return:
- verdict: "VETO" if there is an imminent binary event (earnings within ~10
  days, pending FDA/court/regulatory decision, fraud or accounting scandal,
  CEO departure, going-concern doubt, buyout rumor that pins the price).
  "CAUTION" if there is elevated uncertainty that warrants half size
  (analyst-day soon, sector-wide regulatory pressure, unresolved guidance cut).
  "CLEAR" otherwise. Most picks should be CLEAR — do not invent concerns.
- reason: one short sentence (max 15 words) usable in a trade journal.
- earnings_risk: true only if you see evidence earnings are within ~10 days.

Be conservative with VETO — it discards real model edge. Headlines being
merely negative is NOT a veto; momentum models buy pullbacks in strong names."""


def screen_picks(
    news_by_ticker: "dict[str, list[NewsItem]]",
) -> dict[str, ScreenResult]:
    """Screen each ticker's news. Returns {ticker: ScreenResult}."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set — news screening SKIPPED. "
            "All picks pass through unscreened."
        )
        return {
            t: ScreenResult(t, "CLEAR", "unscreened (no API key)", False, screened=False)
            for t in news_by_ticker
        }

    import anthropic

    client = anthropic.Anthropic()
    results: dict[str, ScreenResult] = {}

    for ticker, items in news_by_ticker.items():
        if not items:
            results[ticker] = ScreenResult(
                ticker, "CLEAR", "no recent news", False, screened=True
            )
            continue

        headlines = "\n".join(
            f"- [{n.created_at[:10]}] {n.headline}" + (f" — {n.summary[:200]}" if n.summary else "")
            for n in items[:10]
        )
        try:
            response = client.messages.parse(
                model=MODEL_ID,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Stock: {ticker}\n\nRecent news:\n{headlines}",
                }],
                output_format=Screening,
            )
            s = response.parsed_output
            verdict = s.verdict if s.verdict in ("VETO", "CAUTION", "CLEAR") else "CLEAR"
            results[ticker] = ScreenResult(
                ticker, verdict, s.reason, s.earnings_risk, screened=True
            )
            logger.info("Screen %s: %s — %s", ticker, verdict, s.reason)
        except Exception as exc:
            logger.warning("Screening failed for %s (%s) — passing through.", ticker, exc)
            results[ticker] = ScreenResult(
                ticker, "CLEAR", f"screening error: {type(exc).__name__}", False, screened=False
            )

    return results


def apply_screening(
    sized_picks: list,          # list[SizedPick]
    screens: dict[str, ScreenResult],
) -> tuple[list, list]:
    """
    Apply verdicts to sized picks.

    Returns (kept_picks, vetoed_picks).  CAUTION halves the weight; VETO
    removes the pick.  Weights are NOT renormalized upward — vetoed capital
    stays in cash (the conservative choice).
    """
    kept, vetoed = [], []
    for pick in sized_picks:
        screen = screens.get(pick.ticker)
        if screen is None or screen.verdict == "CLEAR":
            kept.append(pick)
        elif screen.verdict == "CAUTION":
            pick.weight = round(pick.weight / 2, 4)
            kept.append(pick)
        else:  # VETO
            vetoed.append(pick)
    return kept, vetoed
