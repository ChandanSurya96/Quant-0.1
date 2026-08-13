"""State definitions and labelers.

Canonical index order is monotone in expected return:

    0 = BEAR, 1 = SIDEWAYS, 2 = BULL

Everything downstream (matrix rows/cols, display headers, signal) uses these
indices. `verify.py` enforces that the mapping actually holds against the data,
which is the defence against the bull/bear display swap that shipped in 1.0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BEAR, SIDEWAYS, BULL = 0, 1, 2
STATE_NAMES = ["BEAR", "SIDEWAYS", "BULL"]
N_STATES = 3


def window_return(close: pd.Series, window: int = 20) -> pd.Series:
    """Cumulative return over the trailing `window` bars, known at close of t."""
    return close.pct_change(window)


def label_threshold(close: pd.Series, window: int = 20, threshold: float = 0.05) -> pd.Series:
    """Price-only states.

    20-bar cumulative return >= +threshold -> BULL
                             <= -threshold -> BEAR
                             otherwise     -> SIDEWAYS

    Ordering is monotone in return by construction, so index 2 is always the
    high-return state. `verify.py` still checks it.
    """
    r = window_return(close, window)
    labels = pd.Series(SIDEWAYS, index=close.index, dtype=int)
    labels[r >= threshold] = BULL
    labels[r <= -threshold] = BEAR
    return labels[r.notna()]


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def label_enhanced(
    df: pd.DataFrame,
    window: int = 20,
    n_states: int = N_STATES,
    random_state: int = 0,
) -> tuple[pd.Series, pd.DataFrame]:
    """Enhanced states: cluster on [20-bar return, ATR%, relative volume].

    So that "bear and violent" is a different state from "bear and asleep".

    Cluster ids from KMeans are arbitrary, so they are remapped to the canonical
    monotone-return order before being returned. That remap IS fix 2 applied at
    the source rather than at the display.

    Returns (labels, feature_frame).
    """
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    close, high, low = df["Close"], df["High"], df["Low"]
    volume = df["Volume"]

    feats = pd.DataFrame(
        {
            "ret": window_return(close, window),
            "atr_pct": _atr(high, low, close, 14) / close,
            "rel_vol": volume / volume.rolling(window).mean(),
        }
    ).replace([np.inf, -np.inf], np.nan).dropna()

    X = StandardScaler().fit_transform(feats.to_numpy())
    raw = KMeans(n_clusters=n_states, n_init=10, random_state=random_state).fit_predict(X)

    # Canonicalise: sort clusters by mean window return, ascending.
    order = np.argsort([feats["ret"].to_numpy()[raw == k].mean() for k in range(n_states)])
    remap = {int(old): int(new) for new, old in enumerate(order)}
    labels = pd.Series([remap[int(k)] for k in raw], index=feats.index, dtype=int)
    return labels, feats


def state_distribution(labels: pd.Series) -> np.ndarray:
    """Empirical frequency of each state."""
    counts = np.array([(labels == s).sum() for s in range(N_STATES)], dtype=float)
    return counts / counts.sum() if counts.sum() else counts
