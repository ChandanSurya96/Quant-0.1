"""Walk-forward backtest. FIX 3 - two explicit modes.

FILTER (default)
    The regime is a gate on a strategy you already have. Your baseline supplies
    the entries; Markov 2.0 only decides when they are allowed to fire. Long
    permitted when signal > +signal_threshold, short when signal <
    -signal_threshold, flat in between. The demo baseline is buy-and-hold long,
    which is a stand-in for "your strategy" - swap `baseline` for your own
    position series and nothing else changes.

STANDALONE
    The differential IS the strategy. Position = clip(signal / scale, -cap,
    +cap), so size tracks conviction.

Walk-forward throughout: at every step the matrix is rebuilt from labels
strictly before the bar being traded. Nothing is ever tested on data it was
fitted on.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from .matrix import counts_overlapping, counts_stride, counts_to_matrix
from .states import BEAR, BULL


def _signal_from_counts(counts: np.ndarray, state: int) -> float:
    P, _ = counts_to_matrix(counts)
    return float(P[state, BULL] - P[state, BEAR])


def walk_forward_signals(
    lab: np.ndarray,
    *,
    matrix_kind: str = "stride",
    stride: int = 20,
    stride_mode: str = "phase",
    min_train: int = 756,
) -> np.ndarray:
    """Per-bar signal with the matrix refit on lab[:t+1] at every t.

    Incremental. Stepping t -> t+1 grows the history by exactly one pair -
    (t-stride, t) for the stride estimator, (t-1, t) for the overlapping one -
    so the counts are updated in O(1) instead of rebuilt in O(t). The counts are
    integers held as floats, so repeated += 1.0 is exact and the result is
    bit-identical to rebuilding from scratch. `tests/test_markov2.py` asserts
    that against a naive from-scratch recomputation.

    Only the loop changed; the estimator is `matrix.counts_stride` unmodified.
    """
    lab = np.asarray(lab, dtype=int)
    n = len(lab)
    signals = np.full(n, np.nan)
    if n <= min_train + 1:
        return signals

    if matrix_kind == "stride":
        if stride_mode != "phase":
            # `single` thins the chain, so an added bar does not map to a single
            # added pair. Correctness first: fall back to the from-scratch path.
            for t in range(min_train, n - 1):
                counts = counts_stride(lab[: t + 1], stride=stride, mode=stride_mode)
                signals[t] = _signal_from_counts(counts, int(lab[t]))
            return signals
        counts = counts_stride(lab[: min_train + 1], stride=stride, mode="phase").copy()
        lag = stride
    elif matrix_kind == "overlapping":
        counts = counts_overlapping(lab[: min_train + 1]).copy()
        lag = 1
    else:
        raise ValueError(f"unknown matrix_kind {matrix_kind!r}")

    for t in range(min_train, n - 1):
        if t > min_train:
            i = t - lag
            if i >= 0:
                counts[lab[i], lab[t]] += 1.0
        s = int(lab[t])
        row = counts[s].sum()
        signals[t] = 0.0 if row == 0 else float(
            (counts[s, BULL] - counts[s, BEAR]) / row)
    return signals


def turnover(positions: np.ndarray) -> dict:
    """Traded notional implied by the position path.

    `total` is the sum of |position change| over the evaluated bars, counting the
    initial entry from flat. Costs scale with this, so a strategy cannot look
    good on gross terms while quietly rebalancing every day.
    """
    p = np.asarray(positions, dtype=float)
    if len(p) == 0:
        return {"total": 0.0, "per_bar": 0.0, "annualised": 0.0}
    deltas = np.abs(np.diff(np.concatenate([[0.0], p])))
    total = float(deltas.sum())
    return {"total": total, "per_bar": total / len(p),
            "annualised": total / len(p) * 252.0}


def apply_costs(strategy_returns: np.ndarray, positions: np.ndarray,
                cost_bps: float) -> np.ndarray:
    """Charge `cost_bps` on every unit of |position change|. Zero -> unchanged."""
    r = np.asarray(strategy_returns, dtype=float)
    if not cost_bps:
        return r.copy()
    p = np.asarray(positions, dtype=float)
    deltas = np.abs(np.diff(np.concatenate([[0.0], p])))
    return r - deltas[: len(r)] * (float(cost_bps) / 10_000.0)


def walk_forward(
    close: pd.Series,
    labels: pd.Series,
    *,
    mode: str = "filter",
    matrix_kind: str = "stride",
    stride: int = 20,
    stride_mode: str = "phase",
    min_train: int = 756,
    signal_threshold: float = 0.10,
    cap: float = 1.0,
    scale: float = 0.50,
    baseline: pd.Series | None = None,
    cost_bps: float = 0.0,
) -> dict:
    """Returns dict with per-bar positions, strategy returns and metrics.

    `cost_bps` defaults to 0.0 so every previously published number is
    reproducible from this function unchanged. The CLI supplies a non-zero
    default of its own and reports gross and net side by side.
    """
    if mode == "standalone":
        warnings.warn(
            "STANDALONE mode is DEPRECATED and is not a recommended trading mode. "
            "Permutation testing put it at the 1st percentile of the null on TCS.NS "
            "(Sharpe 0.024) and it returned -0.798 on TMPV.NS: worse than randomly "
            "rotated labels, i.e. a systematic anti-edge rather than a weak edge. "
            "It remains callable for reproducibility and research only.",
            DeprecationWarning,
            stacklevel=2,
        )

    rets = close.pct_change()
    common = labels.index.intersection(rets.index)
    labels = labels.loc[common]
    rets = rets.loc[common]
    if baseline is None:
        baseline = pd.Series(1.0, index=common)  # buy-and-hold stand-in
    else:
        baseline = baseline.reindex(common).fillna(0.0)

    n = len(labels)
    if n < min_train + 30:
        raise ValueError(
            f"need at least {min_train + 30} labelled bars, have {n}. "
            "Use more history or a shorter --min-train."
        )

    lab = labels.to_numpy(dtype=int)
    ret = rets.to_numpy(dtype=float)
    base = baseline.to_numpy(dtype=float)

    positions = np.zeros(n)
    signals = walk_forward_signals(lab, matrix_kind=matrix_kind, stride=stride,
                                   stride_mode=stride_mode, min_train=min_train)

    for t in range(min_train, n - 1):
        s = signals[t]

        if mode == "filter":
            if s > signal_threshold:
                pos = base[t]
            elif s < -signal_threshold:
                pos = -base[t]
            else:
                pos = 0.0
        elif mode == "standalone":
            pos = float(np.clip(s / scale, -cap, cap))
        else:
            raise ValueError(f"unknown mode {mode!r}")
        positions[t] = pos

    # A position set at the close of t earns the return of t+1. `effective` is
    # that position aligned to the bar it actually earned, so win rate, profit
    # factor and exposure describe the same bars as the returns. Masking with
    # the unshifted `positions` is an off-by-one that silently decouples PF
    # from the equity curve.
    effective = np.zeros(n)
    effective[1:] = positions[:-1]
    ret_clean = np.nan_to_num(ret, nan=0.0)
    strat = effective * ret_clean

    active = slice(min_train + 1, n)
    strat_active = strat[active]
    bh_active = ret_clean[active]
    idx_active = labels.index[active]
    eff_active = effective[active]

    # Gross is what the module reported before costs existed and is preserved
    # unchanged. Net is the same path charged `cost_bps` per unit of position
    # change; with cost_bps=0 the two are identical, so old results still hold.
    net_active = apply_costs(strat_active, eff_active, cost_bps)
    tno = turnover(eff_active)

    return {
        "index": idx_active,
        "strategy_returns": pd.Series(strat_active, index=idx_active),
        "net_returns": pd.Series(net_active, index=idx_active),
        "buy_hold_returns": pd.Series(bh_active, index=idx_active),
        "positions": pd.Series(eff_active, index=idx_active),
        "signals": pd.Series(signals[active], index=idx_active),
        "metrics": metrics(strat_active, eff_active),
        "net_metrics": metrics(net_active, eff_active),
        "buy_hold_metrics": metrics(bh_active, np.ones(len(bh_active))),
        "turnover": tno,
        "cost_bps": float(cost_bps),
        "mode": mode,
        "matrix_kind": matrix_kind,
    }


def metrics(r: np.ndarray, positions: np.ndarray) -> dict:
    """Win rate, profit factor, max drawdown, Sharpe, exposure, CAGR."""
    r = np.asarray(r, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return {k: float("nan") for k in
                ("win_rate", "profit_factor", "max_drawdown", "sharpe", "exposure", "cagr", "n_bars")}

    traded = r[positions[: len(r)] != 0] if len(positions) >= len(r) else r
    traded = traded[traded != 0]
    wins = traded[traded > 0]
    losses = traded[traded < 0]

    win_rate = float(len(wins) / len(traded)) if len(traded) else float("nan")
    gross_win, gross_loss = float(wins.sum()), float(-losses.sum())
    profit_factor = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")

    sd = r.std(ddof=1)
    sharpe = float(r.mean() / sd * np.sqrt(252)) if sd > 0 and np.isfinite(sd) else float("nan")

    equity = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(equity)
    max_dd = float(((equity - peak) / peak).min())

    years = len(r) / 252.0
    cagr = float(equity[-1] ** (1.0 / years) - 1.0) if years > 0 and equity[-1] > 0 else float("nan")

    # Coherence guard. Profit factor and the equity curve are computed from the
    # same bars, so PF > 1 must agree with a positive net sum. If they diverge,
    # the position mask has drifted out of alignment with the returns and every
    # per-trade statistic here is describing different bars from the curve.
    net = float(traded.sum()) if len(traded) else 0.0
    coherent = True
    if len(traded) and gross_loss > 0:
        coherent = (profit_factor > 1.0) == (net > 0.0)

    return {
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "exposure": float(np.mean(positions[: len(r)] != 0)),
        "cagr": cagr,
        "n_bars": int(len(r)),
        "coherent": bool(coherent),
    }


def equity_curve(returns: pd.Series) -> pd.Series:
    return (1.0 + returns.fillna(0.0)).cumprod()
