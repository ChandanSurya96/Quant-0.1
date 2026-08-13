"""Equity curve rendering. Headless (Agg) so it works over SSH and in CI."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .backtest import equity_curve  # noqa: E402


def plot_equity(
    curves: dict[str, pd.Series],
    out_path: Path,
    title: str,
) -> Path:
    """curves: display name -> per-bar return series."""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 7.5), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]}
    )

    styles = {
        "Buy & hold": dict(color="#8c8c8c", lw=1.4, ls="--"),
        "Legacy (overlapping matrix)": dict(color="#d1701c", lw=1.5),
        "Markov 2.0 (stride matrix)": dict(color="#1f6fb4", lw=1.9),
    }

    for name, rets in curves.items():
        eq = equity_curve(rets)
        ax1.plot(eq.index, eq.to_numpy(), label=name, **styles.get(name, {}))
        peak = np.maximum.accumulate(eq.to_numpy())
        dd = (eq.to_numpy() - peak) / peak
        ax2.plot(eq.index, dd * 100.0, label=name, **styles.get(name, {}))

    ax1.set_yscale("log")
    ax1.set_ylabel("Growth of 1 (log)")
    ax1.set_title(title)
    ax1.legend(loc="upper left", frameon=False, fontsize=9)
    ax1.grid(alpha=0.25)

    ax2.set_ylabel("Drawdown (%)")
    ax2.grid(alpha=0.25)
    ax2.axhline(0, color="#444", lw=0.8)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path
