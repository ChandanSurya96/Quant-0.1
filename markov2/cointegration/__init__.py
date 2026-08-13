"""Cointegration and Condition-Number Acceleration Subsystem for Markov 2.0.

Provides:
- Condition number estimation tools (Exact SVD & Fast Lanczos/Power Iteration).
- Engle-Granger Cointegration testing (Classical OLS vs Fast QR/CG + ADF unit-root test).
- Multivariate cointegration screening pipeline with walk-forward data leakage protection.
- Synthetic validation and benchmark engines.
"""

from __future__ import annotations

from .condition_number import estimate_condition_number, exact_condition_number
from .engle_granger import engle_granger_test, fast_engle_granger_test
from .pipeline import scan_cointegrated_pairs, walk_forward_cointegration

__all__ = [
    "exact_condition_number",
    "estimate_condition_number",
    "engle_granger_test",
    "fast_engle_granger_test",
    "scan_cointegrated_pairs",
    "walk_forward_cointegration",
]
