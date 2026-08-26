"""Statistical utilities for Sharpe Ratio standard errors, higher moments, and DSR."""

from __future__ import annotations

import math
import numpy as np
import pandas as pd


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function (error function based)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Standard normal percentage point function (inverse CDF) using Peter J. Acklam's algorithm."""
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0

    a = [
        -3.969683028665376e+01,
         2.209460984245205e+02,
        -2.759285104469687e+02,
         1.383577518672690e+02,
        -3.066479806614716e+01,
         2.506628277459239e+00,
    ]
    b = [
        -5.447609879822406e+01,
         1.615858368580409e+02,
        -1.556989798598866e+02,
         6.680131188771972e+01,
        -1.328068155288572e+01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e+00,
        -2.549732539343734e+00,
         4.374664141464968e+00,
         2.938163982698783e+00,
    ]
    d = [
         7.784695709041462e-03,
         3.224671290700398e-01,
         2.445134137142996e+00,
         3.754408661907416e+00,
    ]

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return float((((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) /
                     ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0))
    elif p <= p_high:
        q = p - 0.5
        r = q * q
        return float((((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5])*q /
                     (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1.0))
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return float(-(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) /
                      ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0))


def calculate_sharpe_statistics(
    returns: pd.Series | np.ndarray,
    rf_daily: float | pd.Series | np.ndarray = 0.0,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """Calculates annualized Gross and Excess Sharpe with Lo & Mertens (2002) SE and CI."""
    r_arr = np.array(returns, dtype=float)
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
    periods_per_year: int = 252,
) -> float:
    """Computes Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) with consistent annualized units."""
    if n_trials <= 1 or var_trials <= 0:
        return norm_cdf(observed_sharpe * math.sqrt(n_observations / periods_per_year))

    euler_mascheroni = 0.5772156649
    p1 = 1.0 - 1.0 / n_trials
    p2 = 1.0 - 1.0 / (n_trials * math.e)
    exp_max_z = (1.0 - euler_mascheroni) * norm_ppf(p1) + euler_mascheroni * norm_ppf(p2)
    sr_benchmark_ann = math.sqrt(var_trials) * exp_max_z

    # Annualized standard error matching observed_sharpe frequency
    daily_sr = observed_sharpe / math.sqrt(periods_per_year)
    var_term = 1.0 - skewness * daily_sr + ((kurtosis + 2.0) / 4.0) * (daily_sr**2)
    daily_se = math.sqrt(max(1e-8, var_term) / max(1, n_observations - 1))
    sr_std_err_ann = daily_se * math.sqrt(periods_per_year)

    z = (observed_sharpe - sr_benchmark_ann) / (sr_std_err_ann + 1e-8)
    return float(norm_cdf(z))
