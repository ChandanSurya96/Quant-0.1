"""Fail-closed data validation gate for market data sanitization."""

from __future__ import annotations

import warnings
import numpy as np
import pandas as pd

from ..core.enums import ExecutionMode
from ..core.exceptions import AnomalyGapError, FailClosedDataError

CORP_ACTION_THRESHOLD = 0.15


class DataValidationGate:
    """Validates and sanitizes market data payloads under a fail-closed policy."""

    @staticmethod
    def filter_vendor_artifacts(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        """Identifies and drops non-trading vendor artifact bars.

        Condition: Volume == 0 AND Open == High == Low == Close.
        """
        if df.empty:
            return df.copy(), []

        df_clean = df.copy()
        vol_zero = (
            df_clean["Volume"] == 0
            if "Volume" in df_clean.columns
            else pd.Series(False, index=df_clean.index)
        )

        cols_check = [c for c in ("Open", "High", "Low", "Close") if c in df_clean.columns]
        if len(cols_check) >= 2:
            price_flat = df_clean[cols_check].min(axis=1) == df_clean[cols_check].max(axis=1)
        else:
            price_flat = pd.Series(False, index=df_clean.index)

        artifact_mask = vol_zero & price_flat
        artifact_bars = df_clean[artifact_mask]
        dropped_dates = [str(pd.Timestamp(d).date()) for d in artifact_bars.index]

        if dropped_dates:
            warnings.warn(
                f"Dropped {len(dropped_dates)} vendor holiday artifacts on dates: {dropped_dates[:5]}",
                UserWarning,
                stacklevel=2,
            )

        return df_clean[~artifact_mask].copy(), dropped_dates

    @staticmethod
    def detect_anomalies(
        close_series: pd.Series,
        threshold: float = CORP_ACTION_THRESHOLD,
    ) -> list[dict]:
        """Detect single-bar price returns exceeding threshold."""
        if close_series.empty or len(close_series) < 2:
            return []
        
        returns = close_series.pct_change()
        hits = returns[returns.abs() >= threshold]
        
        anomalies = []
        for dt, ret in hits.items():
            anomalies.append({
                "date": str(pd.Timestamp(dt).date()),
                "return": float(ret),
                "threshold": threshold,
            })
        return anomalies

    @classmethod
    def validate_matrix(
        cls,
        df: pd.DataFrame,
        universe: list[str] | None = None,
        mode: ExecutionMode = ExecutionMode.RESEARCH,
        threshold: float = CORP_ACTION_THRESHOLD,
    ) -> pd.DataFrame:
        """Validates aligned close price matrix for a multi-asset universe.
        
        Enforces fail-closed rules:
        - Must not be empty.
        - Must contain all requested universe columns.
        - Must not contain all-NaN columns or Inf values.
        """
        if df is None or df.empty:
            raise FailClosedDataError("Market data payload is empty.")

        if universe is not None:
            missing = [t for t in universe if t not in df.columns]
            if missing:
                raise FailClosedDataError(
                    f"Market data missing {len(missing)} requested universe tickers: {missing}"
                )

        # Check for non-finite values
        clean_df = df.copy()
        if universe:
            clean_df = clean_df[universe]

        clean_df = clean_df.replace([np.inf, -np.inf], np.nan)
        clean_df = clean_df.ffill().dropna(how="all")

        if clean_df.empty:
            raise FailClosedDataError("All data rows were empty after cleaning.")

        for col in clean_df.columns:
            series = clean_df[col].dropna()
            if len(series) < 10:
                raise FailClosedDataError(f"Insufficient history for ticker {col!r}: {len(series)} bars.")
            
            # Check for anomalies if in PAPER or LIVE
            if mode in (ExecutionMode.PAPER, ExecutionMode.LIVE):
                anomalies = cls.detect_anomalies(series, threshold=threshold)
                if anomalies:
                    raise AnomalyGapError(
                        f"Unhandled price anomaly gap >= +/-{threshold*100:.0f}% detected for {col!r}: "
                        f"{anomalies}. Ingestion failed closed."
                    )

        return clean_df

    validate_universe_matrix = validate_matrix
