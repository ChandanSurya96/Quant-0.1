"""Dataset splits for walk-forward evaluation (TRAIN, VALIDATION, TRUE_OOS).

Prevents future data leakage by strictly partitioning timestamps chronologically.
"""

from __future__ import annotations

import pandas as pd


def get_splits(
    df_or_series: pd.DataFrame | pd.Series | pd.Index,
    train_pct: float = 0.60,
    val_pct: float = 0.20,
) -> dict[str, pd.Index]:
    """Partition dates into TRAIN, VALIDATION, and TRUE_OOS chronologically.

    Args:
        df_or_series: Pandas object or Index containing time series data.
        train_pct: Proportion of total samples allocated to TRAIN (default 0.60).
        val_pct: Proportion of total samples allocated to VALIDATION (default 0.20).

    Returns:
        Dict with keys 'TRAIN', 'VALIDATION', 'TRUE_OOS', each containing a DatetimeIndex.
    """
    if isinstance(df_or_series, (pd.DataFrame, pd.Series)):
        index = df_or_series.index
    else:
        index = df_or_series

    n = len(index)
    train_end = int(n * train_pct)
    val_end = int(n * (train_pct + val_pct))

    train_idx = index[:train_end]
    val_idx = index[train_end:val_end]
    oos_idx = index[val_end:]

    return {
        "TRAIN": train_idx,
        "VALIDATION": val_idx,
        "TRUE_OOS": oos_idx,
    }
