"""Statistical uncertainty and risk-adjusted metrics engine."""

from __future__ import annotations

import math
import statistics
from typing import Any
import numpy as np
import pandas as pd

_NORMAL_DIST = statistics.NormalDist()


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return _NORMAL_DIST.cdf(x)


def norm_ppf(p: float) -> float:
    """Standard normal percent-point function (inverse CDF)."""
    p = max(1e-7, min(1.0 - 1e-7, float(p)))
    return _NORMAL_DIST.inv_cdf(p)


def calculate_sharpe_statistics(
    returns: pd.Series | np.ndarray,
    rf_daily: float | pd.Series | np.ndarray = 0.0,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """Calculates comprehensive Sharpe point estimate and statistical uncertainty metrics.

    Includes Lo (2002) and Mertens (2002) standard errors adjusting for skewness and kurtosis.
    """
    if isinstance(returns, pd.Series):
        r_arr = returns.dropna().to_numpy(dtype=float)
    else:
        r_arr = np.array(returns, dtype=float)
        r_arr = r_arr[~np.isnan(r_arr)]

    n = len(r_arr)
    if n < 3:
        return {
            "gross_sharpe": 0.0,
            "excess_sharpe": 0.0,
            "sharpe_se": 0.0,
            "sharpe_t_stat": 0.0,
            "sharpe_ci_lower_95": 0.0,
            "sharpe_ci_upper_95": 0.0,
            "annualized_return": 0.0,
            "annualized_volatility": 0.0,
            "skewness": 0.0,
            "kurtosis": 0.0,
            "n_observations": n,
        }

    if isinstance(rf_daily, (pd.Series, np.ndarray)):
        rf_arr = np.array(rf_daily, dtype=float)[-n:]
    else:
        rf_arr = np.full(n, float(rf_daily))

    excess_returns = r_arr - rf_arr
    mean_excess = float(np.mean(excess_returns))
    sd_excess = float(np.std(excess_returns, ddof=1))
    mean_gross = float(np.mean(r_arr))
    sd_gross = float(np.std(r_arr, ddof=1))

    ann_factor = math.sqrt(periods_per_year)
    gross_sharpe = float((mean_gross / sd_gross) * ann_factor) if sd_gross > 1e-8 else 0.0
    daily_sr = float(mean_excess / sd_excess) if sd_excess > 1e-8 else 0.0
    excess_sharpe = float(daily_sr * ann_factor)

    # Higher moments (Mertens 2002 / Lo 2002)
    s_series = pd.Series(excess_returns)
    skew = float(s_series.skew()) if n > 2 else 0.0
    kurt = float(s_series.kurtosis()) if n > 3 else 0.0  # Excess kurtosis (normal = 0)

    # Standard Error of annualized Sharpe Ratio
    # SE(SR_ann) = sqrt( (1 + 0.5 * SR_daily^2 - skew * SR_daily + ((kurt)/4) * SR_daily^2) / n ) * ann_factor
    var_term = 1.0 - skew * daily_sr + ((kurt + 2.0) / 4.0) * (daily_sr**2)
    daily_se = math.sqrt(max(1e-8, var_term) / max(1, n - 1))
    sharpe_se = float(daily_se * ann_factor)

    t_stat = float(excess_sharpe / sharpe_se) if sharpe_se > 1e-8 else 0.0
    ci_lower = float(excess_sharpe - 1.96 * sharpe_se)
    ci_upper = float(excess_sharpe + 1.96 * sharpe_se)

    return {
        "gross_sharpe": gross_sharpe,
        "excess_sharpe": excess_sharpe,
        "sharpe_se": sharpe_se,
        "sharpe_t_stat": t_stat,
        "sharpe_ci_lower_95": ci_lower,
        "sharpe_ci_upper_95": ci_upper,
        "annualized_return": float(mean_gross * periods_per_year),
        "annualized_volatility": float(sd_gross * ann_factor),
        "skewness": skew,
        "kurtosis": kurt,
        "n_observations": n,
    }


def compute_deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    var_trials: float,
    skewness: float,
    kurtosis: float,
    n_observations: int,
) -> float:
    """Computes Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR)."""
    if n_trials <= 1 or var_trials <= 0:
        return norm_cdf(observed_sharpe * math.sqrt(n_observations))

    euler_mascheroni = 0.5772156649
    p1 = 1.0 - 1.0 / n_trials
    p2 = 1.0 - 1.0 / (n_trials * math.e)
    exp_max_z = (1.0 - euler_mascheroni) * norm_ppf(p1) + euler_mascheroni * norm_ppf(p2)
    sr_benchmark = math.sqrt(var_trials) * exp_max_z

    denom_term = 1.0 - skewness * observed_sharpe + ((kurtosis - 1.0) / 4.0) * (observed_sharpe**2)
    sr_std_err = math.sqrt(max(1e-8, denom_term) / max(1, n_observations - 1))

    z = (observed_sharpe - sr_benchmark) / (sr_std_err + 1e-8)
    return float(norm_cdf(z))
