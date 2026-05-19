"""
Builds the BTC market context document that MiroFish agents reason about.

MiroFish expects a plain-text or markdown "seed document" describing the
scenario.  We generate one fresh before each simulation run from the
latest Binance snapshot and kline history.
"""
import time
from datetime import datetime, timezone

from feeds.binance_ws import BtcSnapshot
from feeds.indicators import IndicatorSet


def build_context(snap: BtcSnapshot, ind: IndicatorSet) -> str:
    """
    Returns a markdown document describing the current BTC market state.
    Structured so that MiroFish agents can form opinions on short-term direction.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    mark = snap.mark_price
    spot = snap.price
    premium_pct = snap.mark_spot_spread * 100

    # Recent kline summary (last 10 candles)
    kline_lines = []
    for k in snap.klines[:10]:
        dt = datetime.fromtimestamp(k.open_time / 1000, tz=timezone.utc).strftime("%H:%M")
        direction = "▲" if k.close >= k.open else "▼"
        change = (k.close - k.open) / k.open * 100
        kline_lines.append(
            f"  {dt}  {direction} ${k.close:,.0f}  ({change:+.2f}%)  vol={k.volume:.1f}"
        )
    kline_block = "\n".join(kline_lines)

    # Trend summary
    ema_trend = "bullish" if ind.ema_9 > ind.ema_21 > ind.ema_50 else \
                "bearish" if ind.ema_9 < ind.ema_21 < ind.ema_50 else "mixed"
    macd_state = "positive (bullish)" if ind.macd_hist > 0 else "negative (bearish)"
    rsi_state = (
        "oversold (bullish signal)" if ind.rsi_14 < 30 else
        "overbought (bearish signal)" if ind.rsi_14 > 70 else
        f"neutral at {ind.rsi_14:.1f}"
    )
    bb_state = (
        "below lower band (oversold)" if spot < ind.bb_lower else
        "above upper band (overbought)" if spot > ind.bb_upper else
        f"{'above' if spot > ind.bb_mid else 'below'} midline ({ind.bb_pct_b:.2f} %B)"
    )
    flow_state = "buyers dominating" if snap.flow_ratio > 0.60 else \
                 "sellers dominating" if snap.flow_ratio < 0.40 else "balanced"
    funding_bias = "longs paying (bearish pressure)" if snap.funding_rate > 0.0002 else \
                   "shorts paying (bullish pressure)" if snap.funding_rate < -0.0002 else "neutral"

    return f"""# BTC/USDT Short-Term Market Analysis
Generated: {now}

## Current Prices
- Spot price:        ${spot:,.2f}
- Futures mark:      ${mark:,.2f}  ({premium_pct:+.3f}% premium)
- Funding rate:      {snap.funding_rate:.5f}  ({funding_bias})

## Order Book
- Best bid:          ${snap.bid:,.2f}  ({snap.bid_qty:.4f} BTC)
- Best ask:          ${snap.ask:,.2f}  ({snap.ask_qty:.4f} BTC)
- Order flow imbal:  {snap.order_flow_imbalance:+.3f}

## aggTrade Flow (last 10s)
- Buy volume:        {snap.agg_buy_vol:.3f} BTC
- Sell volume:       {snap.agg_sell_vol:.3f} BTC
- Flow ratio:        {snap.flow_ratio:.1%}  ({flow_state})

## Recent 5-Minute Candles
{kline_block}

## Technical Indicators
- RSI (14):          {ind.rsi_14:.1f}  — {rsi_state}
- StochRSI K/D:      {ind.stoch_rsi_k:.1f} / {ind.stoch_rsi_d:.1f}
- MACD histogram:    {ind.macd_hist:+.2f}  — {macd_state}
- EMA alignment:     {ema_trend}  (EMA9={ind.ema_9:,.0f}  EMA21={ind.ema_21:,.0f}  EMA50={ind.ema_50:,.0f})
- Bollinger Bands:   {bb_state}  (upper={ind.bb_upper:,.0f}  lower={ind.bb_lower:,.0f})
- VWAP:              ${ind.vwap:,.2f}  (price {'above' if spot > ind.vwap else 'below'})
- OBV delta:         {ind.obv:+.4f}
- Buy/sell ratio:    {ind.buy_sell_ratio:.1%}

## Simulation Requirement
You are a market analyst agent. Based on the data above, assess:
**Will the BTC/USDT price be HIGHER or LOWER at the close of the current
5-minute candle compared to its open price?**

Consider: momentum, order flow, futures premium, technical indicators,
and any divergences. Give a directional verdict (UP or DOWN) and a
confidence percentage (0-100%).
"""


def build_requirement(snap: BtcSnapshot) -> str:
    """Short simulation_requirement string sent alongside the seed doc."""
    direction = "up" if snap.flow_ratio > 0.5 else "down"
    return (
        f"Predict whether BTC/USDT price will go UP or DOWN over the next "
        f"5 minutes. Current price ${snap.price:,.0f}. "
        f"Recent flow suggests {direction}ward momentum. "
        f"Provide a probability (0-100%) and directional verdict."
    )
