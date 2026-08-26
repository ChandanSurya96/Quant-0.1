"""Yale / Gatev et al. (2006) Statistical Arbitrage & Pairs Trading Research Subsystem.

Provides:
- Point-in-time price normalization and Euclidean distance calculation
- Pair formation and ranking (T20, T100, T500, L50, L75, R20)
- 2-sigma spread divergence trading signals with wait-one-day execution
- Buy-and-hold capital weighting with convergence and horizon exit rules
- Overlapping monthly 6-month trading cohort aggregation
- Engle-Granger cointegration & dynamic hedge-ratio estimation
- 6-factor and macroeconomic risk regressions with Newey-West HAC standard errors
- Portfolio combination and diversification analytics
"""

from __future__ import annotations

from .backtest import YalePairsBacktester
from .cohorts import OverlappingCohortManager
from .cointegration import CointegrationPairEngine
from .diagnostics import PairsRiskDiagnostics
from .distance import calculate_pairwise_distances, calculate_spread_variance
from .execution import PairExecutionEngine, PairTrade
from .formation import PairFormationEngine, select_top_pairs
from .normalization import normalize_price_series
from .signals import PairSignalEngine

__all__ = [
    "normalize_price_series",
    "calculate_pairwise_distances",
    "calculate_spread_variance",
    "PairFormationEngine",
    "select_top_pairs",
    "PairSignalEngine",
    "PairTrade",
    "PairExecutionEngine",
    "OverlappingCohortManager",
    "CointegrationPairEngine",
    "PairsRiskDiagnostics",
    "YalePairsBacktester",
]
