"""Accounting invariant tests for physical share and cash portfolio simulator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.portfolio.simulator import PortfolioSimulator


# ----------------------------------------------------------- 1. Buy Accounting
def test_buy_accounting_cash_and_holdings():
    # Start: $100,000 cash. Buy 100 shares of SPY at $400.
    # Traded Notional = $40,000. Cost @ 10 bps = $40.
    # Post-Trade Cash = $100,000 - $40,040 = $59,960.
    # Holding Value = 100 * $400 = $40,000.
    # Post-Trade NAV = $59,960 + $40,000 = $99,960.
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    prices_df = pd.DataFrame({"SPY": [400.0, 400.0, 400.0]}, index=dates)
    # Target weight: 0.40 on Day 0, rebalance at Day 1
    target_weights_df = pd.DataFrame({"SPY": [0.40, 0.40, 0.40]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=1, start_idx=0)

    # Day 1 is rebalance day (uses Day 0 target weight)
    cash_day1 = res["cash"].iloc[1]
    shares_day1 = res["holdings"]["SPY"].iloc[1]
    nav_day1 = res["nav"].iloc[1]

    assert shares_day1 == pytest.approx(100.0, abs=1e-5)  # $40,000 / $400
    assert cash_day1 == pytest.approx(59_960.0, abs=1e-5)  # $100k - $40k - $40
    assert nav_day1 == pytest.approx(99_960.0, abs=1e-5)   # Cash + Holdings MV


# ---------------------------------------------------------- 2. Sell Accounting
def test_sell_accounting_cash_and_holdings():
    # Day 1: Buy 100 shares at $400 (Target = 0.40).
    # Day 2: Reduce target to 0.20 (50 shares). Sells 50 shares at $400.
    # Sold Notional = 50 * $400 = $20,000. Cost @ 10 bps = $20.
    # Cash increases by $20,000 - $20 = $19,980.
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    prices_df = pd.DataFrame({"SPY": [400.0, 400.0, 400.0, 400.0]}, index=dates)
    target_weights_df = pd.DataFrame({"SPY": [0.40, 0.20, 0.20, 0.20]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=1, start_idx=0)

    shares_day2 = res["holdings"]["SPY"].iloc[2]
    cash_day2 = res["cash"].iloc[2]
    nav_day2 = res["nav"].iloc[2]

    assert shares_day2 == 49.0  # Exact discrete shares: floor(0.20 * 99,960 / 400) = 49.0
    assert cash_day2 > res["cash"].iloc[1]  # Cash increased from sale proceeds
    assert abs(nav_day2 - (cash_day2 + shares_day2 * 400.0)) < 1e-4  # NAV conservation holds


# ---------------------------------------------------- 3. Open Short Accounting
def test_open_short_accounting():
    # Target weight = -0.50 (Short $50,000 of TLT at $100 = -500 shares).
    # Short sale proceeds = +$50,000. Transaction cost @ 10 bps = $50.
    # Cash becomes $100,000 + $50,000 - $50 = $149,950.
    # Shares = -500. Holding MV = -500 * $100 = -$50,000 (liability).
    # NAV = $149,950 + (-$50,000) = $99,950.
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    prices_df = pd.DataFrame({"TLT": [100.0, 100.0, 100.0]}, index=dates)
    target_weights_df = pd.DataFrame({"TLT": [-0.50, -0.50, -0.50]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=1, start_idx=0)

    shares_day1 = res["holdings"]["TLT"].iloc[1]
    cash_day1 = res["cash"].iloc[1]
    nav_day1 = res["nav"].iloc[1]

    assert shares_day1 == pytest.approx(-500.0, abs=1e-4)
    assert cash_day1 == pytest.approx(149_950.0, abs=1e-4)
    assert nav_day1 == pytest.approx(99_950.0, abs=1e-4)


# --------------------------------------------------- 4. Cover Short Accounting
def test_cover_short_accounting():
    # Day 1: Short 500 shares of TLT at $100.
    # Day 2: Target weight becomes 0.0 (Cover all 500 shares at $100).
    # Cover cost = 500 * $100 = $50,000. Cost @ 10 bps = $50.
    # Cash decreases by $50,000 + $50 = $50,050.
    # Shares become 0.0. Holding MV = $0.0.
    # NAV = $149,950 - $50,050 = $99,900.
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    prices_df = pd.DataFrame({"TLT": [100.0, 100.0, 100.0, 100.0]}, index=dates)
    target_weights_df = pd.DataFrame({"TLT": [-0.50, 0.0, 0.0, 0.0]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=1, start_idx=0)

    shares_day2 = res["holdings"]["TLT"].iloc[2]
    cash_day2 = res["cash"].iloc[2]
    nav_day2 = res["nav"].iloc[2]

    assert shares_day2 == pytest.approx(0.0, abs=1e-6)
    assert cash_day2 == pytest.approx(99_900.0, abs=1e-4)
    assert nav_day2 == pytest.approx(99_900.0, abs=1e-4)


# ---------------------------------------------------- 5. NAV Conservation Invariant
def test_nav_conservation_invariant_every_bar():
    # Run a 100-bar multi-asset simulation with volatile price paths.
    # Assert that NAV == Cash + sum(Shares * Price) on 100% of bars.
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=100, freq="D")
    p1 = 100.0 * np.exp(np.cumsum(np.random.normal(0, 0.02, 100)))
    p2 = 50.0 * np.exp(np.cumsum(np.random.normal(0, 0.015, 100)))
    prices_df = pd.DataFrame({"A": p1, "B": p2}, index=dates)

    # Alternate target weights
    w_a = np.where(np.arange(100) % 2 == 0, 0.40, -0.30)
    w_b = np.where(np.arange(100) % 2 == 0, -0.40, 0.30)
    target_weights_df = pd.DataFrame({"A": w_a, "B": w_b}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=5, start_idx=0)

    for dt in res["index"]:
        nav = res["nav"].loc[dt]
        cash = res["cash"].loc[dt]
        q_a = res["holdings"]["A"].loc[dt]
        q_b = res["holdings"]["B"].loc[dt]
        px_a = prices_df["A"].loc[dt]
        px_b = prices_df["B"].loc[dt]

        expected_nav = cash + (q_a * px_a) + (q_b * px_b)
        assert abs(nav - expected_nav) < 1e-6, f"NAV mismatch on {dt}: {nav} vs {expected_nav}"


# -------------------------------------------------- 6. Share Conservation Invariant
def test_share_conservation_invariant():
    dates = pd.date_range("2026-01-01", periods=20, freq="D")
    prices_df = pd.DataFrame({"SPY": np.linspace(400, 420, 20)}, index=dates)
    target_weights_df = pd.DataFrame({"SPY": [0.30] * 10 + [0.50] * 10}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=10, start_idx=0)

    trades = res["trades"]
    # Should have trade on bar 10 (rebalance)
    total_delta_q = trades["delta_shares"].sum()
    final_shares = res["holdings"]["SPY"].iloc[-1]
    assert final_shares == pytest.approx(total_delta_q, abs=1e-4)


# --------------------------------------------------------- 7. Position Closure
def test_position_closure_to_zero():
    dates = pd.date_range("2026-01-01", periods=5, freq="D")
    prices_df = pd.DataFrame({"SPY": [100.0, 105.0, 110.0, 115.0, 120.0]}, index=dates)
    # Day 1: Buy (target=0.50), Day 2: Close completely (target=0.0)
    target_weights_df = pd.DataFrame({"SPY": [0.50, 0.0, 0.0, 0.0, 0.0]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=1, start_idx=0)

    # Day 2 is rebalance day applying Day 1 target (0.0)
    shares_day2 = res["holdings"]["SPY"].iloc[2]
    assert shares_day2 == 0.0


# --------------------------------------------------------- 8. Short Borrow Cost
def test_short_borrow_cost_deduction():
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    prices_df = pd.DataFrame({"SPY": [100.0] * 10}, index=dates)
    target_weights_df = pd.DataFrame({"SPY": [-0.50] * 10}, index=dates)

    # Run with 0 borrow cost vs 500 bps borrow cost
    sim_0 = PortfolioSimulator(initial_cash=100_000.0, cost_bps=0.0, borrow_cost_annual_bps=0.0)
    res_0 = sim_0.run(target_weights_df, prices_df, rebalance_freq=1, start_idx=0)

    sim_500 = PortfolioSimulator(initial_cash=100_000.0, cost_bps=0.0, borrow_cost_annual_bps=500.0)
    res_500 = sim_500.run(target_weights_df, prices_df, rebalance_freq=1, start_idx=0)

    nav_0 = res_0["nav"].iloc[-1]
    nav_500 = res_500["nav"].iloc[-1]
    # NAV with 500 bps borrow fee must be strictly lower than 0 bps borrow fee
    assert nav_500 < nav_0


# --------------------------------------------------------- 9. Friction Monotonicity
def test_friction_monotonicity_invariant():
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    prices_df = pd.DataFrame({"SPY": np.linspace(100, 110, 10)}, index=dates)
    target_weights_df = pd.DataFrame({"SPY": [0.30, -0.30, 0.40, -0.40, 0.20] * 2}, index=dates)

    sim_gross = PortfolioSimulator(initial_cash=100_000.0, cost_bps=0.0)
    res_gross = sim_gross.run(target_weights_df, prices_df, rebalance_freq=2, start_idx=0)

    sim_net = PortfolioSimulator(initial_cash=100_000.0, cost_bps=20.0)
    res_net = sim_net.run(target_weights_df, prices_df, rebalance_freq=2, start_idx=0)

    assert res_gross["nav"].iloc[-1] > res_net["nav"].iloc[-1]

