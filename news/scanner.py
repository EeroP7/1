"""
News scanner — fetch recent news per ticker from the Alpaca News API.

Free with any Alpaca account; uses the same ALPACA_API_KEY / ALPACA_SECRET_KEY.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

NEWS_URL = "https://data.alpaca.markets/v1beta1/news"


@dataclass
class NewsItem:
    headline: str
    summary: str
    source: str
    created_at: str
    symbols: list[str] = field(default_factory=list)


def fetch_news(
    tickers: list[str],
    lookback_days: int = 5,
    limit_per_ticker: int = 10,
) -> dict[str, list[NewsItem]]:
    """
    Return {ticker: [NewsItem, ...]} for recent news.
    Returns empty lists on API failure — news screening degrades gracefully.
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        logger.warning("No Alpaca credentials — skipping news fetch.")
        return {t: [] for t in tickers}

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
    }
    start = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

    result: dict[str, list[NewsItem]] = {}
    for ticker in tickers:
        try:
            resp = requests.get(
                NEWS_URL,
                headers=headers,
                params={
                    "symbols": ticker,
                    "start": start,
                    "limit": limit_per_ticker,
                    "sort": "desc",
                },
                timeout=10,
            )
            resp.raise_for_status()
            items = resp.json().get("news", [])
            result[ticker] = [
                NewsItem(
                    headline=n.get("headline", ""),
                    summary=n.get("summary", ""),
                    source=n.get("source", ""),
                    created_at=n.get("created_at", ""),
                    symbols=n.get("symbols", []),
                )
                for n in items
            ]
            logger.debug("Fetched %d news items for %s", len(result[ticker]), ticker)
        except Exception as exc:
            logger.warning("News fetch failed for %s: %s", ticker, exc)
            result[ticker] = []

    return result
