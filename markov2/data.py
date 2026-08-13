"""Data fetch. yfinance only - free, no key, no account."""

from __future__ import annotations

import time

import pandas as pd


def fetch(ticker: str, years: int = 10, retries: int = 2, pause: int = 20) -> pd.DataFrame:
    """Daily OHLCV. Returns a flat-column frame with Open/High/Low/Close/Volume."""
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
    return df[keep].dropna(subset=["Close"])


def splice(df: pd.DataFrame, dates: list[str]) -> tuple[pd.DataFrame, list[dict]]:
    """Neutralise corporate-action gaps that the feed failed to adjust.

    A demerger, spin-off or unadjusted split shows up as one enormous bar that
    no holder actually experienced - value left the listed entity, it was not
    lost. Left in, that bar dominates every window that contains it and invents
    a regime.

    Standard treatment: back-adjust all prior prices by the gap ratio so the
    event-day return becomes zero and the series is economically continuous.
    Pre-event history is then expressed in post-event units.
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
