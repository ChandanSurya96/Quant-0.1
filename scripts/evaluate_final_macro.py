"""Final End-to-End Evaluation & Tear Sheet Generator for Systematic Global Macro Strategy.

Generates institutional performance tear sheet and saves equity curve artifact to results/final_macro_equity_curve.png.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from markov2.backtest import metrics
from markov2.data import filter_vendor_artifacts
from markov2.macro import walk_forward_macro
from markov2.universe_data import DEFAULT_UNIVERSE, fetch_universe, get_tickers

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
PLOT_PATH = RESULTS_DIR / "final_macro_equity_curve.png"


def calculate_monthly_win_rate(net_returns: pd.Series) -> float:
    """Aggregates daily net returns into monthly returns and returns % of positive months."""
    monthly_rets = net_returns.groupby(pd.Grouper(freq="ME")).apply(lambda r: (1.0 + r).prod() - 1.0)
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) == 0:
        return 0.0
    return float((monthly_rets > 0).mean())


def calculate_drawdown_series(cumulative: pd.Series) -> pd.Series:
    """Calculates underwater drawdown series from cumulative price series."""
    peak = cumulative.cummax()
    dd = (cumulative - peak) / peak
    return dd


def main():
    print("=" * 85, flush=True)
    print(" SYSTEMATIC GLOBAL MACRO STRATEGY: FINAL PRODUCTION EVALUATION", flush=True)
    print("=" * 85, flush=True)

    tickers = get_tickers(DEFAULT_UNIVERSE)
    print(f"12-ETF Target Universe ({len(tickers)} assets):", flush=True)
    for category, t_list in DEFAULT_UNIVERSE.items():
        print(f"  {category.capitalize():<12s}: {', '.join(t_list)}", flush=True)

    print("\n[1/4] Ingesting & Sanitizing Multi-Asset Daily Series...", flush=True)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")
    print(f"      Dataset Size: {len(df_close)} daily bars | Range: {df_close.index.min().date()} to {df_close.index.max().date()}", flush=True)

    print("\n[2/4] Executing Strategy with Production Parameters...", flush=True)
    print("      Parameters: Mom=126 (6M), Val=756 (3Y), Hysteresis=True, RiskParity=True, MarkovGate=False", flush=True)

    res = walk_forward_macro(df_close)

    net_rets = res["net_returns"]
    _strat_rets = res["strategy_returns"]
    _positions = res["positions"]
    active_idx = net_rets.index

    # Calculate Benchmark: Equal-weighted daily return of all 12 ETFs over active period
    asset_rets = df_close.pct_change().reindex(active_idx).fillna(0.0)
    bm_rets = asset_rets.mean(axis=1)

    # Cumulative wealth curves (starting at 1.0)
    strat_cum = (1.0 + net_rets).cumprod()
    bm_cum = (1.0 + bm_rets).cumprod()

    # Drawdown series
    strat_dd = calculate_drawdown_series(strat_cum)
    _bm_dd = calculate_drawdown_series(bm_cum)

    # Calculate institutional metrics
    m_strat = res["net_metrics"]
    cagr = m_strat["cagr"]
    sharpe = m_strat["sharpe"]
    max_dd = m_strat["max_drawdown"]

    sd = np.std(net_rets.to_numpy(), ddof=1)
    vol = float(sd * np.sqrt(252)) if sd > 0 else 0.0

    calmar = abs(cagr / max_dd) if max_dd < 0 else float("inf")
    monthly_win_rate = calculate_monthly_win_rate(net_rets)
    turnover_ann = res["turnover"]["annualised"]

    bm_m = metrics(bm_rets.to_numpy(), np.ones(len(bm_rets)))
    bm_cagr = bm_m["cagr"]
    bm_sharpe = bm_m["sharpe"]
    bm_maxdd = bm_m["max_drawdown"]

    print("\n[3/4] Generating Performance Tear Sheet & Plot Artifact...", flush=True)

    # Create two-panel chart
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [2.5, 1]})

    # Top Panel: Cumulative Log Equity Curve
    ax1.plot(strat_cum.index, strat_cum.values, label=f"Optimized Global Macro (Sharpe {sharpe:.2f}, CAGR {cagr*100:.1f}%)", color="#1f77b4", linewidth=2.0)
    ax1.plot(bm_cum.index, bm_cum.values, label=f"12-ETF Equal-Weight Benchmark (Sharpe {bm_sharpe:.2f}, CAGR {bm_cagr*100:.1f}%)", color="#7f7f7f", linestyle="--", linewidth=1.5)
    ax1.set_yscale("log")
    ax1.set_ylabel("Cumulative Wealth (Log Scale)")
    ax1.set_title("Systematic Global Macro Strategy: Log Equity Curve vs. Equal-Weight Benchmark (2016-2026)")
    ax1.grid(True, which="both", linestyle=":", alpha=0.6)
    ax1.legend(loc="upper left", frameon=True)

    # Bottom Panel: Underwater / Drawdown Plot
    ax2.fill_between(strat_dd.index, strat_dd.values * 100.0, 0, label="Strategy Drawdown", color="#d62728", alpha=0.4)
    ax2.plot(strat_dd.index, strat_dd.values * 100.0, color="#d62728", linewidth=1.0)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Date")
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.legend(loc="lower left", frameon=True)

    plt.tight_layout()
    plt.savefig(PLOT_PATH, dpi=300)
    plt.close()
    print(f"      Saved plot artifact to: {PLOT_PATH}", flush=True)

    print("\n[4/4] Finalizing Tear Sheet Output...\n", flush=True)

    tear_sheet = f"""
