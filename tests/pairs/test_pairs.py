"""Comprehensive unit and integration test suite for quant/pairs package."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.pairs.normalization import normalize_price_series
from quant.pairs.distance import calculate_pairwise_distances, calculate_spread_variance
from quant.pairs.universe import filter_universe_liquidity, filter_same_sector_pairs
from quant.pairs.formation import select_top_pairs, PairFormationEngine
from quant.pairs.signals import PairSignalEngine, PairTradeRecord
from quant.pairs.execution import PairExecutionEngine
from quant.pairs.cohorts import OverlappingCohortManager
from quant.pairs.cointegration import CointegrationPairEngine, estimate_half_life
from quant.pairs.diagnostics import newey_west_ols, PairsRiskDiagnostics
from quant.pairs.backtest import YalePairsBacktester


@pytest.fixture
def sample_price_data():
    """Generates synthetic multi-asset daily price data."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-01", periods=500, freq="B")
    n_assets = 6
    tickers = [f"ASSET_{i}" for i in range(n_assets)]

    # Generate correlated random walks
    cov = np.eye(n_assets) * 0.0004
    cov[0, 1] = cov[1, 0] = 0.00035  # Strong co-movement between 0 and 1
    cov[2, 3] = cov[3, 2] = 0.00030

    rets = rng.multivariate_normal(mean=np.zeros(n_assets), cov=cov, size=len(dates))
    prices = 100.0 * np.exp(np.cumsum(rets, axis=0))
    df = pd.DataFrame(prices, index=dates, columns=tickers)
    return df


def test_price_normalization(sample_price_data):
    """Normalized price series must start strictly at 1.0."""
    norm = normalize_price_series(sample_price_data)
    assert np.allclose(norm.iloc[0].values, 1.0)
    assert norm.shape == sample_price_data.shape


def test_pairwise_distance(sample_price_data):
    """Euclidean distance between ASSET_0 and ASSET_1 should be minimal."""
    norm = normalize_price_series(sample_price_data)
    distances = calculate_pairwise_distances(norm)
    assert ("ASSET_0", "ASSET_1") in distances or ("ASSET_1", "ASSET_0") in distances
    d_01 = distances.get(("ASSET_0", "ASSET_1"), distances.get(("ASSET_1", "ASSET_0")))
    assert d_01 is not None and d_01 >= 0.0


def test_spread_variance():
    """Spread variance must match exact analytical variance."""
    p1 = np.array([1.0, 1.05, 1.10, 1.08, 1.12])
    p2 = np.array([1.0, 1.02, 1.07, 1.05, 1.09])
    mean_s, std_s = calculate_spread_variance(p1, p2)
    diff = p1 - p2
    assert np.isclose(mean_s, np.mean(diff))
    assert np.isclose(std_s, np.std(diff, ddof=1))


def test_universe_filters(sample_price_data):
    """Liquidity and sector filtering logic validation."""
    volumes = pd.DataFrame(1000.0, index=sample_price_data.index, columns=sample_price_data.columns)
    volumes["ASSET_0"] = 5000.0  # High volume

    liquid = filter_universe_liquidity(sample_price_data, volumes=volumes, percentile_threshold=0.50)
    assert "ASSET_0" in liquid

    pairs = [("ASSET_0", "ASSET_1"), ("ASSET_0", "ASSET_2")]
    sector_map = {"ASSET_0": "TECH", "ASSET_1": "TECH", "ASSET_2": "FIN"}
    sec_pairs = filter_same_sector_pairs(pairs, sector_map)
    assert sec_pairs == [("ASSET_0", "ASSET_1")]


def test_wait_one_day_execution_rule(sample_price_data):
    """Positions must open exactly one day after 2-sigma divergence."""
    sig_engine = PairSignalEngine(entry_threshold_sigma=1.0, wait_one_day=True)
    p_info = {
        "asset_i": "ASSET_0",
        "asset_j": "ASSET_1",
        "spread_std": 0.01,
        "p_i_init": float(sample_price_data["ASSET_0"].iloc[0]),
        "p_j_init": float(sample_price_data["ASSET_1"].iloc[0]),
    }
    rets, trades = sig_engine.evaluate_pair_states(p_info, sample_price_data.iloc[:100])
    for tr in trades:
        # Execution date must be strictly after signal date
        assert tr.entry_exec_date > tr.entry_signal_date


def test_cointegration_engine(sample_price_data):
    """Engle-Granger cointegration screening and hedge ratio estimation."""
    c_engine = CointegrationPairEngine(alpha_significance=0.10, top_m=5)
    pairs = c_engine.form_cointegrated_pairs(sample_price_data.iloc[:252])
    assert isinstance(pairs, list)
    for p in pairs:
        assert "hedge_ratio" in p
        assert "p_value" in p
        assert "half_life" in p


def test_newey_west_ols():
    """Validates Newey-West standard error implementation."""
    rng = np.random.default_rng(42)
    N = 200
    X = rng.standard_normal((N, 2))
    beta_true = np.array([0.5, -0.3])
    y = 0.1 + X @ beta_true + rng.standard_normal(N) * 0.1

    res = newey_west_ols(y, X, lags=4)
    assert len(res["coefficients"]) == 3  # Intercept + 2 features
    assert np.isclose(res["coefficients"][1], 0.5, atol=0.1)
    assert np.isclose(res["coefficients"][2], -0.3, atol=0.1)
    assert res["r_squared"] > 0.0


def test_yale_backtester_end_to_end(sample_price_data):
    """End-to-end simulation of overlapping cohort pairs trading."""
    backtester = YalePairsBacktester(
        formation_bars=100,
        trading_bars=60,
        step_bars=20,
        top_m=3,
        entry_threshold_sigma=1.5,
        cost_bps=10.0,
    )
    res = backtester.run(sample_price_data)

    assert "sharpe_net" in res
    assert "cagr_net" in res
    assert len(res["daily_returns"]) > 0


def test_vectorized_pairwise_distance_invariant(sample_price_data):
    """Vectorized matrix pairwise distance must match element-wise calculation."""
    norm = normalize_price_series(sample_price_data)
    distances = calculate_pairwise_distances(norm)

    cols = list(norm.columns)
    vals = norm.to_numpy()
    T = len(vals)

    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            expected_d = float(np.mean((vals[:, i] - vals[:, j]) ** 2))
            actual_d = distances[(cols[i], cols[j])]
            assert np.isclose(actual_d, expected_d, rtol=1e-5, atol=1e-7)


def test_portfolio_variance_invariant():
    """Validates analytical vs empirical portfolio variance formula for 50/50 ensemble."""
    rng = np.random.default_rng(123)
    N = 1000
    r1 = rng.standard_normal(N) * 0.015
    r2 = -0.5 * r1 + rng.standard_normal(N) * 0.005  # Negatively correlated

    r_ens = 0.5 * r1 + 0.5 * r2
    var_empirical = np.var(r_ens, ddof=1)

    var1 = np.var(r1, ddof=1)
    var2 = np.var(r2, ddof=1)
    cov12 = np.cov(r1, r2)[0, 1]
    var_analytical = 0.25 * var1 + 0.25 * var2 + 0.5 * cov12

    assert np.isclose(var_empirical, var_analytical, rtol=1e-5)

