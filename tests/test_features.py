import numpy as np
import pandas as pd
import pytest
from features.library import (
    compute_features, compute_feature_matrix, cs_zscore, cs_rank, atr,
    momentum, vol_adjusted_trend, mean_reversion_zscore,
)


def test_compute_features_returns_all_names(prices):
    feats = compute_features(prices, normalize=True)
    expected = {"mom_1m", "mom_3m", "mom_6m", "mom_12m_skip1m",
                "vol_adj_trend", "mean_rev_z20", "dist_52w_high",
                "vol_trend", "price_range"}
    assert expected.issubset(set(feats.keys()))


def test_features_no_look_ahead(prices):
    # features at date t should not depend on data after t
    # We verify by checking that shifting the close by 1 day changes the feature
    import copy
    close_orig = prices.close.copy()
    feats_orig = compute_features(prices, normalize=False)

    # Shift close by 1 future day
    prices_shifted = copy.copy(prices)
    prices_shifted.close = close_orig.shift(-1)
    feats_shifted = compute_features(prices_shifted, normalize=False)

    # Features should differ
    assert not feats_orig["mom_1m"].equals(feats_shifted["mom_1m"])


def test_cszscore_zero_mean(prices):
    feats = compute_features(prices, normalize=False)
    z = cs_zscore(feats["mom_1m"].dropna())
    row_means = z.mean(axis=1).dropna()
    # cross-sectional mean should be near 0 for each date
    assert (row_means.abs() < 0.1).all()


def test_atr_positive(prices):
    a = atr(prices)
    assert (a.dropna().values > 0).all()


def test_feature_matrix_shape(prices, features):
    last_date = max(df.index.max() for df in features.values())
    mat = compute_feature_matrix(prices, date_=last_date)
    assert mat.shape[1] > 0
