"""Cointegration and Dynamic Hedge Ratio extension for Pairs Trading."""

from __future__ import annotations

import itertools
import numpy as np
import pandas as pd

from markov2.cointegration.engle_granger import fast_engle_granger_test


def estimate_half_life(spread: np.ndarray | pd.Series) -> float:
    """Estimates Ornstein-Uhlenbeck mean-reversion half-life via AR(1) regression.

    Model:
        Delta s_t = theta * s_{t-1} + e_t
        Half-life = -ln(2) / theta  (for theta < 0)
    """
    s = np.asarray(spread, dtype=float)
    s = s[~np.isnan(s)]
    if len(s) < 10:
        return np.nan

    ds = np.diff(s)
    s_lag = s[:-1]
    s_lag_const = np.column_stack([s_lag, np.ones(len(s_lag))])

    try:
        sol, _, _, _ = np.linalg.lstsq(s_lag_const, ds, rcond=None)
        theta = sol[0]
        if theta < -1e-6:
            hl = float(-np.log(2.0) / np.log(1.0 + theta))
            return max(1.0, hl)
    except Exception:
        pass
    return np.nan


class CointegrationPairEngine:
    """Forms pairs using two-step Engle-Granger cointegration and dynamic hedge ratios."""

    def __init__(
        self,
        alpha_significance: float = 0.05,
        top_m: int = 20,
    ) -> None:
        self.alpha_significance = alpha_significance
        self.top_m = top_m

    def form_cointegrated_pairs(
        self,
        formation_prices: pd.DataFrame,
    ) -> list[dict]:
        """Scans formation prices for cointegrated pairs via Engle-Granger ADF test.

        Uses Rad et al. (2015) two-step approach: pre-screens top closest pairs by
        Euclidean distance before running computational Engle-Granger regressions.
        """
        cols = list(formation_prices.columns)
        if len(cols) < 2:
            return []

        # Rad et al. (2015) Euclidean pre-screening
        from .normalization import normalize_price_series
        from .distance import calculate_pairwise_distances

        norm_p = normalize_price_series(formation_prices)
        distances = calculate_pairwise_distances(norm_p)
        sorted_cand = sorted(distances.items(), key=lambda x: x[1])

        # Pre-screen top 100 closest candidates
        screen_m = min(len(sorted_cand), max(self.top_m * 5, 100))
        candidate_pairs = [p[0] for p in sorted_cand[:screen_m]]
        results = []

        for t1, t2 in candidate_pairs:
            p1 = formation_prices[t1].dropna().to_numpy(dtype=float)
            p2 = formation_prices[t2].dropna().to_numpy(dtype=float)

            min_len = min(len(p1), len(p2))
            if min_len < 30:
                continue

            p1 = p1[-min_len:]
            p2 = p2[-min_len:]

            eg_res = fast_engle_granger_test(p1, p2)
            if eg_res["p_value"] <= self.alpha_significance or eg_res["cointegrated"]:
                beta = float(eg_res["hedge_ratio"][0])
                spread = p1 - beta * p2
                hl = estimate_half_life(spread)
                results.append({
                    "pair": (t1, t2),
                    "asset_i": t1,
                    "asset_j": t2,
                    "hedge_ratio": beta,
                    "intercept": float(eg_res["intercept"]),
                    "test_statistic": float(eg_res["test_statistic"]),
                    "p_value": float(eg_res["p_value"]),
                    "half_life": hl,
                    "spread_std": float(np.std(spread, ddof=1)),
                    "p_i_init": float(p1[0]),
                    "p_j_init": float(p2[0]),
                })

        # Sort by test statistic ascending (strongest rejection of non-stationarity first)
        results.sort(key=lambda x: x["test_statistic"])
        return results[:self.top_m]
