"""
Paper trading execution via Alpaca.

⚠️  This module auto-places orders in Alpaca PAPER only.
    Live trading requires per-order explicit approval (confirmed via prompt).
    Never call place_basket() with live=True without reading the confirmation.

Environment variables required:
    ALPACA_API_KEY      — paper account key
    ALPACA_SECRET_KEY   — paper account secret
    ALPACA_BASE_URL     — https://paper-api.alpaca.markets  (default)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from risk.sizing import SizedPick

logger = logging.getLogger(__name__)

PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL = "https://api.alpaca.markets"


@dataclass
class OrderResult:
    ticker: str
    order_id: str
    status: str
    qty: float
    notional: float | None
    side: str
    error: str | None = None


def _get_client(live: bool = False):
    from alpaca.trading.client import TradingClient

    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise EnvironmentError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in the environment."
        )
    return TradingClient(api_key, secret_key, paper=not live)


def get_account(live: bool = False) -> dict:
    client = _get_client(live)
    acct = client.get_account()
    return {
        "equity": float(acct.equity),
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
    }


def get_positions(live: bool = False) -> dict[str, float]:
    """Current open positions as {symbol: market_value_usd}."""
    client = _get_client(live)
    return {p.symbol: float(p.market_value) for p in client.get_all_positions()}


def rotate_out(
    picks: "list[SizedPick]",
    dry_run: bool = True,
    live: bool = False,
) -> list[str]:
    """Close every open position whose symbol is not in the pick list.

    Returns the list of symbols closed. Sells are submitted before buys so the
    freed capital funds the new basket at the next open.
    """
    if live:
        _confirm_live_trading()

    keep = {p.ticker for p in picks}
    try:
        positions = get_positions(live)
    except Exception as exc:
        logger.error("Could not fetch positions for rotation: %s", exc)
        return []

    closed: list[str] = []
    for symbol, mv in positions.items():
        if symbol in keep:
            continue
        if dry_run:
            logger.info("[DRY RUN] Would SELL %s (market value $%.2f)", symbol, mv)
            closed.append(symbol)
            continue
        try:
            client = _get_client(live)
            client.close_position(symbol)
            logger.info("Closed position %s (market value $%.2f)", symbol, mv)
            closed.append(symbol)
        except Exception as exc:
            logger.error("Failed to close %s: %s", symbol, exc)
    return closed


def place_basket(
    picks: "list[SizedPick]",
    portfolio_value: float,
    dry_run: bool = True,
    live: bool = False,
    current_positions: dict[str, float] | None = None,
) -> list[OrderResult]:
    """
    Place fractional notional orders for each pick.

    Parameters
    ----------
    picks : sized picks from risk.sizing
    portfolio_value : total account equity in USD
    dry_run : if True, compute orders but do NOT submit
    live : if True, use live account (requires separate confirmation prompt)
    current_positions : {symbol: market_value} of holdings; when given, only
        the difference between target and held value is traded (delta orders)
    """
    if live:
        _confirm_live_trading()

    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    client = _get_client(live) if not dry_run else None
    held = current_positions or {}

    results: list[OrderResult] = []
    for pick in picks:
        target = round(pick.weight * portfolio_value, 2)
        delta = round(target - held.get(pick.ticker, 0.0), 2)
        if abs(delta) < 1.0:
            logger.debug("Skipping %s: delta %.2f < $1", pick.ticker, delta)
            continue
        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        notional = abs(delta)

        if dry_run:
            logger.info(
                "[DRY RUN] Would %s %s notional=$%.2f (target weight=%.1f%%)",
                side.name, pick.ticker, notional, pick.weight * 100,
            )
            results.append(OrderResult(
                ticker=pick.ticker,
                order_id="dry_run",
                status="simulated",
                qty=0,
                notional=notional,
                side=side.name.lower(),
            ))
        else:
            try:
                req = MarketOrderRequest(
                    symbol=pick.ticker,
                    notional=notional,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )
                order = client.submit_order(req)
                results.append(OrderResult(
                    ticker=pick.ticker,
                    order_id=str(order.id),
                    status=str(order.status),
                    qty=float(order.qty or 0),
                    notional=notional,
                    side=side.name.lower(),
                ))
                logger.info(
                    "Placed %s order %s for %s notional=$%.2f",
                    side.name, order.id, pick.ticker, notional,
                )
            except Exception as exc:
                logger.error("Order failed for %s: %s", pick.ticker, exc)
                results.append(OrderResult(
                    ticker=pick.ticker,
                    order_id="",
                    status="error",
                    qty=0,
                    notional=notional,
                    side=side.name.lower(),
                    error=str(exc),
                ))

    return results


def close_all_positions(dry_run: bool = True, live: bool = False) -> None:
    """Liquidate all open positions (kill switch)."""
    if live:
        _confirm_live_trading()
    if dry_run:
        logger.info("[DRY RUN] Would close all positions.")
        return
    client = _get_client(live)
    client.close_all_positions(cancel_orders=True)
    logger.info("All positions closed.")


def _confirm_live_trading() -> None:
    """Raise unless the user explicitly confirms live trading."""
    print("\n⚠️  WARNING: live=True will place REAL orders in your live account.")
    answer = input("Type 'I CONFIRM LIVE TRADING' to proceed: ")
    if answer.strip() != "I CONFIRM LIVE TRADING":
        raise RuntimeError("Live trading not confirmed. Aborting.")
