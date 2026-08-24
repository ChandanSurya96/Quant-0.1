"""Unit tests for adversarial audit components and simulation modes."""

import numpy as np
import pandas as pd
import pytest
from scripts.run_adversarial_cand001_audit import run_simulation_engine


def test_adversarial_simulation_modes_deterministic():
    dates = pd.date_range("2020-01-01", periods=800, freq="D")
    tickers = ["SPY", "TLT", "UUP", "FXE"]
    rng = np.random.default_rng(42)
    p_data = {t: 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 800))) for t in tickers}
    df_close = pd.DataFrame(p_data, index=dates)

    # 1. Raw Momentum
    res_raw = run_simulation_engine(df_close, mom_mode="RAW", start_idx=756)
    assert "sharpe" in res_raw
    assert "cagr" in res_raw
    assert len(res_raw["returns"]) == 800 - 756

    # 2. Skip-Month Momentum
    res_skip = run_simulation_engine(df_close, mom_mode="SKIP_1M", start_idx=756)
    assert "sharpe" in res_skip

    # 3. Asymmetric Short Mode
    res_asym = run_simulation_engine(df_close, mom_mode="ASYMMETRIC_SHORT", start_idx=756)
    assert "sharpe" in res_asym
    # Asymmetric short should have lower absolute short exposure
    weights = res_asym["target_weights"]
    short_w = weights[weights < 0].abs()
    assert float(short_w.sum().sum()) <= float(res_raw["target_weights"][res_raw["target_weights"] < 0].abs().sum().sum()) + 1e-4
