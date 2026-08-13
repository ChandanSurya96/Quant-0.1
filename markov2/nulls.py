"""Permutation null. The gate a result has to walk through before it is called
tradeable.

A backtest number on its own says nothing, because the null it should be judged
against is not zero - it is "what would an equally-active strategy have earned
from a label sequence with no predictive content". On TCS.NS that null spans
Sharpe -0.63 to +0.67 at the 5th/95th, so a real Sharpe of 0.21 is unremarkable.

CIRCULAR ROTATION is the primary null and the default. Rotating the label series
preserves, exactly:

  * the count of each state,
  * every run length and the full autocorrelation function,
  * the stride-20 transition geometry and therefore the whole matrix,
  * the number of observations.

It breaks one thing only: the alignment between a label and the returns that
follow it. That isolates predictive content, which is the thing under test.

I.I.D. SHUFFLE is available but is NOT the primary null and must not be used as
one. It additionally destroys the autocorrelation, so its spread is too narrow
and its p-values are anti-conservative - it will call things significant that
rotation will not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .stats import percentile_and_p

PRIMARY_NULL = "rotate"
DEFAULT_N_PERM = 1000
METRIC_KEYS = ("sharpe", "cagr", "max_drawdown", "profit_factor")


def circular_rotation(labels, shift: int) -> np.ndarray:
    """Rotate the label sequence by `shift`, wrapping around.

    Counts, run lengths and autocorrelation survive untouched; only the phase
    relative to the return series moves.
    """
    return np.roll(np.asarray(labels, dtype=int), int(shift))


def iid_shuffle(labels, rng: np.random.Generator) -> np.ndarray:
    """Secondary null. Preserves counts only - see the module docstring."""
    return rng.permutation(np.asarray(labels, dtype=int))


def _shifts(n: int, n_perm: int, rng: np.random.Generator, guard: int) -> np.ndarray:
    """Rotations far enough from 0 and n that the series is genuinely re-phased.

    A shift of 3 bars leaves the labels almost where they were and would stack
    the null with near-copies of the real thing.
    """
    lo, hi = guard, max(guard + 1, n - guard)
    if hi <= lo:
        lo, hi = 1, max(2, n)
    return rng.integers(lo, hi, size=n_perm)


def permutation_null(
    labels,
    evaluate,
    *,
    n_perm: int = DEFAULT_N_PERM,
    method: str = PRIMARY_NULL,
    seed: int = 20260813,
    guard: int = 252,
) -> pd.DataFrame:
    """Run `evaluate(permuted_labels) -> metrics dict` over `n_perm` surrogates.

    `evaluate` owns the strategy; this module only supplies the label surrogates,
    so the null runs through the identical walk-forward, identical costs and
    identical evaluation window as the real result.
    """
    lab = np.asarray(labels, dtype=int)
    n = len(lab)
    rng = np.random.default_rng(seed)
    if method == "rotate":
        surrogates = (circular_rotation(lab, s) for s in _shifts(n, n_perm, rng, guard))
    elif method == "iid":
        surrogates = (iid_shuffle(lab, rng) for _ in range(n_perm))
    else:
        raise ValueError(f"unknown null method {method!r} (expected 'rotate' or 'iid')")

    rows = []
    for surrogate in surrogates:
        m = evaluate(surrogate)
        rows.append({k: m.get(k, float("nan")) for k in METRIC_KEYS}
                    | {"exposure": m.get("exposure", float("nan"))})
    return pd.DataFrame(rows)


def summarise(null_df: pd.DataFrame, real_metrics: dict) -> dict:
    """Per-metric null summary plus the percentile and p of the real result."""
    out = {}
    for key in METRIC_KEYS:
        if key not in null_df.columns:
            continue
        v = null_df[key].replace([np.inf, -np.inf], np.nan).to_numpy(float)
        out[key] = {"real": float(real_metrics.get(key, float("nan")))} | percentile_and_p(
            v, float(real_metrics.get(key, float("nan"))))
    return out
