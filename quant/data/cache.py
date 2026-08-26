"""On-disk market data caching layer for offline reproducibility."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import pandas as pd


class MarketDataCache:
    """Provides local on-disk caching of raw and aligned market data panels."""

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        if cache_dir is None:
            self.cache_dir = Path(__file__).resolve().parent.parent.parent / "data" / "cache"
        else:
            self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _compute_key(self, universe: list[str], start_date: str, end_date: str, provider: str) -> str:
        payload = {
            "universe": sorted(universe),
            "start": str(start_date),
            "end": str(end_date),
            "provider": provider,
        }
        raw_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def get(self, universe: list[str], start_date: str, end_date: str, provider: str) -> pd.DataFrame | None:
        """Retrieves cached DataFrame if present."""
        key = self._compute_key(universe, start_date, end_date, provider)
        file_path = self.cache_dir / f"{key}.parquet"
        if file_path.exists():
            try:
                df = pd.read_parquet(file_path)
                return df
            except Exception:
                return None
        return None

    def put(self, df: pd.DataFrame, universe: list[str], start_date: str, end_date: str, provider: str) -> Path:
        """Saves DataFrame to on-disk parquet cache."""
        key = self._compute_key(universe, start_date, end_date, provider)
        file_path = self.cache_dir / f"{key}.parquet"
        df.to_parquet(file_path)
        return file_path
