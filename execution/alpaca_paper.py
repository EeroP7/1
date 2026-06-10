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


def place_basket(
    picks: "list[SizedPick]",
    portfolio_value: float,
    dry_run: bool = True,
    live: bool = False,
) -> list[OrderResult]:
    """
    Place fractional notional orders for each pick.

    Parameters
    ----------
    picks : sized picks from risk.sizing
    portfolio_value : total account equity in USD
    dry_run : if True, compute orders but do NOT submit
    live : if True, use live account (requires separate confirmation prompt)
    """
    if live:
        _confirm_live_trading()

    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    client = _get_client(live) if not dry_run else None

    results: list[OrderResult] = []
    for pick in picks:
        notional = round(pick.weight * portfolio_value, 2)
        if notional < 1.0:
            logger.debug("Skipping %s: notional %.2f < $1", pick.ticker, notional)
            continue

        if dry_run:
            logger.info(
                "[DRY RUN] Would BUY %s notional=$%.2f (weight=%.1f%%)",
                pick.ticker, notional, pick.weight * 100,
            )
            results.append(OrderResult(
                ticker=pick.ticker,
                order_id="dry_run",
                status="simulated",
                qty=0,
                notional=notional,
                side="buy",
            ))
        else:
            try:
                req = MarketOrderRequest(
                    symbol=pick.ticker,
                    notional=notional,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                )
                order = client.submit_order(req)
                results.append(OrderResult(
                    ticker=pick.ticker,
                    order_id=str(order.id),
                    status=str(order.status),
                    qty=float(order.qty or 0),
                    notional=notional,
                    side="buy",
                ))
                logger.info(
                    "Placed order %s for %s notional=$%.2f",
                    order.id, pick.ticker, notional,
                )
            except Exception as exc:
                logger.error("Order failed for %s: %s", pick.ticker, exc)
                results.append(OrderResult(
                    ticker=pick.ticker,
                    order_id="",
                    status="error",
                    qty=0,
                    notional=notional,
                    side="buy",
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
