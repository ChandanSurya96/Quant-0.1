"""Translation mapper between Polygon.io aggregates and Quant market data frames."""

from __future__ import annotations

import pandas as pd

from .models import PolygonAggregateBar

OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


class PolygonMapper:
    """Translates between Polygon aggregate representations and domain OHLCV frames."""

    @classmethod
    def to_ohlcv_frame(cls, bars: list[PolygonAggregateBar]) -> pd.DataFrame:
        """Converts aggregate bars to an OHLCV DataFrame indexed by tz-naive trading date.

        Polygon reports the aggregate window start as Unix epoch milliseconds in UTC. The
        index is normalised to midnight and stripped of tz so it aligns with the frames the
        other providers return.
        """
        if not bars:
            return pd.DataFrame(columns=list(OHLCV_COLUMNS))

        frame = pd.DataFrame(
            {
                "Open": [b.open for b in bars],
                "High": [b.high for b in bars],
                "Low": [b.low for b in bars],
                "Close": [b.close for b in bars],
                "Volume": [b.volume for b in bars],
            },
            index=cls.to_index(bars),
        )
        frame = frame[~frame.index.duplicated(keep="last")]
        return frame.sort_index()

    @classmethod
    def to_close_series(cls, bars: list[PolygonAggregateBar]) -> pd.Series:
        """Converts aggregate bars to a Close price Series indexed by tz-naive trading date."""
        if not bars:
            return pd.Series(dtype="float64")
        return cls.to_ohlcv_frame(bars)["Close"]

    @staticmethod
    def to_index(bars: list[PolygonAggregateBar]) -> pd.DatetimeIndex:
        """Builds the tz-naive normalised DatetimeIndex for a list of aggregate bars."""
        return (
            pd.to_datetime([b.timestamp_ms for b in bars], unit="ms", utc=True)
            .tz_localize(None)
            .normalize()
        )
