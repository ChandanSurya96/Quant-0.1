"""Multi-asset data fetch and alignment for Macro strategy."""

from __future__ import annotations

import hashlib
import time
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

from quant.core.exceptions import FailClosedDataError

# Default 12-market universe from gaticc3939
DEFAULT_UNIVERSE = {
    'bonds': ['TLT', 'IEF', 'BNDX', 'IGOV'],
    'currencies': ['UUP', 'FXE', 'FXY', 'FXB'],
    'equities': ['SPY', 'EWJ', 'EFA', 'EEM'],
}


def get_tickers(universe: dict[str, list[str]] = None) -> list[str]:
    """Flatten the universe dictionary into a list of tickers."""
    if universe is None:
        universe = DEFAULT_UNIVERSE
    return [t for sublist in universe.values() for t in sublist]


def fetch_universe(
    tickers: list[str],
    years: int = 10,
    retries: int = 1,
    pause: int = 2,
    allow_synthetic_fallback: bool = False,
) -> pd.DataFrame:
    """Download daily Close prices for a list of tickers with fail-closed validation."""
    end = pd.Timestamp.now("UTC").normalize()
    start = end - pd.DateOffset(years=years)

    series_dict = {}
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            df_batch = yf.download(
                tickers,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
            if not df_batch.empty:
                if isinstance(df_batch.columns, pd.MultiIndex):
                    close_df = df_batch["Close"] if "Close" in df_batch.columns.get_level_values(0) else df_batch
                else:
                    close_df = df_batch
                for t in tickers:
                    if t in close_df.columns:
                        s = close_df[t].dropna()
                        if not s.empty:
                            series_dict[t] = s
                if len(series_dict) == len(tickers):
                    break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"    ! yfinance batch download exception on attempt {attempt}: {exc}")
        if attempt < retries and len(series_dict) < len(tickers):
            time.sleep(pause)

    if not series_dict or len(series_dict) < len(tickers):
        if not allow_synthetic_fallback:
            raise FailClosedDataError(
                f"yfinance returned incomplete data for {tickers} (retrieved {list(series_dict.keys())}, "
                f"last error: {last_error}). Ingestion failed closed."
            )
        warnings.warn(
            "SYNTHETIC / NON-PERFORMANCE EVIDENCE: yfinance rate limited; generating synthetic geometric random walks.",
            UserWarning,
            stacklevel=2,
        )
        print("    ! yfinance rate limited on all attempts. Falling back to synthetic data for non-performance exploration.")
        dates = pd.date_range(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), freq='B')
        for t in tickers:
            seed = int(hashlib.sha256(t.encode("utf-8")).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            rets = rng.normal(0.0002, 0.015, size=len(dates))
            prices = 100.0 * np.exp(np.cumsum(rets))
            series_dict[t] = pd.Series(prices, index=dates)

    df = pd.DataFrame(series_dict)
            
    # Forward fill to handle non-overlapping holidays (e.g. US vs Japan holidays)
    df = df.ffill()
    
    # Drop rows where all tickers are NaN
    df = df.dropna(how='all')
    
    return df


def approximate_carry(tickers: list[str]) -> pd.Series:
    """Baseline structural carry approximations aligned with reference implementation."""
    yields = {
        'TLT': 0.045, 'IEF': 0.040, 'BNDX': 0.030, 'IGOV': 0.025,
        'UUP': 0.045, 'FXE': 0.025, 'FXY': 0.005, 'FXB': 0.045,
        'SPY': 0.013, 'EWJ': 0.020, 'EFA': 0.030, 'EEM': 0.028,
        'GLD': 0.000, 'DBC': 0.000, 'USO': -0.050, 'CORN': -0.030,
    }
    return pd.Series({t: yields.get(t, 0.0) for t in tickers})
