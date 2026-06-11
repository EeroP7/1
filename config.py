import os
from dotenv import load_dotenv

load_dotenv()

# ── Polymarket credentials ────────────────────────────────────────────────────
POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY", "")
POLY_API_KEY     = os.getenv("POLY_API_KEY", "")
POLY_API_SECRET  = os.getenv("POLY_API_SECRET", "")
POLY_PASSPHRASE  = os.getenv("POLY_PASSPHRASE", "")
POLY_HOST        = os.getenv("POLY_HOST", "https://clob.polymarket.com")
POLY_CHAIN_ID    = int(os.getenv("POLY_CHAIN_ID", "137"))  # Polygon mainnet

# ── Binance WebSocket ─────────────────────────────────────────────────────────
BINANCE_WS_BASE       = "wss://stream.binance.com:9443/stream"
BINANCE_FUTURES_WS    = "wss://fstream.binance.com/stream"   # perpetual futures
BINANCE_REST          = "https://api.binance.com"
BINANCE_FUTURES_REST  = "https://fapi.binance.com"
BTC_SYMBOL       = "btcusdt"
KLINE_INTERVAL   = "5m"
KLINE_LIMIT      = 60        # history candles to seed indicators
DEPTH_LEVELS     = 5         # order book depth levels to track
AGG_TRADE_WINDOW = 10        # seconds of aggTrade flow to accumulate

# ── Signal / force-graph ──────────────────────────────────────────────────────
GRAPH_NODES      = 100
GRAPH_EDGES      = 180
CONVERGENCE_THRESHOLD = 0.65  # cluster dominance ratio to trigger signal
MIN_SIGNAL_NODES = 12         # minimum active nodes before trusting signal

# ── Arbitrage edge detection ──────────────────────────────────────────────────
LAG_THRESHOLD    = 0.003      # 0.3% spot-vs-CLOB lag to enter
EDGE_EXPIRE_MS   = 80         # discard edge if older than 80ms

# ── Risk controls ─────────────────────────────────────────────────────────────
STARTING_BALANCE = float(os.getenv("STARTING_BALANCE", "1000"))
PER_TRADE_RISK   = float(os.getenv("PER_TRADE_RISK", "0.005"))  # fraction of balance per arb trade
DAILY_CAP_RISK   = float(os.getenv("DAILY_CAP_RISK", "0.02"))   # halt after this daily drawdown
HARD_STOP        = -0.004     # -0.4% unrealised loss → exit immediately
MIN_LIQUIDITY    = 200        # minimum $200 on best bid/ask before entering
MAX_SPREAD       = 0.015      # skip if spread > 1.5%

# ── Execution ─────────────────────────────────────────────────────────────────
ORDER_SIDE_YES   = "BUY"      # YES = BTC goes UP in the 5min window
ORDER_SIDE_NO    = "BUY"      # NO  = BTC goes DOWN
SLIPPAGE_LIMIT   = 0.005      # max 0.5% slippage on fill price

# ── MiroFish swarm intelligence ───────────────────────────────────────────────
# Run `npm run dev` inside the cloned 666ghj/MiroFish repo first.
# Set MIROFISH_ENABLED=false to run without MiroFish (force-graph only).
MIROFISH_HOST          = os.getenv("MIROFISH_HOST", "http://localhost:5001")
MIROFISH_ENABLED       = os.getenv("MIROFISH_ENABLED", "true").lower() == "true"
MIROFISH_REFRESH_MIN   = int(os.getenv("MIROFISH_REFRESH_MIN", "15"))  # re-run every N minutes
MIROFISH_AGENT_COUNT   = int(os.getenv("MIROFISH_AGENT_COUNT", "500"))
MIROFISH_MIN_CONFIDENCE = 0.60   # minimum swarm confidence to allow trading
MIROFISH_LLM_API_KEY   = os.getenv("LLM_API_KEY", "")   # same key as MiroFish .env

# ── Copy trading ──────────────────────────────────────────────────────────────
POLY_DATA_API          = "https://data-api.polymarket.com"
COPY_ENABLED           = os.getenv("COPY_ENABLED", "true").lower() == "true"
COPY_TOP_N             = int(os.getenv("COPY_TOP_N", "20"))       # wallets to track
COPY_LEADERBOARD_WINDOW = "ALL"   # DAY / WEEK / MONTH / ALL
COPY_POLL_INTERVAL     = 15       # seconds between activity polls per wallet
COPY_LEADERBOARD_REFRESH = 3600   # re-fetch leaderboard every hour
COPY_RISK_PER_TRADE    = float(os.getenv("COPY_RISK_PER_TRADE", "0.003"))  # fraction of balance per copy
COPY_MIN_TRADE_USD     = float(os.getenv("COPY_MIN_TRADE_USD", "20"))      # ignore whale trades smaller than this
COPY_MAX_TRADE_USD     = float(os.getenv("COPY_MAX_TRADE_USD", "500"))     # hard cap per copied trade
COPY_MARKET_COOLDOWN   = 300      # don't copy same market twice within 5 min
