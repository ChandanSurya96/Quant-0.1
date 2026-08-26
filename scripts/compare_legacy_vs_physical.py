"""Side-by-side benchmark comparison: Legacy Vectorized Backtest vs. Physical Share Simulator.

TEST FIXTURE — NOT RESEARCH PERFORMANCE DATA
This script evaluates synthetic accounting and behavioral parity across a deterministic
test fixture (1,000 bars, 243 synthetic holdout evaluation bars). It is NOT intended
to demonstrate live or real-world strategy performance.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd

from markov2.macro import walk_forward_macro
from quant.portfolio.simulator import PortfolioSimulator
from quant.strategies.macro import SystematicMacroStrategy

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "synthetic_macro_12etf.csv"


def run_comparison(fixture_path: Path | str = FIXTURE_PATH, cost_bps: float = 10.0) -> None:
    """Runs legacy vectorized backtester and physical share simulator side-by-side."""
    df = pd.read_csv(fixture_path, index_col=0, parse_dates=True)
    print("=" * 78)
    print("SYNTHETIC ACCOUNTING / BEHAVIORAL COMPARISON")
    print("TEST FIXTURE — NOT RESEARCH PERFORMANCE DATA")
    print(f"Dataset: {fixture_path} (Shape: {df.shape}, 243 synthetic holdout bars)")
    print("=" * 78)

    # 1. Legacy Vectorized Backtest
    res_legacy = walk_forward_macro(df, min_train=756, cost_bps=cost_bps, apply_markov_gate=False)
    m_leg = res_legacy["metrics"]

    # 2. Physical Share Simulator
    strat = SystematicMacroStrategy(min_train=756)
    target_weights = strat.generate_target_weights(df)
    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=cost_bps)
    res_phys = sim.run(target_weights, df, rebalance_freq=21, start_idx=756)
    m_phys = res_phys["metrics"]

    print(f"{'METRIC':<30} | {'LEGACY VECTORIZED':<20} | {'PHYSICAL SHARE-BASED':<20}")
    print("-" * 78)
    print(f"{'Sharpe Ratio':<30} | {m_leg['sharpe']:<20.4f} | {m_phys['sharpe']:<20.4f}")
    print(f"{'CAGR':<30} | {m_leg['cagr']*100:<19.2f}% | {m_phys['cagr']*100:<19.2f}%")
    print(f"{'Max Drawdown':<30} | {m_leg['max_drawdown']*100:<19.2f}% | {m_phys['max_drawdown']*100:<19.2f}%")
    print(f"{'Turnover (Annualized)':<30} | {res_legacy['turnover']['total']:<20.4f} | {m_phys['annualized_turnover']:<20.4f}")
    print(f"{'Total Costs ($)':<30} | {'Return drag approx':<20} | ${m_phys['total_costs']:<19.2f}")
    print(f"{'Final NAV ($)':<30} | {'Indexed':<20} | ${m_phys['final_nav']:<19.2f}")
    print("=" * 78)


if __name__ == "__main__":
    run_comparison()
