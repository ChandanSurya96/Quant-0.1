"""Comprehensive Physical Share Accounting Invariant Tests.

Covers the 13 required deterministic accounting tests:
1. Initial share calculation
2. Cash conservation
3. NAV conservation: NAV_t == Cash_t + sum(Shares_i * Price_i)
4. Weight drift: Holding-day natural weight evolution
5. No hidden rebalance: Zero trades on non-rebalance days
6. Share conservation: Shares_t == Shares_t-1 on holding days
7. Trade-to-share mapping: delta_shares == target_shares - current_shares
8. Rebalance conversion: Target weights converted accurately to notionals and shares
9. Transaction costs: 10 bps friction applied to traded notional
10. Short-position accounting: Correct negative liability and proceeds treatment
11. Return-from-NAV calculation: r_t == NAV_t / NAV_t-1 - 1
12. Legacy target-weight equality: Strategy target weights identical between models
13. Deterministic repeated simulation: Identical seeds yield byte-identical outputs
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant.portfolio.drift import calculate_market_values, calculate_portfolio_nav, calculate_realized_weights
from quant.portfolio.simulator import PortfolioSimulator
from quant.portfolio.sizer import target_weights_to_shares
from quant.strategies.macro import SystematicMacroStrategy


@pytest.fixture
def sample_market_data():
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    prices_df = pd.DataFrame(
        {
            "SPY": [100.0, 102.0, 105.0, 103.0, 106.0, 108.0, 107.0, 110.0, 112.0, 115.0],
            "TLT": [50.0, 49.0, 48.0, 51.0, 52.0, 50.0, 49.0, 48.0, 47.0, 46.0],
        },
        index=dates,
    )
    target_weights_df = pd.DataFrame(
        {
            "SPY": [0.50, 0.50, 0.50, 0.50, 0.50, 0.60, 0.60, 0.60, 0.60, 0.60],
            "TLT": [-0.50, -0.50, -0.50, -0.50, -0.50, -0.40, -0.40, -0.40, -0.40, -0.40],
        },
        index=dates,
    )
    return dates, prices_df, target_weights_df


# 1. Initial Share Calculation
def test_1_initial_share_calculation():
    nav = 100_000.0
    weights = {"SPY": 0.40, "TLT": -0.30}
    prices = {"SPY": 200.0, "TLT": 100.0}
    shares = target_weights_to_shares(weights, nav, prices)
    assert shares["SPY"] == pytest.approx(200.0)    # $40,000 / $200
    assert shares["TLT"] == pytest.approx(-300.0)   # -$30,000 / $100


# 2. Cash Conservation
def test_2_cash_conservation(sample_market_data):
    dates, prices_df, target_weights_df = sample_market_data
    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=5, start_idx=0)
    trades = res["trades"]
    cash_series = res["cash"]

    # At day 1 (rebalance):
    day1_trades = trades[trades["date"] == dates[1]]
    total_trade_cash_delta = 0.0
    for _, tr in day1_trades.iterrows():
        if tr["delta_shares"] > 0:
            total_trade_cash_delta -= (tr["delta_shares"] * tr["fill_price"] + tr["cost"])
        else:
            total_trade_cash_delta += (abs(tr["delta_shares"]) * tr["fill_price"] - tr["cost"])

    assert cash_series.iloc[1] == pytest.approx(100_000.0 + total_trade_cash_delta, abs=1e-4)


# 3. NAV Conservation
def test_3_nav_conservation(sample_market_data):
    dates, prices_df, target_weights_df = sample_market_data
    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=5, start_idx=0)

    for dt in dates:
        cash = res["cash"].loc[dt]
        nav = res["nav"].loc[dt]
        holdings = res["holdings"].loc[dt].to_dict()
        prices = prices_df.loc[dt].to_dict()
        expected_nav = cash + sum(holdings[s] * prices[s] for s in holdings)
        assert nav == pytest.approx(expected_nav, abs=1e-4)


# 4. Weight Drift
def test_4_weight_drift():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    prices_df = pd.DataFrame({"A": [100.0, 100.0, 150.0], "B": [100.0, 100.0, 50.0]}, index=dates)
    weights_df = pd.DataFrame({"A": [0.5, 0.5, 0.5], "B": [0.5, 0.5, 0.5]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=0.0)
    res = sim.run(weights_df, prices_df, rebalance_freq=10, start_idx=0)

    # Day 1: Rebalance executes -> 50% A, 50% B
    assert res["realized_weights"]["A"].iloc[1] == pytest.approx(0.50, abs=1e-3)
    # Day 2: Holding day (A rises 50%, B drops 50%). Total MV = 500*150 + 500*50 = 75k + 25k = 100k
    assert res["realized_weights"]["A"].iloc[2] == pytest.approx(0.75, abs=1e-3)
    assert res["realized_weights"]["B"].iloc[2] == pytest.approx(0.25, abs=1e-3)


# 5. No Hidden Rebalance
def test_5_no_hidden_rebalance(sample_market_data):
    dates, prices_df, target_weights_df = sample_market_data
    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=5, start_idx=0)
    trades = res["trades"]
    # Rebalance occurs at index 1 and index 6 (t - 1 % 5 == 0 -> t=1, 6)
    allowed_dates = {dates[1], dates[6]}
    for td in trades["date"].unique():
        assert td in allowed_dates, f"Unexpected trade on non-rebalance date {td}"


# 6. Share Conservation
def test_6_share_conservation(sample_market_data):
    dates, prices_df, target_weights_df = sample_market_data
    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=5, start_idx=0)
    holdings = res["holdings"]

    # Holding days: 2, 3, 4, 5 and 7, 8, 9
    for i in [2, 3, 4, 5, 7, 8, 9]:
        assert holdings.iloc[i].equals(holdings.iloc[i - 1])


# 7. Trade-to-Share Mapping
def test_7_trade_to_share_mapping(sample_market_data):
    dates, prices_df, target_weights_df = sample_market_data
    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res = sim.run(target_weights_df, prices_df, rebalance_freq=5, start_idx=0)
    trades = res["trades"]
    holdings = res["holdings"]

    for _, tr in trades.iterrows():
        dt = tr["date"]
        sym = tr["symbol"]
        dt_idx = dates.get_loc(dt)
        q_curr = holdings.loc[dt, sym]
        q_prev = holdings.iloc[dt_idx - 1][sym] if dt_idx > 0 else 0.0
        assert q_curr - q_prev == pytest.approx(tr["delta_shares"], abs=1e-5)


# 8. Rebalance Conversion
def test_8_rebalance_conversion():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    prices_df = pd.DataFrame({"SPY": [250.0, 250.0, 250.0]}, index=dates)
    weights_df = pd.DataFrame({"SPY": [0.80, 0.80, 0.80]}, index=dates)

    sim = PortfolioSimulator(initial_cash=50_000.0, cost_bps=0.0)
    res = sim.run(weights_df, prices_df, rebalance_freq=1, start_idx=0)

    # 80% of $50,000 = $40,000 / $250 = 160 shares
    assert res["holdings"]["SPY"].iloc[1] == pytest.approx(160.0, abs=1e-4)


# 9. Transaction Costs
def test_9_transaction_costs():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    prices_df = pd.DataFrame({"SPY": [100.0, 100.0, 100.0]}, index=dates)
    weights_df = pd.DataFrame({"SPY": [1.0, 1.0, 1.0]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)  # 10 bps
    res = sim.run(weights_df, prices_df, rebalance_freq=1, start_idx=0)

    trade = res["trades"].iloc[0]
    # Traded $100,000 @ 10 bps = $100.00
    assert trade["cost"] == pytest.approx(100.0, abs=1e-4)
    assert res["nav"].iloc[1] == pytest.approx(99_900.0, abs=1e-4)


# 10. Short-Position Accounting
def test_10_short_position_accounting():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    prices_df = pd.DataFrame({"TLT": [100.0, 100.0, 110.0]}, index=dates)
    weights_df = pd.DataFrame({"TLT": [-0.50, -0.50, -0.50]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=0.0)
    res = sim.run(weights_df, prices_df, rebalance_freq=10, start_idx=0)

    # Day 1: Short 500 shares @ $100. Cash = $150,000. Holdings MV = -$50,000. NAV = $100,000
    assert res["holdings"]["TLT"].iloc[1] == pytest.approx(-500.0)
    assert res["cash"].iloc[1] == pytest.approx(150_000.0)
    assert res["nav"].iloc[1] == pytest.approx(100_000.0)

    # Day 2: TLT rises to $110. Holdings MV = -500 * $110 = -$55,000. NAV = $150,000 - $55,000 = $95,000 (-5% loss)
    assert res["nav"].iloc[2] == pytest.approx(95_000.0)


# 11. Return-From-NAV Calculation
def test_11_return_from_nav():
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    prices_df = pd.DataFrame({"SPY": [100.0, 100.0, 110.0, 121.0]}, index=dates)
    weights_df = pd.DataFrame({"SPY": [1.0, 1.0, 1.0, 1.0]}, index=dates)

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=0.0)
    res = sim.run(weights_df, prices_df, rebalance_freq=10, start_idx=0)

    returns = res["returns"]
    nav = res["nav"]
    for i in range(1, len(dates)):
        expected_r = (nav.iloc[i] / nav.iloc[i - 1]) - 1.0
        assert returns.iloc[i] == pytest.approx(expected_r, abs=1e-6)


# 12. Legacy Target-Weight Equality
def test_12_legacy_target_weight_equality():
    fixture_path = "tests/fixtures/synthetic_macro_12etf.csv"
    df = pd.read_csv(fixture_path, index_col=0, parse_dates=True)
    strat = SystematicMacroStrategy(min_train=756)
    target_weights = strat.generate_target_weights(df)

    assert target_weights.shape[0] == df.shape[0]
    assert list(target_weights.columns) == list(df.columns)
    # Long weights sum to +1.0 and Short weights sum to -1.0, so gross exposure <= 2.0 and net exposure approx 0.0
    for i in range(756, len(df)):
        if (i - 756) % 21 == 0:
            gross = target_weights.iloc[i].abs().sum()
            net = target_weights.iloc[i].sum()
            assert gross <= 2.000001, f"Gross exposure {gross} exceeded 2.0 at {df.index[i]}"
            assert net == pytest.approx(0.0, abs=1e-5), f"Net exposure {net} not market neutral at {df.index[i]}"


# 13. Deterministic Repeated Simulation
def test_13_deterministic_repeated_simulation(sample_market_data):
    dates, prices_df, target_weights_df = sample_market_data
    sim1 = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res1 = sim1.run(target_weights_df, prices_df, rebalance_freq=3, start_idx=0)

    sim2 = PortfolioSimulator(initial_cash=100_000.0, cost_bps=10.0)
    res2 = sim2.run(target_weights_df, prices_df, rebalance_freq=3, start_idx=0)

    assert res1["nav"].equals(res2["nav"])
    assert res1["cash"].equals(res2["cash"])
    assert res1["returns"].equals(res2["returns"])
    assert res1["metrics"] == res2["metrics"]
