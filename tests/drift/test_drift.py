"""Unit tests for holding weight drift and rebalance timing invariants."""

from __future__ import annotations

import pandas as pd
import pytest

from quant.portfolio.simulator import PortfolioSimulator


# ----------------------------------------------- 1. Natural Price-Driven Drift
def test_price_driven_weight_drift_on_holding_days():
    # Day 0: Target = 50% Asset A, 50% Asset B.
    # Day 1: Rebalance executes. Buy 500 shares of A ($100) and 500 shares of B ($100).
    #        Post-trade weights = 50% A, 50% B.
    # Day 2: Holding Day (No Rebalance).
    #        Asset A jumps to $200 (100% gain). Asset B stays at $100.
    #        MV_A = 500 * $200 = $100,000. MV_B = 500 * $100 = $50,000.
    #        NAV = $150,000 (ignoring small initial cost).
    #        Realized Weight A = $100,000 / $150,000 = 66.67%.
    #        Realized Weight B = $50,000 / $150,000 = 33.33%.
    #        Assertion: Zero trades executed on Day 2; realized weights naturally drifted.
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    prices_df = pd.DataFrame(
        {
            "A": [100.0, 100.0, 200.0, 200.0],
            "B": [100.0, 100.0, 100.0, 100.0],
        },
        index=dates,
    )
    # Target weights constant at 50/50
    target_weights_df = pd.DataFrame(
        {
            "A": [0.50, 0.50, 0.50, 0.50],
            "B": [0.50, 0.50, 0.50, 0.50],
        },
        index=dates,
    )

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=0.0)  # Zero cost for clean math
    # Rebalance only every 10 days, so Day 2 and Day 3 are holding days
    res = sim.run(target_weights_df, prices_df, rebalance_freq=10, start_idx=0)

    # Day 1 is Rebalance
    w_a_day1 = res["realized_weights"]["A"].iloc[1]
    w_b_day1 = res["realized_weights"]["B"].iloc[1]
    assert w_a_day1 == pytest.approx(0.50, abs=1e-3)
    assert w_b_day1 == pytest.approx(0.50, abs=1e-3)

    # Day 2 is Holding Day (Price of A doubled)
    w_a_day2 = res["realized_weights"]["A"].iloc[2]
    w_b_day2 = res["realized_weights"]["B"].iloc[2]
    assert w_a_day2 == pytest.approx(2.0 / 3.0, abs=1e-3)  # 66.67%
    assert w_b_day2 == pytest.approx(1.0 / 3.0, abs=1e-3)  # 33.33%

    # Assert NO trades executed on Day 2 or Day 3
    trades = res["trades"]
    trades_day2 = trades[trades["date"] == dates[2]]
    assert len(trades_day2) == 0, "No trades should occur on holding days"


# -------------------------------------- 2. Zero Trades During Holding Period
def test_zero_trades_during_holding_period():
    # 60-day run with 21-day rebalance frequency.
    # Rebalances should ONLY occur on bar 21, bar 42.
    # Bars 1..20, 22..41, 43..59 must have ZERO trades.
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    prices_df = pd.DataFrame({"SPY": [100.0 + i for i in range(60)]}, index=dates)
    target_weights_df = pd.DataFrame({"SPY": [0.50] * 60}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=21, start_idx=0)

    trades = res["trades"]
    trade_dates = trades["date"].unique()

    expected_rebalance_dates = [dates[1], dates[22], dates[43]]
    for td in trade_dates:
        assert td in expected_rebalance_dates, f"Unexpected trade on non-rebalance date {td}"


# --------------------------------------------- 3. Exact Rebalance Share Delta
def test_exact_rebalance_share_delta():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    prices_df = pd.DataFrame({"SPY": [100.0, 100.0, 100.0]}, index=dates)
    # Day 0: Target = 0.50 ($50,000 / $100 = 500 shares)
    # Day 1: Target = 0.80 ($80,000 / $100 = 800 shares) -> Delta should be +300 shares
    target_weights_df = pd.DataFrame({"SPY": [0.50, 0.80, 0.80]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=0.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=1, start_idx=0)

    trades = res["trades"]
    assert len(trades) == 2
    assert trades.iloc[0]["delta_shares"] == pytest.approx(500.0, abs=1e-4)
    assert trades.iloc[1]["delta_shares"] == pytest.approx(300.0, abs=1e-4)


# ------------------------------------------------ 4. 1-Bar Execution Lag Test
def test_execution_lag_1_bar():
    # Signal changes on Day 1. Trade must execute on Day 2 using Day 2 price.
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    prices_df = pd.DataFrame({"SPY": [100.0, 100.0, 150.0, 150.0]}, index=dates)
    # Day 0: Target 0.0, Day 1: Target 0.50 (Signal emitted at Day 1 close)
    target_weights_df = pd.DataFrame({"SPY": [0.0, 0.50, 0.50, 0.50]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=0.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=1, start_idx=0)

    trades = res["trades"]
    # Day 1 trade uses Day 0 target (0.0 -> no trade).
    # Day 2 trade uses Day 1 target (0.50) executed at Day 2 price ($150).
    assert len(trades) == 1
    assert trades.iloc[0]["date"] == dates[2]
    assert trades.iloc[0]["fill_price"] == 150.0
    assert trades.iloc[0]["delta_shares"] == pytest.approx(int(100_000 * 0.50 / 150.0), abs=1e-4)


# --------------------------------------------- 5. Deterministic Repeatability
def test_deterministic_repeatability():
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    prices_df = pd.DataFrame({"SPY": [100.0 + i for i in range(30)], "TLT": [100.0 - i * 0.5 for i in range(30)]}, index=dates)
    target_weights_df = pd.DataFrame({"SPY": [0.4] * 30, "TLT": [-0.3] * 30}, index=dates)

    sim1 = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    sim2 = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)

    res1 = sim1.run(target_weights_df, prices_df, rebalance_freq=7, start_idx=0)
    res2 = sim2.run(target_weights_df, prices_df, rebalance_freq=7, start_idx=0)

    pd.testing.assert_series_equal(res1["nav"], res2["nav"])
    pd.testing.assert_series_equal(res1["cash"], res2["cash"])
