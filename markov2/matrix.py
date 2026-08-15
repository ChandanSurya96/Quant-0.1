"""Transition matrices - legacy (overlapping) and stride-sampled (honest).

RESEARCH STATUS: DEPRECATED. Empirical evaluations (SUZLON-001, TMPV-001) prove the 3-state transition matrix provides no incremental alpha over continuous momentum.

DEPRECATION NOTICE:
Single-asset 20-bar discrete Markov transition matrix filters are DEPRECATED following
empirical rejection across single-asset equities (SUZLON, TCS, TMPV, ^NSEI). 95% Wilson Score
intervals confirm 9/9 transition cells cover unconditional base rates, carrying no predictive
alpha over simple momentum controls. Research focus has shifted to Cross-Sectional Factor Alpha.

FIX 1. Labels are built from a trailing 20-bar window. Two labels one bar apart
describe windows that share 19 of their 20 bars, so counting day-to-day
transitions measures the overlap of the windows, not the persistence of the
regime. The diagonal comes out near 1.0 no matter what the asset does.

The corrected estimator only ever counts transitions between windows that share
zero bars, i.e. labels separated by at least `stride` bars where stride equals
the window length.

Two ways to do that:

  single     take every stride-th label (one chain, phases discarded).
             Literal, easy to explain, throws away 95% of the data.
  phase      count every (t, t+stride) pair. Each counted pair is still
             non-overlapping, so the persistence bias is gone, but all phase
             offsets contribute instead of just one. Same estimator, lower
             variance. This is the default.

Neither recovers the lost information: the effective sample size is bars/stride
either way. `phase` just stops the point estimate from depending on where you
happened to start counting.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .states import N_STATES

TransitionResult = dict


def _counts_from_pairs(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    counts = np.zeros((N_STATES, N_STATES), dtype=float)
    if len(a) == 0:
        return counts
    np.add.at(counts, (a, b), 1.0)
    return counts


def counts_overlapping(labels) -> np.ndarray:
    """LEGACY / BIASED. Consecutive-bar transitions between overlapping windows."""
    a = np.asarray(labels, dtype=int)
    if len(a) < 2:
        return np.zeros((N_STATES, N_STATES))
    return _counts_from_pairs(a[:-1], a[1:])


def counts_stride(labels, stride: int = 20, mode: str = "phase") -> np.ndarray:
    """CORRECTED. Transitions between non-overlapping windows only."""
    a = np.asarray(labels, dtype=int)
    if len(a) <= stride:
        return np.zeros((N_STATES, N_STATES))
    if mode == "single":
        chain = a[::stride]
        if len(chain) < 2:
            return np.zeros((N_STATES, N_STATES))
        return _counts_from_pairs(chain[:-1], chain[1:])
    if mode == "phase":
        return _counts_from_pairs(a[:-stride], a[stride:])
    raise ValueError(f"unknown stride mode {mode!r} (expected 'phase' or 'single')")


def counts_to_matrix(counts: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Row-normalise. Returns (P, unobserved_row_indices).

    A row with zero observations is filled with a uniform 1/3 so that matrix
    powers stay well defined, and reported separately so it is never mistaken
    for a measurement.
    """
    row_sums = counts.sum(axis=1, keepdims=True)
    unobserved = [int(i) for i in np.where(row_sums.ravel() == 0)[0]]
    safe = np.where(row_sums == 0, 1.0, row_sums)
    P = counts / safe
    for i in unobserved:
        P[i, :] = 1.0 / N_STATES
    return P, unobserved


def build(labels, stride: int = 20, stride_mode: str = "phase") -> TransitionResult:
    """Build both matrices side by side. Never return only one."""
    c_over = counts_overlapping(labels)
    c_str = counts_stride(labels, stride=stride, mode=stride_mode)
    P_over, un_over = counts_to_matrix(c_over)
    P_str, un_str = counts_to_matrix(c_str)
    return {
        "counts_overlapping": c_over,
        "counts_stride": c_str,
        "P_overlapping": P_over,
        "P_stride": P_str,
        "unobserved_overlapping": un_over,
        "unobserved_stride": un_str,
        "stride": stride,
        "stride_mode": stride_mode,
    }


def stickiness(P: np.ndarray) -> np.ndarray:
    """The diagonal: P(stay in state | in state)."""
    return np.diag(P).copy()


def stationary(P: np.ndarray) -> np.ndarray:
    """Left eigenvector for eigenvalue 1, normalised. Falls back to iteration."""
    try:
        vals, vecs = np.linalg.eig(P.T)
        idx = int(np.argmin(np.abs(vals - 1.0)))
        v = np.real(vecs[:, idx])
        v = np.abs(v)
        if v.sum() > 0:
            return v / v.sum()
    except np.linalg.LinAlgError:
        pass
    v = np.full(N_STATES, 1.0 / N_STATES)
    for _ in range(10_000):
        v = v @ P
    return v / v.sum()


def n_step(P: np.ndarray, n: int) -> np.ndarray:
    """Chapman-Kolmogorov."""
    return np.linalg.matrix_power(P, n)


def signal(P: np.ndarray, state: int) -> float:
    """P(bull next) - P(bear next). Sign = direction, magnitude = conviction."""
    from .states import BEAR, BULL

    return float(P[state, BULL] - P[state, BEAR])


def signal_vector(P: np.ndarray) -> np.ndarray:
    return np.array([signal(P, s) for s in range(N_STATES)])


def convergence_profile(P: np.ndarray, horizons=(1, 2, 5, 10, 20, 60, 120)) -> list[dict]:
    """How fast does the n-step forecast decay into the stationary mix?

    Once max|signal| is inside noise, longer horizons carry no information.
    """
    pi = stationary(P)
    out = []
    for h in horizons:
        Ph = n_step(P, h)
        tv = float(np.abs(Ph - pi[None, :]).sum(axis=1).max() / 2.0)
        out.append(
            {
                "horizon": h,
                "max_signal": float(np.abs(signal_vector(Ph)).max()),
                "tv_distance_to_stationary": tv,
            }
        )
    return out
