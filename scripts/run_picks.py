#!/usr/bin/env python3
"""
run_picks.py — generate today's stock picks and optionally place them.

Usage:
    python scripts/run_picks.py --dry-run           # generate picks, place nothing
    python scripts/run_picks.py --execute           # place basket in Alpaca paper
    python scripts/run_picks.py --validate          # run full walk-forward first
    python scripts/run_picks.py --kill-switch       # close all positions in paper account

Environment:
    See .env.example for required / optional variables.

Kill switch:
    python scripts/run_picks.py --kill-switch
    (closes all open positions in paper account; add --live for live account)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

# Make package importable without install
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("run_picks")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Daily stock pick generator")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Generate picks without placing any orders (default)")
    p.add_argument("--execute", action="store_true",
                   help="Place basket in Alpaca paper account")
    p.add_argument("--validate", action="store_true",
                   help="Run walk-forward validation before generating picks")
    p.add_argument("--kill-switch", action="store_true",
                   help="Close all open positions immediately")
    p.add_argument("--live", action="store_true",
                   help="⚠️  Use live Alpaca account (requires confirmation)")
    p.add_argument("--top-n", type=int, default=int(os.getenv("TOP_N", "10")))
    p.add_argument("--min-price", type=float, default=float(os.getenv("MIN_PRICE", "5")))
    p.add_argument("--min-adv", type=float, default=float(os.getenv("MIN_ADV", "1000000")))
    p.add_argument("--max-weight", type=float, default=float(os.getenv("MAX_WEIGHT", "0.15")))
    p.add_argument("--sector-cap", type=float, default=float(os.getenv("SECTOR_CAP", "0.30")))
    p.add_argument("--dsr-threshold", type=float, default=float(os.getenv("DSR_THRESHOLD", "0.95")))
    p.add_argument("--rebalance", default=os.getenv("REBALANCE_FREQ", "W"),
                   choices=["D", "W", "M", "ME"])
    return p.parse_args()


def main() -> None:
    args = parse_args()
    today = date.today()

    # --- Kill switch ---
    if args.kill_switch:
        from execution.alpaca_paper import close_all_positions
        close_all_positions(dry_run=not args.execute, live=args.live)
        return

    print(f"\nStock Pick System  —  {today}")
    print("⚠️  SURVIVORSHIP BIAS: Universe is current S&P 500 only. "
          "Backtest results are optimistic.\n")

    # --- Load universe ---
    logger.info("Loading universe...")
    from data.universe import UniverseConfig, load_universe
    uni_config = UniverseConfig(
        min_price=args.min_price,
        min_adv=args.min_adv,
    )
    prices = load_universe(config=uni_config)
    logger.info("Universe: %d tickers after liquidity filter", len(prices.universe))

    # --- Compute features ---
    logger.info("Computing features...")
    import pandas as pd
    from features.library import compute_features, atr

    features = compute_features(prices, normalize=True)
    # Drop dates with mostly NaN (initial feature warmup period)
    count_series = [df.count(axis=1) for df in features.values()]
    min_valid = count_series[0].copy()
    for s in count_series[1:]:
        min_valid = min_valid.where(min_valid <= s, s)
    threshold = len(prices.universe) * 0.5
    valid_dates = min_valid[min_valid > threshold].index
    features = {k: v.loc[valid_dates] for k, v in features.items()}
    logger.info("Feature dates: %s to %s", valid_dates[0], valid_dates[-1])

    atr_df = atr(prices)
    if not isinstance(atr_df.index, pd.DatetimeIndex):
        atr_df.index = pd.to_datetime(atr_df.index)

    # --- Walk-forward validation ---
    from strategy.cross_sectional import CrossSectionalRanker, RankerConfig
    from backtest.portfolio import BacktestConfig, run_backtest, run_validation

    ranker_config = RankerConfig(n_top=args.top_n, dsr_threshold=args.dsr_threshold)
    ranker = CrossSectionalRanker(ranker_config)

    if args.validate:
        logger.info("Running walk-forward backtest...")
        bt_config = BacktestConfig(n_top=args.top_n, rebalance_freq=args.rebalance)
        bt_result = run_backtest(prices, ranker, features, bt_config)
        print(bt_result.summary())

        val_result = run_validation(bt_result, n_trials=ranker_config.n_trials, dsr_threshold=args.dsr_threshold)
        print(val_result)

        if not val_result.passes and args.execute:
            logger.error(
                "DSR=%.3f < threshold=%.2f. Refusing to trade. "
                "Run with --dry-run to inspect picks without trading.",
                val_result.deflated_sharpe, args.dsr_threshold,
            )
            sys.exit(1)
        elif val_result.passes:
            ranker.mark_validated()
    else:
        # Fit on all available data for today's picks
        from features.library import compute_forward_returns
        close = prices.close
        if not isinstance(close.index, pd.DatetimeIndex):
            close.index = pd.to_datetime(close.index)
        fwd_returns = compute_forward_returns(close)
        ranker.fit(features, fwd_returns)
        if not args.execute:
            ranker.mark_validated()  # dry-run doesn't need DSR gate

    # --- Generate today's picks ---
    logger.info("Scoring universe for %s...", today)
    last_feat_date = max(df.index.max() for df in features.values())
    ranked = ranker.select_top_n(last_feat_date)
    logger.info("Top picks: %s", [t for t, _ in ranked])

    # --- Size picks ---
    from risk.sizing import RiskConfig, size_picks

    risk_config = RiskConfig(
        max_weight=args.max_weight,
        sector_cap=args.sector_cap,
    )
    sized = size_picks(ranked, prices, atr_df, risk_config)

    # --- Feature rows for rationale ---
    feature_rows = {}
    for ticker in [p.ticker for p in sized]:
        feature_rows[ticker] = {
            name: float(df.loc[last_feat_date, ticker])
            for name, df in features.items()
            if ticker in df.columns and last_feat_date in df.index
        }

    # --- Output ---
    from output.picks import print_picks, write_picks, send_alert

    print_picks(sized, as_of=today, feature_rows=feature_rows)

    if not args.execute or args.dry_run:
        write_picks(sized, as_of=today, feature_rows=feature_rows)
        send_alert(sized, as_of=today)
        print(f"\n[DRY RUN] Picks written to output_data/. No orders placed.\n")
        return

    # --- Execute (paper only unless --live confirmed) ---
    if not ranker.is_validated():
        logger.error("Ranker not validated. Run with --validate first.")
        sys.exit(1)

    from execution.alpaca_paper import get_account, place_basket

    acct = get_account(live=args.live)
    logger.info("Account equity: $%.2f", acct["equity"])

    results = place_basket(
        picks=sized,
        portfolio_value=acct["equity"],
        dry_run=False,
        live=args.live,
    )
    errors = [r for r in results if r.error]
    if errors:
        logger.warning("%d orders failed: %s", len(errors), [r.ticker for r in errors])

    write_picks(sized, as_of=today, feature_rows=feature_rows)
    send_alert(sized, as_of=today)
    print(f"\n✅ Placed {len(results) - len(errors)}/{len(results)} orders in "
          f"{'LIVE' if args.live else 'PAPER'} account.\n")


if __name__ == "__main__":
    main()
