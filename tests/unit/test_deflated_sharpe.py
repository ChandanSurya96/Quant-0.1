"""Unit tests for Deflated Sharpe Ratio and statistical methods."""

from scripts.run_momentum_factor_deep_study import compute_deflated_sharpe_ratio, norm_cdf, norm_ppf


def test_norm_cdf_and_ppf_inverses():
    # Test inverse round-trip
    for p in [0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99]:
        z = norm_ppf(p)
        p_recon = norm_cdf(z)
        assert abs(p - p_recon) < 1e-4, f"Failed roundtrip for p={p}: got {p_recon}"


def test_deflated_sharpe_ratio_decreases_with_trials():
    # As the number of trials increases, DSR should decrease (higher hurdle for statistical significance)
    dsr_1 = compute_deflated_sharpe_ratio(
        observed_sharpe=0.10,
        n_trials=2,
        var_trials=0.05,
        skewness=0.0,
        kurtosis=3.0,
        n_observations=252,
    )
    dsr_50 = compute_deflated_sharpe_ratio(
        observed_sharpe=0.10,
        n_trials=50,
        var_trials=0.05,
        skewness=0.0,
        kurtosis=3.0,
        n_observations=252,
    )
    assert dsr_1 > dsr_50, f"DSR failed to penalize trials: {dsr_1} vs {dsr_50}"


def test_deflated_sharpe_ratio_single_trial():
    dsr = compute_deflated_sharpe_ratio(
        observed_sharpe=0.50,
        n_trials=1,
        var_trials=0.0,
        skewness=0.0,
        kurtosis=3.0,
        n_observations=1000,
    )
    assert 0.0 <= dsr <= 1.0
