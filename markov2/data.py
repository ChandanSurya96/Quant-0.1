"""Data fetch, vendor artifact filtration, and corporate action manifest adjustments.

yfinance only - free, no key, no account.
"""

from __future__ import annotations

import json
import time
import warnings
from pathlib import Path

import pandas as pd

MANIFEST_PATH = Path(__file__).resolve().parent / "config" / "corporate_actions.json"


def filter_vendor_artifacts(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Identifies and removes non-trading vendor artifact bars.

    Condition: Volume == 0 AND Open == High == Low == Close.
    Action: Remove these bars from the dataset and log warning.
    """
    df = df.copy()
    if df.empty:
        return df, []

    vol_zero = df["Volume"] == 0 if "Volume" in df.columns else pd.Series(True, index=df.index)
    
    # Check Open == High == Low == Close
    cols_check = [c for c in ("Open", "High", "Low", "Close") if c in df.columns]
    if len(cols_check) >= 2:
        price_flat = (df[cols_check].min(axis=1) == df[cols_check].max(axis=1))
    else:
        price_flat = pd.Series(False, index=df.index)

    artifact_mask = vol_zero & price_flat
    artifact_bars = df[artifact_mask]
    dropped_dates = [str(pd.Timestamp(d).date()) for d in artifact_bars.index]

    if dropped_dates:
        msg = f"Dropped {len(dropped_dates)} vendor holiday artifacts on dates: {dropped_dates[:5]}"
        if len(dropped_dates) > 5:
            msg += f" ... (+{len(dropped_dates) - 5} more)"
        warnings.warn(msg, UserWarning)
        print(f"  ! {msg}")

    filtered_df = df[~artifact_mask].copy()
    return filtered_df, dropped_dates


def load_corporate_action_manifest(config_path: Path | str | None = None) -> dict:
    """Loads the Corporate Action Manifest JSON configuration file."""
    path = Path(config_path) if config_path else MANIFEST_PATH
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        warnings.warn(f"Failed to load corporate action manifest from {path}: {exc}", UserWarning)
        return {}


def apply_manifest_adjustments(df: pd.DataFrame, ticker: str, config_path: Path | str | None = None) -> pd.DataFrame:
    """Applies backward adjustments for known corporate events from the Manifest.

    For each event date t, applies adjustment_factor to Open, High, Low, Close
    and 1 / adjustment_factor to Volume for all rows preceding corporate action date t.
    """
    manifest = load_corporate_action_manifest(config_path)
    if ticker not in manifest or not manifest[ticker]:
        return df

    df = df.copy()
    idx = df.index
    price_cols = [c for c in ("Open", "High", "Low", "Close") if c in df.columns]

    for event in manifest[ticker]:
        event_date = event.get("date")
        adj_factor = float(event.get("adjustment_factor", 1.0))
        if not event_date or adj_factor <= 0 or adj_factor == 1.0:
            continue

        ts = pd.Timestamp(event_date)
        if idx.tz is not None and ts.tz is None:
            ts = ts.tz_localize(idx.tz)

        pos = int(idx.searchsorted(ts))
        if pos <= 0 or pos >= len(idx):
            continue

        if "Volume" in df.columns:
            df["Volume"] = df["Volume"].astype(float)
            df.iloc[:pos, df.columns.get_loc("Volume")] /= adj_factor
        if price_cols:
            df.iloc[:pos, [df.columns.get_loc(c) for c in price_cols]] *= adj_factor

    return df


def fetch(ticker: str, years: int = 10, retries: int = 2, pause: int = 20) -> pd.DataFrame:
    """Daily OHLCV. Returns a flat-column frame with Open/High/Low/Close/Volume, vendor artifacts removed, and manifest adjusted."""
    import yfinance as yf

    end = pd.Timestamp.now("UTC").normalize()
    start = end - pd.DateOffset(years=years)

    df = pd.DataFrame()
    for attempt in range(1, retries + 1):
        try:
            df = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ! yfinance error on attempt {attempt}: {exc}")
            df = pd.DataFrame()
        if not df.empty:
            break
        if attempt < retries:
            print(f"  ! empty response - retrying in {pause}s")
            time.sleep(pause)

    if df.empty:
        raise RuntimeError(
            f"yfinance returned no data for {ticker!r} after {retries} attempts. "
            "Yahoo may be rate-limiting, or the symbol may be wrong."
        )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    df_clean = df[keep].dropna(subset=["Close"]).copy()

    # 1. Filter Vendor Holiday Artifacts
    df_clean, _ = filter_vendor_artifacts(df_clean)

    # 2. Apply Deterministic Corporate Action Manifest Adjustments
    df_clean = apply_manifest_adjustments(df_clean, ticker)

    return df_clean


def splice(df: pd.DataFrame, dates: list[str]) -> tuple[pd.DataFrame, list[dict]]:
    """Neutralise corporate-action gaps that the feed failed to adjust.

    Standard treatment: back-adjust all prior prices by the gap ratio so the
    event-day return becomes zero and the series is economically continuous.
    """
    df = df.copy()
    applied = []
    idx = df.index
    for d in dates:
        ts = pd.Timestamp(d)
        if idx.tz is not None and ts.tz is None:
            ts = ts.tz_localize(idx.tz)
        pos = int(idx.searchsorted(ts))
        if pos <= 0 or pos >= len(idx):
            applied.append({"date": str(d), "ok": False, "why": "outside data range"})
            continue
        prev_c = float(df["Close"].iloc[pos - 1])
        this_c = float(df["Close"].iloc[pos])
        if prev_c <= 0:
            applied.append({"date": str(d), "ok": False, "why": "non-positive prior close"})
            continue
        ratio = this_c / prev_c
        cols = [c for c in ("Open", "High", "Low", "Close") if c in df.columns]
        df.iloc[:pos, [df.columns.get_loc(c) for c in cols]] *= ratio
        applied.append(
            {
                "date": str(idx[pos].date()),
                "ok": True,
                "raw_move_pct": (ratio - 1.0) * 100.0,
                "ratio": ratio,
            }
        )
    return df, applied
