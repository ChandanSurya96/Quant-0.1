"""Unit tests for Data Integrity module, Manifest Splicer, Vendor Artifact Filtration, and DataIntegrityError."""

from __future__ import annotations

import pandas as pd
import pytest

from markov2.data import (
    apply_manifest_adjustments,
    filter_vendor_artifacts,
    load_corporate_action_manifest,
)
from markov2.gates import (
    CORP_ACTION_THRESHOLD,
    DataIntegrityError,
    detect_corporate_actions,
    validate_data_integrity,
)


def test_corp_action_threshold_reduced_to_15_percent():
    assert CORP_ACTION_THRESHOLD == 0.15


def test_filter_vendor_artifacts():
    dates = pd.date_range("2025-01-01", periods=5, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0, 102.0, 105.0],
            "High": [100.0, 103.0, 102.0, 102.0, 106.0],
            "Low": [100.0, 100.5, 102.0, 102.0, 104.0],
            "Close": [100.0, 102.0, 102.0, 102.0, 105.5],
            "Volume": [0, 1000, 0, 0, 2000],  # Bar 0 and Bar 2, 3 are zero vol
        },
        index=dates,
    )
    # Bar 0 (Open==High==Low==Close==100, Vol==0) and Bar 2,3 (Open==High==Low==Close==102, Vol==0) are vendor artifacts
    filtered_df, dropped_dates = filter_vendor_artifacts(df)

    assert len(filtered_df) == 2
    assert len(dropped_dates) == 3
    assert "2025-01-01" in dropped_dates
    assert "2025-01-03" in dropped_dates
    assert "2025-01-04" in dropped_dates


def test_load_corporate_action_manifest():
    manifest = load_corporate_action_manifest()
    assert "SUZLON.NS" in manifest
    assert "TMPV.NS" in manifest
    assert manifest["SUZLON.NS"][0]["type"] == "RIGHTS_ISSUE"
    assert manifest["SUZLON.NS"][0]["adjustment_factor"] == 0.93
    assert manifest["TMPV.NS"][0]["type"] == "DEMERGER"
    assert manifest["TMPV.NS"][0]["adjustment_factor"] == 0.5985


def test_apply_manifest_adjustments():
    dates = pd.date_range("2025-10-10", periods=5, freq="D")
    df = pd.DataFrame(
        {
            "Open": [100.0, 100.0, 100.0, 60.0, 61.0],
            "High": [102.0, 102.0, 102.0, 62.0, 63.0],
            "Low": [98.0, 98.0, 98.0, 58.0, 59.0],
            "Close": [100.0, 100.0, 100.0, 60.0, 60.0],
            "Volume": [1000, 1000, 1000, 1000, 1000],
        },
        index=dates,
    )

    adjusted_df = apply_manifest_adjustments(df, "TMPV.NS")

    # For TMPV.NS, adjustment factor is 0.5985 on 2025-10-14 (which is index pos 4 in dates)
    # Preceding rows (index 0..3) should be multiplied by 0.5985
    assert adjusted_df["Close"].iloc[0] == pytest.approx(100.0 * 0.5985)
    assert adjusted_df["Close"].iloc[3] == pytest.approx(60.0 * 0.5985)
    assert adjusted_df["Close"].iloc[4] == 60.0  # On/after event day (pos 4), untouched
    assert adjusted_df["Volume"].iloc[0] == pytest.approx(1000 / 0.5985)


def test_validate_data_integrity_raises_data_integrity_error():
    dates = pd.date_range("2025-01-01", periods=5, freq="D")
    close = pd.Series([100.0, 101.0, 80.0, 81.0, 82.0], index=dates)  # -20.79% gap on bar 2

    # Should detect gap since threshold is 15% (0.15)
    actions = detect_corporate_actions(close, threshold=0.15)
    assert len(actions) == 1
    assert actions[0]["date"] == "2025-01-03"

    with pytest.raises(DataIntegrityError, match="Unhandled price anomaly gap"):
        validate_data_integrity(close, ticker="TEST.NS", threshold=0.15, raise_on_anomaly=True)
