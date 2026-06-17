"""
Daily pick list formatter and writer.

Output:
  - Terminal: formatted ranked list
  - picks.csv: appended row per pick
  - journal.csv: same schema + timestamp + realized-R tracking fields
  - Optional: webhook alert (Slack / Discord)
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from risk.sizing import SizedPick

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "output_data"))
PICKS_CSV = OUTPUT_DIR / "picks.csv"
JOURNAL_CSV = OUTPUT_DIR / "journal.csv"

PICKS_FIELDS = [
    "date", "ticker", "rank", "score", "entry_ref", "stop",
    "atr", "weight", "sector", "earnings_flag", "rationale",
]
JOURNAL_FIELDS = PICKS_FIELDS + [
    "screen_verdict", "screen_reason",
    "dd_leadership", "dd_narrative", "dd_macro", "dd_event_risk", "dd_key_risks",
    "exit_price", "exit_date", "realized_r", "model_or_discretionary",
]

_EARNINGS_WITHIN = 10   # flag if earnings within this many calendar days
_earnings_cache: dict[str, list] = {}  # ticker → list[date]


def _fetch_earnings_dates(ticker: str) -> list:
    """Fetch upcoming earnings dates from yfinance. Returns [] on any failure."""
    if ticker in _earnings_cache:
        return _earnings_cache[ticker]
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        dates = cal.get("Earnings Date", []) if isinstance(cal, dict) else []
        _earnings_cache[ticker] = list(dates)
        return _earnings_cache[ticker]
    except Exception as exc:
        logger.debug("Could not fetch earnings calendar for %s: %s", ticker, exc)
        _earnings_cache[ticker] = []
        return []


def _earnings_flag(ticker: str, as_of: date) -> str:
    """Returns earnings date string if within _EARNINGS_WITHIN days, else 'no earnings <Nd'."""
    from datetime import timedelta
    dates = _fetch_earnings_dates(ticker)
    cutoff = as_of + timedelta(days=_EARNINGS_WITHIN)
    upcoming = [d for d in dates if isinstance(d, date) and as_of <= d <= cutoff]
    if upcoming:
        nearest = min(upcoming)
        days_away = (nearest - as_of).days
        return f"⚠️ EARNINGS {nearest} ({days_away}d)"
    return f"no earnings <{_EARNINGS_WITHIN}d"


def _build_rationale(ticker: str, score: float, features_row: dict | None) -> str:
    """
    One-line rationale built from the highest-contributing features.
    Falls back to a generic string if no feature data supplied.
    """
    if not features_row:
        return f"composite score {score:.2f}"

    sorted_features = sorted(features_row.items(), key=lambda x: abs(x[1]), reverse=True)
    top = sorted_features[:2]
    parts = []
    for name, val in top:
        if "mom" in name and val > 0:
            parts.append(_humanize(name))
        elif "mean_rev" in name and val < -0.5:
            parts.append("mean-reversion setup")
        elif "dist_52w" in name and val > -0.05:
            parts.append("near 52w high")
        elif val > 0.5:
            parts.append(_humanize(name))
    return " + ".join(parts) if parts else f"composite score {score:.2f}"


def _humanize(feature_name: str) -> str:
    mapping = {
        "mom_1m": "1-mo momentum",
        "mom_3m": "3-mo momentum",
        "mom_6m": "6-mo momentum",
        "mom_12m_skip1m": "12-mo momentum",
        "vol_adj_trend": "vol-adj trend",
        "mean_rev_z20": "mean-reversion",
        "dist_52w_high": "near 52w high",
        "vol_trend": "rising volume",
        "price_range": "tight range",
    }
    return mapping.get(feature_name, feature_name.replace("_", " "))


def format_pick(pick: "SizedPick", rationale: str, earnings: str) -> str:
    """Single-line pick summary in the spec format."""
    return (
        f"{pick.ticker:6s} · rank {pick.rank:2d} · score {pick.score:.2f} · "
        f"buy ~{pick.entry_ref:.2f} · stop {pick.stop:.2f} ({pick.atr:.2f} ATR×2) · "
        f"weight {pick.weight:.0%} · {earnings} · why: {rationale}"
    )


def print_picks(
    picks: "list[SizedPick]",
    as_of: date | None = None,
    feature_rows: dict | None = None,
) -> None:
    """Print ranked pick list to stdout."""
    as_of = as_of or date.today()
    print(f"\n{'='*70}")
    print(f"  STOCK PICKS  —  {as_of}  (model output, not investment advice)")
    print(f"{'='*70}")
    for pick in picks:
        features_row = (feature_rows or {}).get(pick.ticker)
        rationale = _build_rationale(pick.ticker, pick.score, features_row)
        earnings = _earnings_flag(pick.ticker, as_of)
        print("  " + format_pick(pick, rationale, earnings))
    print(f"{'='*70}\n")


def write_picks(
    picks: "list[SizedPick]",
    as_of: date | None = None,
    feature_rows: dict | None = None,
    model: str = "model",
    screens: dict | None = None,
) -> None:
    """Append picks to picks.csv and journal.csv."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    as_of = as_of or date.today()

    rows = []
    for pick in picks:
        features_row = (feature_rows or {}).get(pick.ticker)
        rationale = _build_rationale(pick.ticker, pick.score, features_row)
        earnings = _earnings_flag(pick.ticker, as_of)
        rows.append({
            "date": as_of.isoformat(),
            "ticker": pick.ticker,
            "rank": pick.rank,
            "score": pick.score,
            "entry_ref": pick.entry_ref,
            "stop": pick.stop,
            "atr": pick.atr,
            "weight": pick.weight,
            "sector": pick.sector,
            "earnings_flag": earnings,
            "rationale": rationale,
        })

    _append_csv(PICKS_CSV, PICKS_FIELDS, rows)

    def _screen_fields(ticker: str) -> dict:
        s = (screens or {}).get(ticker)
        if s is None:
            return {"screen_verdict": "", "screen_reason": "",
                    "dd_leadership": "", "dd_narrative": "",
                    "dd_macro": "", "dd_event_risk": "", "dd_key_risks": ""}
        return {
            "screen_verdict": s.verdict,
            "screen_reason": s.reason,
            "dd_leadership": getattr(s, "leadership_score", ""),
            "dd_narrative": getattr(s, "narrative_score", ""),
            "dd_macro": getattr(s, "macro_score", ""),
            "dd_event_risk": getattr(s, "event_risk_score", ""),
            "dd_key_risks": " | ".join(getattr(s, "key_risks", [])),
        }

    journal_rows = [{**r, **_screen_fields(r["ticker"]),
                     "exit_price": "", "exit_date": "", "realized_r": "",
                     "model_or_discretionary": model}
                    for r in rows]
    _append_csv(JOURNAL_CSV, JOURNAL_FIELDS, journal_rows)
    logger.info("Wrote %d picks to %s and %s", len(picks), PICKS_CSV, JOURNAL_CSV)


