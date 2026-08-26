"""Authoritative provenance tracking for all research and backtest results."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def get_git_commit_sha() -> str:
    """Retrieves current Git commit SHA."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "UNKNOWN_COMMIT"


def get_git_dirty_flag(ignore_results: bool = True) -> bool:
    """Checks if current git working tree is dirty (ignoring output results/ artifacts by default)."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        if ignore_results:
            lines = [line for line in lines if not ("results/" in line or line.endswith(".json"))]
        return bool(lines)
    except Exception:
        return True


def compute_price_panel_hash(prices_df: pd.DataFrame) -> str:
    """Computes SHA-256 hash over price panel values and index."""
    if prices_df is None or prices_df.empty:
        return "EMPTY_PANEL"
    raw_bytes = prices_df.to_csv(index=True).encode("utf-8")
    return hashlib.sha256(raw_bytes).hexdigest()


def build_provenance_record(
    strategy_id: str,
    parameters: dict[str, Any],
    dataset_provider: str,
    universe: list[str],
    prices_df: pd.DataFrame,
    execution_mode: str = "RESEARCH",
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Constructs an immutable structured provenance dictionary."""
    start_date = str(prices_df.index[0]) if not prices_df.empty else "N/A"
    end_date = str(prices_df.index[-1]) if not prices_df.empty else "N/A"
    missing_count = int(prices_df.isna().sum().sum()) if not prices_df.empty else 0

    record = {
        "git_commit_sha": get_git_commit_sha(),
        "is_dirty": get_git_dirty_flag(),
        "utc_timestamp": datetime.now(timezone.utc).isoformat(),
        "strategy_id": strategy_id,
        "execution_mode": execution_mode,
        "parameters": parameters,
        "dataset_provider": dataset_provider,
        "universe": sorted(universe),
        "date_range": {"start": start_date, "end": end_date},
        "row_count": len(prices_df),
        "column_count": len(prices_df.columns) if not prices_df.empty else 0,
        "missing_values_count": missing_count,
        "price_panel_sha256": compute_price_panel_hash(prices_df),
        "metadata": extra_metadata or {},
    }
    return record
