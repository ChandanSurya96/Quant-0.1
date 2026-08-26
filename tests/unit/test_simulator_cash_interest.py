"""Unit tests for cash interest, discrete shares, and slippage in PortfolioSimulator."""

import numpy as np
import pandas as pd
import pytest
from quant.portfolio.simulator import PortfolioSimulator


def test_simulator_credits_cash_interest_on_flat_portfolio():
    dates = pd.date_range("2020-01-01", periods=252, freq="B")
    prices_df = pd.DataFrame({"SPY": np.linspace(300, 310, 252)}, index=dates)
    # Zero weights (100% cash)
    target_weights_df = pd.DataFrame({"SPY": 0.0}, index=dates)

    sim = PortfolioSimulator(
        initial_cash=100_000.0,
        cost_bps=0.0,
        slippage_bps=0.0,
        borrow_cost_annual_bps=0.0,
        risk_free_rate_annual=0.05,  # 5% annual interest
    )
    res = sim.run(target_weights_df, prices_df, start_idx=0)
    final_nav = res["metrics"]["final_nav"]

    # Final NAV should reflect ~5% interest earned on cash
    assert final_nav > 104_500.0
    assert res["metrics"]["total_return"] > 0.045


def test_simulator_includes_slippage_and_discrete_shares():
    dates = pd.date_range("2020-01-01", periods=100, freq="B")
    prices_df = pd.DataFrame({"SPY": np.linspace(300, 350, 100)}, index=dates)
    target_weights_df = pd.DataFrame({"SPY": 0.50}, index=dates)

    sim = PortfolioSimulator(
        initial_cash=100_000.0,
        cost_bps=10.0,
        slippage_bps=2.5,
        discrete_shares=True,
    )
    res = sim.run(target_weights_df, prices_df, start_idx=0)
    assert res["metrics"]["total_costs"] > 0
    assert "gross_sharpe" in res["metrics"]
    assert "excess_sharpe" in res["metrics"]
    assert "sharpe_se" in res["metrics"]
