"""
Downloads historical BTC/USDT 5M candles from Binance public API.
No API key required.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
import asyncio
import pandas as pd

BINANCE_REST = "https://api.binance.com"
KLINES_URL = f"{BINANCE_REST}/api/v3/klines"
CACHE_DIR = Path("models/data")
COLUMNS = ["open_time", "open", "high", "low", "close", "volume",
           "close_time", "quote_vol", "trades", "taker_buy_base",
           "taker_buy_quote", "ignore"]


async def _fetch_chunk(
    session: aiohttp.ClientSession,
    symbol: str,
    interval: str,
    start_ms: int,
    limit: int = 1000,
) -> list:
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "limit": limit,
    }
    for attempt in range(5):
        try:
            async with session.get(KLINES_URL, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                await asyncio.sleep(2 ** attempt)
        except Exception:
            await asyncio.sleep(2 ** attempt)
    return []


async def download_candles(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    days: int = 365,
    cache: bool = True,
) -> pd.DataFrame:
    """
    Download `days` worth of `interval` candles.
    Saves to models/data/<symbol>_<interval>.parquet for reuse.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{symbol}_{interval}_{days}d.parquet"

    if cache and cache_file.exists():
        print(f"Loading cached data from {cache_file}")
        return pd.read_parquet(cache_file)

    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = end_ms - days * 24 * 3600 * 1000

    print(f"Downloading {days} days of {symbol} {interval} candles from Binance...")
    all_rows = []

    async with aiohttp.ClientSession() as session:
        cursor = start_ms
        while cursor < end_ms:
            chunk = await _fetch_chunk(session, symbol, interval, cursor)
            if not chunk:
                break
            all_rows.extend(chunk)
            cursor = chunk[-1][0] + 1   # next candle after last
            # Respect Binance rate limit (1200 weight/min, each call = 1-2 weight)
            await asyncio.sleep(0.05)
            if len(all_rows) % 10000 == 0:
                print(f"  {len(all_rows):,} candles fetched...")

    print(f"Total candles: {len(all_rows):,}")
    df = pd.DataFrame(all_rows, columns=COLUMNS)
    df = df[["open_time", "open", "high", "low", "close", "volume"]].copy()
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df = df.set_index("open_time").sort_index().drop_duplicates()

    if cache:
        df.to_parquet(cache_file)
        print(f"Saved to {cache_file}")

    return df


def train_test_split(df: pd.DataFrame, test_ratio: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame]:
    split = int(len(df) * (1 - test_ratio))
    return df.iloc[:split], df.iloc[split:]