def _append_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    write_header = not path.exists()
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def send_alert(picks: "list[SizedPick]", as_of: date | None = None) -> None:
    """POST picks summary to ALERT_WEBHOOK_URL if configured."""
    webhook = os.getenv("ALERT_WEBHOOK_URL", "")
    if not webhook:
        return

    as_of = as_of or date.today()
    lines = [f"*Stock Picks — {as_of}*"]
    for pick in picks[:5]:  # top 5 in alert
        lines.append(
            f"`{pick.ticker}` #{pick.rank}  score={pick.score:.2f}  "
            f"entry~{pick.entry_ref}  stop={pick.stop}  wt={pick.weight:.0%}"
        )
    text = "\n".join(lines)

    try:
        resp = requests.post(webhook, json={"text": text}, timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Alert webhook failed: %s", exc)


def send_email_alert(
    picks: "list[SizedPick]",
    as_of: "date | None" = None,
    equity: float | None = None,
    sold: list[str] | None = None,
    order_results: list | None = None,
    feature_rows: dict | None = None,
    screens: dict | None = None,
) -> None:
    """Send a daily trade signal email via Gmail SMTP.

    Required env vars (add as GitHub Secrets):
        GMAIL_USER        — your Gmail address (e.g. eerop20@gmail.com)
        GMAIL_APP_PASSWORD — Gmail app password (not your login password)

    Optional:
        ALERT_EMAIL       — recipient address; defaults to GMAIL_USER
    """
    sender = os.getenv("GMAIL_USER", "")
    password = os.getenv("GMAIL_APP_PASSWORD", "")
    if not sender or not password:
        logger.info("GMAIL_USER/GMAIL_APP_PASSWORD not set — email alert skipped.")
        return

    recipient = os.getenv("ALERT_EMAIL", sender)
    as_of = as_of or date.today()
    sold = sold or []
    order_results = order_results or []
    feature_rows = feature_rows or {}
    screens = screens or {}

    # ── build plain-text body ──────────────────────────────────────────────
    lines: list[str] = []
    lines.append(f"DAILY TRADE SIGNAL — {as_of}")
    lines.append("=" * 50)

    if equity is not None:
        lines.append(f"Account equity: ${equity:,.2f}  (paper)")
    lines.append("")

    # Sells
    if sold:
        lines.append(f"SOLD (rotated out):")
        for ticker in sold:
            lines.append(f"  ✖  {ticker}")
        lines.append("")

    # Buys / adjustments
    lines.append("CURRENT POSITIONS (fills at next open):")
    for pick in picks:
        earnings = _earnings_flag(pick.ticker, as_of)
        screen = screens.get(pick.ticker)
        verdict_tag = ""
        if screen and screen.verdict == "CAUTION":
            verdict_tag = "  ⚠️ CAUTION (weight halved)"
        elif screen and screen.verdict == "VETO":
            verdict_tag = "  ⛔ VETOED"

        # find matching order result
        order_tag = ""
        for r in order_results:
            if r.ticker == pick.ticker:
                if r.error:
                    order_tag = "  ❌ ORDER FAILED"
                elif hasattr(r, "side"):
                    order_tag = f"  → {r.side.upper()}"
                break

        lines.append(
            f"  #{pick.rank}  {pick.ticker:6s}"
            f"  entry ~${pick.entry_ref:.2f}"
            f"  stop ${pick.stop:.2f}"
            f"  weight {pick.weight:.0%}"
            f"{order_tag}{verdict_tag}"
        )
        if "EARNINGS" in earnings:
            lines.append(f"         ⚠️  {earnings}")
        rationale = _build_rationale(pick.ticker, pick.score, feature_rows.get(pick.ticker))
        lines.append(f"         why: {rationale}")

    lines.append("")
    lines.append("─" * 50)
    lines.append("Stops are ATR-based journal levels, not live Alpaca orders.")
    lines.append("This is paper trading — no real money at risk.")

    body = "\n".join(lines)

    # ── send via Gmail SMTP ────────────────────────────────────────────────
    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = f"📈 Trade Signal {as_of} — {len(picks)} positions"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)
        logger.info("Email alert sent to %s", recipient)
    except Exception as exc:
        logger.warning("Email alert failed: %s", exc)