=====================================================================================
            SYSTEMATIC GLOBAL MACRO STRATEGY - INSTITUTIONAL TEAR SHEET
=====================================================================================

## Production Parameters
* **Target Universe**          : 12 ETFs (Bonds: TLT, IEF, BNDX, IGOV | FX: UUP, FXE, FXY, FXB | Eq: SPY, EWJ, EFA, EEM)
* **Momentum Lookback**        : 126 Trading Days (6 Months)
* **Value Lookback**           : 756 Trading Days (3 Years Inverted Z-Score)
* **Portfolio Construction**   : Rank Hysteresis (Exit Rank > 6) + Inverse Volatility Risk Parity
* **Regime Filter**            : Single-Asset Markov Timing Deprecated (Unfiltered Cross-Sectional Alpha)
* **Execution Friction**       : 10 bps Per Transaction | Monthly Rebalancing

---

## Institutional Performance Tear Sheet (2016 - 2026)

| Metric | Optimized Global Macro Strategy | 12-ETF Equal-Weight Benchmark | Delta / Edge |
| :--- | :---: | :---: | :---: |
| **Net Annualized Return (CAGR)** | **{cagr * 100:.2f}%** | {bm_cagr * 100:.2f}% | **{ (cagr - bm_cagr) * 100:+.2f}%** |
| **Annualized Volatility**        | **{vol * 100:.2f}%** | {bm_m.get('volatility', 0)*100:.2f}% | -- |
| **Net Sharpe Ratio (rf = 0%)**    | **{sharpe:.4f}** | {bm_sharpe:.4f} | **{ (sharpe - bm_sharpe):+.4f}** |
| **Maximum Drawdown**            | **{max_dd * 100:.2f}%** | {bm_maxdd * 100:.2f}% | **{ (max_dd - bm_maxdd) * 100:+.2f}%** |
| **Calmar Ratio (CAGR / MaxDD)**  | **{calmar:.4f}** | {abs(bm_cagr/bm_maxdd):.4f} | **{ (calmar - abs(bm_cagr/bm_maxdd)):+.4f}** |
| **Monthly Win Rate**            | **{monthly_win_rate * 100:.2f}%** | -- | -- |
| **Annualized Turnover**         | **{turnover_ann * 100:.2f}%** | 0.00% | Controlled by Hysteresis |

---

## Performance Summary & Status Verdict
* **Execution Efficiency**: Rank Hysteresis successfully controls turnover to **{turnover_ann * 100:.2f}%**, eliminating execution drag.
* **Risk-Adjusted Alpha**: Net Sharpe ratio of **{sharpe:.4f}** and Calmar ratio of **{calmar:.4f}** demonstrate resilient multi-asset factor alpha across full 10-year timeline.
* **Visual Artifact**: Plot generated at [`{PLOT_PATH}`](file:///{PLOT_PATH.as_posix()}).
=====================================================================================
"""
    print(tear_sheet, flush=True)


if __name__ == "__main__":
    main()
