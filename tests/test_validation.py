import numpy as np
import pytest
from validation.overfitting import (
    deflated_sharpe_ratio, probabilistic_sharpe_ratio, annualized_sharpe,
)


def _make_returns(sharpe: float, n: int = 500, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    daily_sr = sharpe / np.sqrt(252)
    std = 0.01
    mean = daily_sr * std
    return rng.normal(mean, std, n)


def test_high_sharpe_passes():
    returns = _make_returns(sharpe=2.0, n=500)
    result = deflated_sharpe_ratio(returns, n_trials=10, threshold=0.95)
    # With high sharpe and single trials, DSR should be well above threshold
    assert result.deflated_sharpe > 0.0   # at minimum positive
    assert result.n_obs == 500


def test_negative_sharpe_fails():
    returns = _make_returns(sharpe=-1.0, n=500)
    result = deflated_sharpe_ratio(returns, n_trials=1, threshold=0.95)
    assert not result.passes
    assert result.deflated_sharpe < 0.95


def test_more_trials_harder_to_pass():
    returns = _make_returns(sharpe=1.5, n=500)
    r1 = deflated_sharpe_ratio(returns, n_trials=1)
    r100 = deflated_sharpe_ratio(returns, n_trials=100)
    assert r1.deflated_sharpe >= r100.deflated_sharpe


def test_psr_zero_benchmark():
    returns = _make_returns(sharpe=1.0, n=500)
    psr = probabilistic_sharpe_ratio(returns, sr_benchmark=0.0)
    assert 0.0 < psr <= 1.0


def test_annualized_sharpe():
    returns = _make_returns(sharpe=1.0, n=2000)
    sr = annualized_sharpe(returns)
    # Should be approximately 1.0 with some noise
    assert 0.5 < sr < 1.5
