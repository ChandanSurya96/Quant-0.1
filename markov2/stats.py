"""Uncertainty for transition-matrix cells.

The matrix prints percentages to two decimals. With ~30 effective observations
behind a row, the real uncertainty on a cell is +/- 15 percentage points. That
gap between apparent and actual precision is how a base-rate table gets mistaken
for a forecast, so every cell now carries its own interval and its own base rate.

n_eff convention is the one already used by `run.py`: in `phase` stride mode the
raw counts are every (t, t+stride) pair, and while each pair is internally
non-overlapping the pairs overlap EACH OTHER, so the raw count overstates
independent information by a factor of `stride`. In `single` mode the chain is
already thinned and the raw count stands.
"""

from __future__ import annotations

import numpy as np

from .states import N_STATES, STATE_NAMES

Z95 = 1.959963984540054


def effective_n(raw_count: float, stride: int, stride_mode: str = "phase") -> float:
    """Independent observations behind a raw transition count."""
    if stride_mode == "phase":
        return float(raw_count) / float(stride)
    if stride_mode == "single":
        return float(raw_count)
    raise ValueError(f"unknown stride mode {stride_mode!r}")


def wilson(successes: float, n: float, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Chosen over the normal approximation because it stays inside [0, 1] and keeps
    sensible coverage at the small n_eff this framework actually has. `successes`
    may be fractional - it is p_hat * n_eff, not a raw count.
    """
    n = float(n)
    if n <= 0:
        return (float("nan"), float("nan"))
    p = float(successes) / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * np.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def cell_stats(counts: np.ndarray, base_rates: np.ndarray, stride: int,
               stride_mode: str = "phase", z: float = Z95) -> list[dict]:
    """One row per transition cell: count, p, n_eff, base rate, lift, CI.

    `contains_base` is the flag that matters. When the interval covers the
    unconditional destination rate, the cell is not distinguishable from "this
    state tells you nothing you did not already know from the state mix".
    """
    rows = []
    for i in range(N_STATES):
        row_total = float(counts[i].sum())
        n_eff = effective_n(row_total, stride, stride_mode)
        for j in range(N_STATES):
            k = float(counts[i, j])
            p = k / row_total if row_total > 0 else float("nan")
            lo, hi = wilson(p * n_eff, n_eff, z) if row_total > 0 else (float("nan"),) * 2
            base = float(base_rates[j])
            rows.append({
                "from": STATE_NAMES[i],
                "to": STATE_NAMES[j],
                "from_idx": i,
                "to_idx": j,
                "count": k,
                "row_total": row_total,
                "p": p,
                "n_eff": n_eff,
                "base_rate": base,
                "lift_pp": (p - base) * 100.0 if np.isfinite(p) else float("nan"),
                "ci_lo": lo,
                "ci_hi": hi,
                "contains_base": bool(lo <= base <= hi) if np.isfinite(lo) else True,
                "thin": bool(n_eff < 30),
            })
    return rows


def percentile_and_p(null_values: np.ndarray, real: float) -> dict:
    """Empirical percentile and one/two-sided p of `real` against a null sample."""
    v = np.asarray(null_values, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) == 0 or not np.isfinite(real):
        return {"n": 0, "percentile": float("nan"), "p_one_sided": float("nan"),
                "p_two_sided": float("nan"), "mean": float("nan"), "median": float("nan"),
                "q05": float("nan"), "q95": float("nan")}
    # one-sided p includes the real result itself: (#{null >= real} + 1) / (n + 1),
    # the standard finite-sample correction. Without the +1 a p of exactly 0 is
    # reportable off 1000 draws, which overstates what 1000 draws can show.
    p_one = (float((v >= real).sum()) + 1.0) / (len(v) + 1.0)
    centre = v.mean()
    p_two = (float((np.abs(v - centre) >= abs(real - centre)).sum()) + 1.0) / (len(v) + 1.0)
    return {
        "n": int(len(v)),
        "percentile": float((v < real).mean() * 100.0),
        "p_one_sided": float(min(p_one, 1.0)),
        "p_two_sided": float(min(p_two, 1.0)),
        "mean": float(centre),
        "median": float(np.median(v)),
        "q05": float(np.quantile(v, 0.05)),
        "q95": float(np.quantile(v, 0.95)),
    }
