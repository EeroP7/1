import pandas as pd
import pytest
from backtest.portfolio import BacktestConfig, run_backtest, run_validation
from strategy.cross_sectional import CrossSectionalRanker, RankerConfig


def test_run_backtest_returns_oos_curve(prices, features):
    config = BacktestConfig(n_top=3, min_train_days=100, oos_days=30, rebalance_freq="W")
    ranker = CrossSectionalRanker(RankerConfig(n_top=3))
    result = run_backtest(prices, ranker, features, config)
    assert len(result.oos_returns) > 0
    assert result.n_folds >= 1
    assert not result.oos_returns.isnull().all()


def test_equity_curve_starts_at_one(prices, features):
    config = BacktestConfig(n_top=3, min_train_days=100, oos_days=30, rebalance_freq="W")
    ranker = CrossSectionalRanker(RankerConfig(n_top=3))
    result = run_backtest(prices, ranker, features, config)
    assert abs(result.equity_curve.iloc[0] - 1.0) < 0.05


def test_backtest_sharpe_is_finite(prices, features):
    config = BacktestConfig(n_top=3, min_train_days=100, oos_days=30, rebalance_freq="W")
    ranker = CrossSectionalRanker(RankerConfig(n_top=3))
    result = run_backtest(prices, ranker, features, config)
    assert isinstance(result.sharpe_annualized, float)
    assert not pd.isna(result.sharpe_annualized)


def test_run_validation_returns_result(prices, features):
    config = BacktestConfig(n_top=3, min_train_days=100, oos_days=30)
    ranker = CrossSectionalRanker(RankerConfig(n_top=3))
    bt = run_backtest(prices, ranker, features, config)
    val = run_validation(bt, n_trials=5)
    assert hasattr(val, "deflated_sharpe")
    assert hasattr(val, "passes")
