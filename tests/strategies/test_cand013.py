"""Unit tests for CAND-013 Asymmetric Vol Targeting & Turnover Hysteresis Engine."""

import numpy as np
import pandas as pd
import pytest
from scripts.run_cand013_research import (
    apply_volatility_targeting,
    compute_metrics,
    generate_sp500_robust_panel,
)
from quant.pairs.backtest import YalePairsBacktester


def test_apply_volatility_targeting_no_leverage_above_1():
    dates = pd.date_range("2020-01-01", periods=100, freq="B")
    np.random.seed(42)
    # Low-volatility return series (approx 4% vol)
    rets = pd.Series(np.random.normal(0.0002, 0.0025, size=100), index=dates)
    targeted_rets, scaling = apply_volatility_targeting(rets, target_vol=0.10, lookback=21)
    
    assert len(targeted_rets) == 100
    assert (scaling <= 1.0).all()  # Strict constraint: No leverage above 1.0x
    assert (scaling >= 0.0).all()


def test_cand013_exit_hysteresis_backtester():
    df_p, df_v = generate_sp500_robust_panel(n_bars=450, random_seed=42)
    bt = YalePairsBacktester(
        formation_bars=252,
        trading_bars=126,
        step_bars=21,
        top_m=10,
        entry_threshold_sigma=2.2,
        exit_threshold_sigma=0.50,
        wait_one_day=True,
        cost_bps=10.0,
    )
    res = bt.run(df_p, df_v)
    assert "daily_returns" in res
    assert "sharpe_net" in res
    assert len(res["daily_returns"]) > 0
