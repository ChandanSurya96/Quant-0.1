"""The control Markov 2.0 has to beat.

Validation showed the only overlay that improved on buy-and-hold - go flat while
the trailing 20-bar return is at or below -5% - is bit-for-bit identical to a
plain trailing-return rule. It consults no transition matrix, no forecast and no
signal. On TCS.NS both produce Sharpe 0.5302; on TMPV.NS both produce 0.9039.

That rule predates this framework and belongs to momentum/volatility filtering,
not to Markov. Reporting its performance as a Markov result would be the exact
error this module exists to prevent, so every backtest now carries it as a
mandatory comparator and the report states plainly whether Markov cleared it.

Deliberately written from the raw trailing return rather than from the state
label, so that it cannot pick up any part of the labelling machinery by
accident. `tests/test_markov2.py` asserts the two formulations agree.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import apply_costs, metrics, turnover

LABEL_ONLY_NAME = "Label-only baseline (flat when trailing 20d <= -5%)"


def trailing_return_positions(close: pd.Series, window: int = 20,
                              threshold: float = 0.05) -> pd.Series:
    """Long 1.0, flat while the trailing `window`-bar return is <= -threshold.

    Known at the close of t, traded on t+1, same convention as `walk_forward`.
    """
    trail = close.pct_change(window)
    flat = trail.fillna(0.0) <= -abs(threshold)
    return pd.Series(np.where(flat, 0.0, 1.0), index=close.index)


def run_label_only(
    close: pd.Series,
    labels: pd.Series,
    *,
    window: int = 20,
    threshold: float = 0.05,
    min_train: int = 756,
    cost_bps: float = 0.0,
) -> dict:
    """Evaluate the baseline over the same window `walk_forward` evaluates."""
    rets = close.pct_change()
    common = labels.index.intersection(rets.index)
    close_a = close.reindex(common)
    ret = np.nan_to_num(rets.reindex(common).to_numpy(float), nan=0.0)
    raw = trailing_return_positions(close_a, window, threshold).to_numpy(float)

    n = len(common)
    pos = np.zeros(n)
    pos[min_train : n - 1] = raw[min_train : n - 1]
    effective = np.zeros(n)
    effective[1:] = pos[:-1]
    strat = effective * ret

    active = slice(min_train + 1, n)
    s_a, e_a = strat[active], effective[active]
    net = apply_costs(s_a, e_a, cost_bps)
    return {
        "index": common[active],
        "strategy_returns": pd.Series(s_a, index=common[active]),
        "net_returns": pd.Series(net, index=common[active]),
        "positions": pd.Series(e_a, index=common[active]),
        "metrics": metrics(s_a, e_a),
        "net_metrics": metrics(net, e_a),
        "turnover": turnover(e_a),
        "name": LABEL_ONLY_NAME,
    }


def markov_adds_value(markov: dict, baseline: dict, key: str = "sharpe",
                      margin: float = 0.0) -> dict:
    """Did Markov beat the matrix-free control on `key`?

    `margin` is a required excess, not a tolerance: setting it above 0 demands
    Markov win by something rather than merely tie.
    """
    m, b = float(markov.get(key, np.nan)), float(baseline.get(key, np.nan))
    beats = bool(np.isfinite(m) and np.isfinite(b) and (m - b) > margin)
    if not np.isfinite(m) or not np.isfinite(b):
        verdict = "UNDETERMINED"
    elif beats:
        verdict = "MARKOV ADDS VALUE over the label-only baseline"
    elif np.isclose(m, b, rtol=1e-9, atol=1e-12):
        verdict = ("NO MARKOV VALUE - identical to the label-only baseline. "
                   "This is a trailing-return effect, not Markov alpha.")
    else:
        verdict = ("NO MARKOV VALUE - the matrix-free baseline is better. "
                   "Any edge here belongs to the trailing-return rule.")
    return {"markov": m, "baseline": b, "delta": m - b, "beats": beats, "verdict": verdict}
