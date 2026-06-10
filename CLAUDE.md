# CLAUDE.md — Stock Pick System

## Binding rules

1. **Stocks only.** No futures, options, or CFDs anywhere in this codebase.
2. **Validated only.** `CrossSectionalRanker` must have `validated=True` (i.e., DSR >= threshold) before any auto-execution path is permitted. The DSR gate lives in `scripts/run_picks.py`.
3. **Paper only for auto-execution.** `execution/alpaca_paper.py` targets `ALPACA_BASE_URL` (default: `https://paper-api.alpaca.markets`). Live execution requires `--live` flag plus an interactive confirmation prompt; never bypass it.
4. **Survivorship bias must be stated.** Every report, summary, and log line that includes backtest performance numbers must include the survivorship warning from `backtest/portfolio.py::SURVIVORSHIP_WARNING`. No exceptions.
5. **No look-ahead.** Features at date `t` may only use price data through close of `t`. Forward returns are computed with `.shift(-horizon)` applied *after* computation. Tests verify this.
6. **Costs on every rebalance.** `BacktestConfig.cost_per_side` (default 10 bps) is applied to turnover on every rebalance in `backtest/portfolio.py`.
7. **Secrets in env vars only.** No API keys, secrets, or credentials in source files. Use `.env` (gitignored) and `python-dotenv`.

## Architecture

```
data/universe.py          → load + filter universe (Alpaca or synthetic fallback)
features/library.py       → cross-sectional features + normalization + ATR
strategy/cross_sectional.py → CrossSectionalRanker (fit / rank / select)
backtest/portfolio.py     → walk-forward portfolio backtester
validation/overfitting.py → Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014)
risk/sizing.py            → inv-vol weights, max-weight cap, sector cap, ATR stops
output/picks.py           → format + write picks.csv / journal.csv + alert
execution/alpaca_paper.py → paper basket execution (live requires confirmation)
scripts/run_picks.py      → CLI entry point
tests/                    → pytest suite (must be green before any push)
```

## Running

```bash
# Install
pip install -r requirements.txt
cp .env.example .env   # fill in ALPACA_API_KEY / ALPACA_SECRET_KEY

# Dry run (no orders placed)
python scripts/run_picks.py --dry-run

# Full walk-forward validation then dry run
python scripts/run_picks.py --validate --dry-run

# Validate then execute in paper account
python scripts/run_picks.py --validate --execute

# Kill switch — close all paper positions immediately
python scripts/run_picks.py --kill-switch
```

## Schedule

Run `python scripts/run_picks.py --dry-run` daily after market close (e.g., 4:30 PM ET) to generate the next day's picks. Orders execute at next-day open.

Suggested cron:
```
30 16 * * 1-5  cd /path/to/repo && python scripts/run_picks.py --execute
```

## Tests

```bash
pytest tests/ -v
```

All 25 tests must pass before any push.

## Key invariants

- `compute_forward_returns(close)` must have NaN in the last row (verified by `test_forward_returns_no_lookahead`)
- `size_picks` weights must satisfy: each weight ≤ `max_weight`, sum ≤ `total_exposure`
- `deflated_sharpe_ratio` with negative Sharpe must return `passes=False`
