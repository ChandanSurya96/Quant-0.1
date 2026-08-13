"""Optional Hidden Markov mode.

No hand-made thresholds: Baum-Welch finds the states, Viterbi assigns them.
The point of running it is the agreement number - if an unsupervised fit lands
on roughly the same regimes as your +/-5% rule, the rule is describing
something real. If it does not, the rule is describing your threshold.

hmmlearn is imported lazily so the rest of the skill works without it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .states import N_STATES, STATE_NAMES


def fit_hmm(returns: pd.Series, n_components: int = N_STATES, random_state: int = 42, n_restarts: int = 5):
    """Fit a Gaussian HMM on daily returns, best of `n_restarts` by log-likelihood.

    States are remapped to the canonical monotone-return order (FIX 2 applied at
    the source, since Baum-Welch state ids are arbitrary).

    Returns (model, labels, info) or (None, None, reason).
    """
    try:
        from hmmlearn import hmm
    except ImportError as exc:
        return None, None, f"hmmlearn unavailable: {exc}"

    r = returns.dropna()
    X = r.to_numpy(dtype=float).reshape(-1, 1)

    best, best_ll = None, -np.inf
    for k in range(n_restarts):
        m = hmm.GaussianHMM(
            n_components=n_components,
            covariance_type="diag",
            n_iter=300,
            random_state=random_state + k,
        )
        try:
            m.fit(X)
            ll = m.score(X)
        except Exception:  # noqa: BLE001 - a bad restart should not kill the fit
            continue
        if ll > best_ll:
            best, best_ll = m, ll

    if best is None:
        return None, None, "all Baum-Welch restarts failed"

    raw = best.predict(X)
    means = np.array([best.means_[k][0] for k in range(n_components)])
    order = np.argsort(means)
    remap = {int(old): int(new) for new, old in enumerate(order)}
    labels = pd.Series([remap[int(k)] for k in raw], index=r.index, dtype=int)

    info = {
        "log_likelihood": float(best_ll),
        "restarts": n_restarts,
        "means_sorted": [float(means[k]) for k in order],
        "vars_sorted": [float(best.covars_[k].ravel()[0]) for k in order],
    }
    return best, labels, info


def agreement(threshold_labels: pd.Series, hmm_labels: pd.Series) -> dict:
    """Where the unsupervised fit agrees with the hand-made labels."""
    common = threshold_labels.index.intersection(hmm_labels.index)
    a = threshold_labels.loc[common].to_numpy(dtype=int)
    b = hmm_labels.loc[common].to_numpy(dtype=int)
    if len(common) == 0:
        return {"overall": float("nan"), "per_state": {}, "n": 0, "confusion": None}

    confusion = np.zeros((N_STATES, N_STATES), dtype=int)
    np.add.at(confusion, (a, b), 1)

    per_state = {}
    for s in range(N_STATES):
        tot = confusion[s].sum()
        per_state[STATE_NAMES[s]] = float(confusion[s, s] / tot) if tot else float("nan")

    return {
        "overall": float((a == b).mean()),
        "per_state": per_state,
        "n": int(len(common)),
        "confusion": confusion,
    }
