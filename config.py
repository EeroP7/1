import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Binance
    BINANCE_WS_URL: str = "wss://stream.binance.com:9443/ws"
    BINANCE_REST_URL: str = "https://api.binance.com"
    BINANCE_SYMBOL: str = "BTCUSDT"
    KLINE_INTERVAL: str = "5m"

    # Polymarket CLOB
    POLYMARKET_HOST: str = "https://clob.polymarket.com"
    POLYMARKET_PRIVATE_KEY: str = field(default_factory=lambda: os.getenv("POLYMARKET_PRIVATE_KEY", ""))
    POLYMARKET_API_KEY: str = field(default_factory=lambda: os.getenv("POLYMARKET_API_KEY", ""))
    POLYMARKET_API_SECRET: str = field(default_factory=lambda: os.getenv("POLYMARKET_API_SECRET", ""))
    POLYMARKET_API_PASSPHRASE: str = field(default_factory=lambda: os.getenv("POLYMARKET_API_PASSPHRASE", ""))
    # BTC UP/DOWN 5MIN market condition IDs (UP = YES on price increase)
    MARKET_CONDITION_UP: str = field(default_factory=lambda: os.getenv("MARKET_CONDITION_UP", ""))
    MARKET_CONDITION_DOWN: str = field(default_factory=lambda: os.getenv("MARKET_CONDITION_DOWN", ""))

    # CryptoQuant
    CRYPTOQUANT_API_KEY: str = field(default_factory=lambda: os.getenv("CRYPTOQUANT_API_KEY", ""))

    # Strategy thresholds
    LAG_THRESHOLD: float = 0.003       # 0.3% CLOB lag vs spot to trigger
    MIN_CONFIDENCE: float = 0.65       # Mirofish cluster confidence floor
    EXECUTION_TIMEOUT_MS: int = 100    # Hard execution deadline

    # Risk controls
    PER_TRADE_RISK: float = 0.005      # 0.5% of portfolio per trade
    DAILY_CAP: float = 0.02            # 2% daily P&L cap (stop trading at +2%)
    HARD_STOP: float = -0.004          # -0.4% hard stop loss

    # Mirofish force-graph
    MIROFISH_NODES: int = 100
    MIROFISH_EDGES: int = 180
    MIROFISH_ITERATIONS: int = 60      # Force simulation steps per tick
    CONVERGENCE_THRESHOLD: float = 0.68  # Cluster separation score to trade

    # Operational
    TICK_INTERVAL_MS: int = 250        # Main loop tick (4x per second)
    DRY_RUN: bool = field(default_factory=lambda: os.getenv("DRY_RUN", "true").lower() == "true")
