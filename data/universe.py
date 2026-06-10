"""
Universe definition and data loading.

⚠️  SURVIVORSHIP BIAS WARNING: This module uses the *current* S&P 500
constituent list, not a point-in-time membership database.  Stocks that were
deleted, delisted, merged, or went bankrupt before today are absent.  Any
backtest that uses this universe will therefore be optimistic — sometimes
severely so.  All backtest reports flag this explicitly.  Treat all in-sample
and out-of-sample Sharpe ratios as upper bounds.

To mitigate: use the watchlist override to supply your own curated, point-in-
time universe file.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static S&P 500 constituent list (current as of mid-2025 — NOT point-in-time)
# ---------------------------------------------------------------------------
_SP500_TICKERS: list[str] = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "META", "TSLA", "AVGO",
    "BRK.B", "JPM", "LLY", "UNH", "V", "XOM", "MA", "HD", "PG", "COST",
    "JNJ", "ABBV", "NFLX", "BAC", "MRK", "CVX", "CRM", "WMT", "ORCL", "PEP",
    "AMD", "ACN", "LIN", "TMO", "ADBE", "TXN", "MCD", "CSCO", "QCOM", "GE",
    "DHR", "ABT", "INTU", "PFE", "IBM", "AMGN", "NEE", "RTX", "AMAT", "PM",
    "CMCSA", "HON", "VZ", "SPGI", "ISRG", "GILD", "GS", "T", "LOW", "CAT",
    "UNP", "AXP", "MS", "ETN", "SYK", "BKNG", "BLK", "UBER", "VRTX", "C",
    "DE", "ADI", "LRCX", "MMC", "REGN", "MDT", "MU", "PANW", "PLD", "CB",
    "BSX", "ADP", "KKR", "CI", "SCHW", "SO", "KLAC", "SBUX", "ZTS", "MDLZ",
    "CMG", "DUK", "TJX", "BMY", "ICE", "INTC", "WM", "CEG", "SNPS", "EMR",
    "MCO", "AON", "GD", "CL", "NOC", "CDNS", "ITW", "FCX", "EOG", "SLB",
    "USB", "PNC", "MAR", "TT", "ELV", "HCA", "WFC", "NSC", "FDX", "APH",
    "PYPL", "CTAS", "OKE", "MSI", "MPC", "PSA", "ORLY", "AIG", "ECL", "HES",
    "COF", "WELL", "GWW", "MMM", "KMB", "TDG", "AEP", "NEM", "SRE", "AFL",
    "COP", "PCAR", "ROST", "TFC", "VLO", "F", "PAYX", "GM", "KR", "EW",
    "CARR", "DLR", "OXY", "BK", "AME", "MCHP", "ON", "IDXX", "FAST", "LHX",
    "FANG", "HAL", "URI", "PCG", "VRSK", "D", "DD", "KDP", "HLT", "STZ",
    "IR", "DXCM", "MNST", "GEHC", "O", "CMI", "A", "PPG", "XEL", "CPRT",
    "PRU", "CTVA", "GPC", "AWK", "KEYS", "GLW", "ACGL", "WTW", "ODFL",
    "ALL", "SYF", "TROW", "MTD", "PWR", "ROK", "CDW", "EXC", "ED", "ROP",
    "BDX", "CCI", "OTIS", "FITB", "IQV", "HPQ", "NDAQ", "ADM", "WAB",
    "EBAY", "DHI", "VMC", "LEN", "MLM", "CTSH", "RF", "HBAN", "ETR",
    "DOV", "CBRE", "TTWO", "PH", "DG", "DECK", "BR", "PODD", "ANSS",
    "MPWR", "ZBRA", "NDSN", "TRMB", "JBHT", "CFG", "WBA", "SWKS",
    "HSY", "CHD", "EFX", "EXAS", "ENPH", "FSLR", "NRG",
]

# Sector mapping for concentration caps (simplified GICS sectors)
SECTOR_MAP: dict[str, str] = {
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "AVGO": "Technology", "AMD": "Technology", "TXN": "Technology",
    "QCOM": "Technology", "AMAT": "Technology", "LRCX": "Technology",
    "ADBE": "Technology", "CRM": "Technology", "ORCL": "Technology",
    "INTU": "Technology", "IBM": "Technology", "CSCO": "Technology",
    "ACN": "Technology", "ADI": "Technology", "KLAC": "Technology",
    "SNPS": "Technology", "CDNS": "Technology", "INTC": "Technology",
    "MSI": "Technology", "APH": "Technology", "MCHP": "Technology",
    "ON": "Technology", "KEYS": "Technology", "GLW": "Technology",
    "CDW": "Technology", "HPQ": "Technology", "ANSS": "Technology",
    "MPWR": "Technology", "ZBRA": "Technology", "SWKS": "Technology",
    "GOOGL": "Communication", "GOOG": "Communication", "META": "Communication",
    "NFLX": "Communication", "VZ": "Communication", "T": "Communication",
    "CMCSA": "Communication", "TTWO": "Communication",
    "AMZN": "ConsumerDiscretionary", "TSLA": "ConsumerDiscretionary",
    "HD": "ConsumerDiscretionary", "MCD": "ConsumerDiscretionary",
    "BKNG": "ConsumerDiscretionary", "UBER": "ConsumerDiscretionary",
    "LOW": "ConsumerDiscretionary", "SBUX": "ConsumerDiscretionary",
    "CMG": "ConsumerDiscretionary", "TJX": "ConsumerDiscretionary",
    "MAR": "ConsumerDiscretionary", "ORLY": "ConsumerDiscretionary",
    "ROST": "ConsumerDiscretionary", "DHI": "ConsumerDiscretionary",
    "LEN": "ConsumerDiscretionary", "DG": "ConsumerDiscretionary",
    "DECK": "ConsumerDiscretionary", "EBAY": "ConsumerDiscretionary",
    "WMT": "ConsumerStaples", "PG": "ConsumerStaples",
    "COST": "ConsumerStaples", "PEP": "ConsumerStaples",
    "KO": "ConsumerStaples", "PM": "ConsumerStaples",
    "MDLZ": "ConsumerStaples", "CL": "ConsumerStaples",
    "KMB": "ConsumerStaples", "KR": "ConsumerStaples",
    "WBA": "ConsumerStaples", "ADM": "ConsumerStaples",
    "STZ": "ConsumerStaples", "KDP": "ConsumerStaples",
    "HSY": "ConsumerStaples", "CHD": "ConsumerStaples",
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
    "EOG": "Energy", "SLB": "Energy", "MPC": "Energy",
    "VLO": "Energy", "OXY": "Energy", "HAL": "Energy",
    "FANG": "Energy", "HES": "Energy", "NRG": "Energy", "FSLR": "Energy",
    "JPM": "Financials", "BAC": "Financials", "V": "Financials",
    "MA": "Financials", "GS": "Financials", "MS": "Financials",
    "BLK": "Financials", "AXP": "Financials", "C": "Financials",
    "SCHW": "Financials", "CB": "Financials", "MMC": "Financials",
    "ICE": "Financials", "USB": "Financials", "PNC": "Financials",
    "TFC": "Financials", "COF": "Financials", "AIG": "Financials",
    "AFL": "Financials", "BK": "Financials", "KKR": "Financials",
    "SPGI": "Financials", "MCO": "Financials", "AON": "Financials",
    "PRU": "Financials", "TROW": "Financials", "SYF": "Financials",
    "FITB": "Financials", "RF": "Financials", "HBAN": "Financials",
    "CFG": "Financials", "ACGL": "Financials", "WTW": "Financials",
    "UNH": "Healthcare", "LLY": "Healthcare", "JNJ": "Healthcare",
    "MRK": "Healthcare", "ABBV": "Healthcare", "TMO": "Healthcare",
    "ABT": "Healthcare", "DHR": "Healthcare", "PFE": "Healthcare",
    "AMGN": "Healthcare", "ISRG": "Healthcare", "GILD": "Healthcare",
    "VRTX": "Healthcare", "REGN": "Healthcare", "MDT": "Healthcare",
    "BSX": "Healthcare", "ZTS": "Healthcare", "BMY": "Healthcare",
    "CI": "Healthcare", "ELV": "Healthcare", "HCA": "Healthcare",
    "EW": "Healthcare", "IDXX": "Healthcare", "DXCM": "Healthcare",
    "GEHC": "Healthcare", "IQV": "Healthcare", "BDX": "Healthcare",
    "MTD": "Healthcare", "PODD": "Healthcare", "EXAS": "Healthcare",
    "GE": "Industrials", "HON": "Industrials", "CAT": "Industrials",
    "UNP": "Industrials", "DE": "Industrials", "ETN": "Industrials",
    "RTX": "Industrials", "GD": "Industrials", "NOC": "Industrials",
    "LHX": "Industrials", "FDX": "Industrials", "NSC": "Industrials",
    "EMR": "Industrials", "ITW": "Industrials", "CTAS": "Industrials",
    "PCAR": "Industrials", "CMI": "Industrials", "WM": "Industrials",
    "CARR": "Industrials", "TDG": "Industrials", "AME": "Industrials",
    "GWW": "Industrials", "FAST": "Industrials", "URI": "Industrials",
    "VRSK": "Industrials", "IR": "Industrials", "CPRT": "Industrials",
    "ODFL": "Industrials", "ROK": "Industrials", "PWR": "Industrials",
    "WAB": "Industrials", "VMC": "Industrials", "MLM": "Industrials",
    "DOV": "Industrials", "PH": "Industrials", "JBHT": "Industrials",
    "NDSN": "Industrials", "TRMB": "Industrials", "BR": "Industrials",
    "LIN": "Materials", "FCX": "Materials", "NEM": "Materials",
    "PPG": "Materials", "DD": "Materials", "CTVA": "Materials",
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "AEP": "Utilities", "SRE": "Utilities", "XEL": "Utilities",
    "D": "Utilities", "CEG": "Utilities", "PCG": "Utilities",
    "ETR": "Utilities", "ED": "Utilities", "AWK": "Utilities",
    "EXC": "Utilities", "ENPH": "Utilities",
    "PLD": "RealEstate", "AMT": "RealEstate", "CCI": "RealEstate",
    "WELL": "RealEstate", "PSA": "RealEstate", "DLR": "RealEstate",
    "O": "RealEstate", "CBRE": "RealEstate", "EFX": "Industrials",
    "F": "ConsumerDiscretionary", "GM": "ConsumerDiscretionary",
    "PAYX": "Technology", "ADP": "Technology",
    "OKE": "Energy", "PYPL": "Technology",
}


@dataclass
class UniverseConfig:
    min_price: float = 5.0
    min_adv: float = 1_000_000        # minimum average dollar volume
    adv_lookback: int = 20            # trading days for ADV calculation
    tickers: list[str] = field(default_factory=list)
    point_in_time: bool = False       # always False for this static list


@dataclass
class PriceData:
    """OHLCV data for the universe, adjusted for splits/dividends."""
    open: pd.DataFrame      # date x ticker
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    universe: list[str]     # tickers that passed liquidity filter
    config: UniverseConfig
    survivorship_warning: str = (
        "⚠️  SURVIVORSHIP BIAS: Universe is current S&P 500 constituents only. "
        "Delisted/bankrupt/merged names are excluded. Backtests are OPTIMISTIC."
    )


def load_universe(
    config: UniverseConfig | None = None,
    start: date | None = None,
    end: date | None = None,
) -> PriceData:
    """
    Load adjusted OHLCV data for the universe.

    Uses Alpaca markets data (Adjustment.ALL) when credentials are present;
    falls back to a synthetic dataset for offline/CI use.

    ⚠️  SURVIVORSHIP BIAS: see module docstring.
    """
    if config is None:
        config = UniverseConfig()

    if not config.tickers:
        config.tickers = list(_SP500_TICKERS)

    end = end or date.today()
    # need extra history for momentum features (252 days lookback)
    start = start or (end - timedelta(days=365 * 3))

    logger.warning(
        "⚠️  SURVIVORSHIP BIAS: loading current-only universe. "
        "Backtest results are optimistic."
    )

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if api_key and secret_key:
        return _load_from_alpaca(config, start, end, api_key, secret_key)
    else:
        logger.warning(
            "No Alpaca credentials found (ALPACA_API_KEY / ALPACA_SECRET_KEY). "
            "Using synthetic data. Set credentials in .env for real data."
        )
        return _make_synthetic(config, start, end)


def _load_from_alpaca(
    config: UniverseConfig,
    start: date,
    end: date,
    api_key: str,
    secret_key: str,
) -> PriceData:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import Adjustment

    client = StockHistoricalDataClient(api_key, secret_key)

    # batch into groups of 100 to avoid hitting query limits
    tickers = config.tickers
    batch_size = 100
    all_bars: list[pd.DataFrame] = []

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        req = StockBarsRequest(
            symbol_or_symbols=batch,
            timeframe=TimeFrame.Day,
            start=datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc),
            end=datetime.combine(end, datetime.min.time()).replace(tzinfo=timezone.utc),
            adjustment=Adjustment.ALL,
        )
        bars = client.get_stock_bars(req).df
        all_bars.append(bars)
        logger.debug("Loaded %d tickers (%d/%d)", len(batch), i + len(batch), len(tickers))

    df = pd.concat(all_bars)
    df.index.names = ["ticker", "timestamp"]
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date

    def _pivot(col: str) -> pd.DataFrame:
        return df.pivot_table(index="date", columns="ticker", values=col, aggfunc="last")

    prices = PriceData(
        open=_pivot("open"),
        high=_pivot("high"),
        low=_pivot("low"),
        close=_pivot("close"),
        volume=_pivot("volume"),
        universe=[],
        config=config,
    )
    prices.universe = _apply_liquidity_filter(prices, config)
    return prices


def _apply_liquidity_filter(prices: PriceData, config: UniverseConfig) -> list[str]:
    """Return tickers that pass price and average-dollar-volume filters."""
    close = prices.close
    volume = prices.volume

    last_close = close.iloc[-1]
    adv = (close * volume).iloc[-config.adv_lookback :].mean()

    passed = [
        t for t in close.columns
        if t in last_close.index
        and last_close[t] >= config.min_price
        and adv.get(t, 0) >= config.min_adv
    ]
    dropped = set(close.columns) - set(passed)
    if dropped:
        logger.info("Liquidity filter removed %d tickers: %s", len(dropped), dropped)
    return passed


def _make_synthetic(
    config: UniverseConfig, start: date, end: date
) -> PriceData:
    """Generate synthetic OHLCV data for testing without real credentials."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(start=start, end=end)
    tickers = config.tickers[:50]  # keep small for speed

    n_dates, n_tickers = len(dates), len(tickers)
    log_returns = rng.normal(0.0003, 0.015, size=(n_dates, n_tickers))
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(log_returns, axis=0)),
        index=dates,
        columns=tickers,
    )
    close.index = close.index.date

    spread = rng.uniform(0.002, 0.01, size=(n_dates, n_tickers))
    high = close * (1 + spread)
    low = close * (1 - spread)
    open_ = close * (1 + rng.normal(0, 0.005, size=(n_dates, n_tickers)))
    volume = pd.DataFrame(
        rng.integers(500_000, 10_000_000, size=(n_dates, n_tickers)).astype(float),
        index=close.index,
        columns=tickers,
    )

    prices = PriceData(
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        universe=tickers,
        config=config,
    )
    return prices


def get_sector(ticker: str) -> str:
    return SECTOR_MAP.get(ticker, "Unknown")
