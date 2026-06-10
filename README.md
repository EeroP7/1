# Stock Pick System

A cross-sectional US stock ranking and pick system. Screens the universe daily, scores every name against validated momentum/trend/mean-reversion signals, and outputs a short list of high-conviction picks — each with an entry reference, an ATR-based stop, a position weight, and a one-line rationale. Optionally places the basket in an Alpaca paper account.

**Stocks only. No futures.**

---

## ⚠️ Survivorship Bias Warning

The universe is built from the *current* S&P 500 constituent list. Names that were delisted, went bankrupt, or were merged before today are absent. All backtest results are **optimistic upper bounds**. This warning appears in every performance report.

To mitigate: supply your own point-in-time universe file via `UniverseConfig(tickers=[...])`.

---

## Architecture

| Module | Purpose |
|--------|---------|
| `data/universe.py` | Universe definition, liquidity filters, Alpaca data load (Adjustment.ALL) |
| `features/library.py` | Cross-sectional features: multi-horizon momentum, vol-adj trend, mean-reversion z-score, 52w-high distance, volume trend. Normalized daily across names. |
| `strategy/cross_sectional.py` | `CrossSectionalRanker`: fits IC-weighted feature scores, ranks universe, selects top N |
| `backtest/portfolio.py` | Walk-forward portfolio backtester: train/OOS split, rebalance, turnover costs, equity curve |
| `validation/overfitting.py` | Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) — required to clear 0.95 before trading |
| `risk/sizing.py` | Inv-vol weights, max-weight cap, sector cap, ATR-based stop levels |
| `output/picks.py` | Formatted pick list, picks.csv, journal.csv, optional webhook alert |
| `execution/alpaca_paper.py` | Auto-place basket in Alpaca paper; live requires explicit per-order confirmation |
| `scripts/run_picks.py` | CLI entry point |

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env — add ALPACA_API_KEY and ALPACA_SECRET_KEY
```

---

## Usage

### Dry run (generate picks, place nothing)
```bash
python scripts/run_picks.py --dry-run
```

### Full walk-forward validation + dry run
```bash
python scripts/run_picks.py --validate --dry-run
```
Prints OOS Sharpe, Deflated Sharpe, and survivorship caveat.

### Execute in Alpaca paper account
```bash
python scripts/run_picks.py --validate --execute
```
DSR must clear the threshold (default 0.95) or execution is refused.

### Kill switch
```bash
python scripts/run_picks.py --kill-switch
```
Closes all open positions in the paper account immediately.

---

## Example output

```
======================================================================
  STOCK PICKS  —  2024-06-01  (model output, not investment advice)
======================================================================
  NVDA   · rank  1 · score 0.82 · buy ~1100.00 · stop 1060.0 (20.0 ATR×2) · weight  8% · no earnings <10d · why: 6-mo momentum + vol-adj trend
  MSFT   · rank  2 · score 0.74 · buy ~420.50  · stop 408.0  (6.3 ATR×2)  · weight  9% · no earnings <10d · why: 12-mo momentum + near 52w high
  AAPL   · rank  3 · score 0.71 · buy ~192.00  · stop 185.0  (3.5 ATR×2)  · weight  8% · no earnings <10d · why: 6-mo momentum + rising volume
======================================================================
```

---

## Validation

The system requires a Deflated Sharpe Ratio >= 0.95 before auto-execution. This guards against overfitting from parameter search. Increase `--top-n` or loosen filters and the DSR may drop — re-validate before trading.

---

## Schedule & Kill Switch

**Recommended schedule:** run after market close (4:30 PM ET) Mon-Fri. Picks act on next-day open prices.

```cron
30 16 * * 1-5  cd /path/to/repo && python scripts/run_picks.py --execute
```

**Kill switch:** `python scripts/run_picks.py --kill-switch` — closes all positions in the paper account. Add `--execute --live` for the live account (requires typed confirmation).

---

## Tests

```bash
pytest tests/ -v    # 25 tests, all must pass
```

---

## Environment variables

See `.env.example` for the full list. Required for real data:

| Variable | Purpose |
|----------|---------|
| `ALPACA_API_KEY` | Paper account API key |
| `ALPACA_SECRET_KEY` | Paper account secret |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` (default) |
| `TOP_N` | Number of picks (default 10) |
| `MAX_WEIGHT` | Max position weight (default 0.15) |
| `DSR_THRESHOLD` | Minimum DSR to trade (default 0.95) |

Without credentials the system falls back to synthetic data for testing.
