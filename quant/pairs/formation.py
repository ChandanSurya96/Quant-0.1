"""Pair Formation Engine per Gatev et al. (2006) and Zhu (2024)."""

from __future__ import annotations

import pandas as pd

from .distance import calculate_pairwise_distances, calculate_spread_variance
from .normalization import normalize_price_series
from .universe import filter_same_sector_pairs, filter_universe_liquidity


def select_top_pairs(
    formation_prices: pd.DataFrame,
    top_m: int = 20,
    volumes: pd.DataFrame | None = None,
    liquidity_percentile: float = 0.0,
    sector_map: dict[str, str] | None = None,
) -> list[dict]:
    """Forms and ranks pairs over a formation window (e.g. 12 months).

    Steps:
    1. Filter eligible universe (liquidity / valid data).
    2. Normalize price series so P_{s,0} = 1.0.
    3. Calculate pairwise Euclidean distance D_{i,j}.
    4. Rank pairs ascending by distance.
    5. Select top M pairs and compute historical spread standard deviation s_{i,j}.

    Returns:
        List of dicts: [
            {
                "pair": (ticker_i, ticker_j),
                "distance": D_ij,
                "mean_spread": mean(P_i - P_j),
                "spread_std": s_ij,
                "p_i_init": P'_{i,0},
                "p_j_init": P'_{j,0},
            }, ...
        ]
    """
    eligible_tickers = filter_universe_liquidity(
        formation_prices,
        volumes=volumes,
        percentile_threshold=liquidity_percentile,
    )
    if len(eligible_tickers) < 2:
        return []

    p_sub = formation_prices[eligible_tickers]
    norm_p = normalize_price_series(p_sub)
    distances = calculate_pairwise_distances(norm_p)

    sorted_pairs = sorted(distances.items(), key=lambda x: x[1])
    if sector_map is not None:
        candidate_pair_tuples = [p[0] for p in sorted_pairs]
        valid_sector_tuples = set(filter_same_sector_pairs(candidate_pair_tuples, sector_map))
        sorted_pairs = [p for p in sorted_pairs if p[0] in valid_sector_tuples]

    selected_pairs = sorted_pairs[:top_m]
    results = []

    for (t1, t2), dist in selected_pairs:
        p1 = norm_p[t1]
        p2 = norm_p[t2]
        mean_sp, std_sp = calculate_spread_variance(p1, p2)
        results.append({
            "pair": (t1, t2),
            "asset_i": t1,
            "asset_j": t2,
            "distance": dist,
            "mean_spread": mean_sp,
            "spread_std": std_sp,
            "p_i_init": float(formation_prices[t1].iloc[0]),
            "p_j_init": float(formation_prices[t2].iloc[0]),
        })

    return results


class PairFormationEngine:
    """Configurable engine for point-in-time pair formation."""

    def __init__(
        self,
        formation_window: int = 252,
        top_m: int = 20,
        liquidity_percentile: float = 0.0,
        sector_map: dict[str, str] | None = None,
    ) -> None:
        self.formation_window = formation_window
        self.top_m = top_m
        self.liquidity_percentile = liquidity_percentile
        self.sector_map = sector_map

    def form_pairs(
        self,
        prices: pd.DataFrame,
        volumes: pd.DataFrame | None = None,
    ) -> list[dict]:
        """Runs formation on the trailing formation_window slice of prices."""
        f_prices = prices.iloc[-self.formation_window:]
        f_volumes = volumes.iloc[-self.formation_window:] if volumes is not None else None
        return select_top_pairs(
            formation_prices=f_prices,
            top_m=self.top_m,
            volumes=f_volumes,
            liquidity_percentile=self.liquidity_percentile,
            sector_map=self.sector_map,
        )
