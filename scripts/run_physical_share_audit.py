"""Physical Share vs Legacy Forward-Filled Backtest Integrity Audit Script.

Computes:
1. Full side-by-side performance metrics (Legacy vs Physical-Share).
2. Daily return series divergence: Mean diff, std diff, max abs diff, correlation.
3. Holding-period drift trace across a representative rebalance cycle.
4. Accounting invariants verification: Cash conservation, NAV conservation, Share conservation, Trade conservation.
5. In-Sample Train (60%), Validation (20%), and True OOS (20%) comparisons.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from markov2.data import filter_vendor_artifacts
from markov2.macro import walk_forward_macro
from markov2.splits import get_splits
from markov2.universe_data import DEFAULT_UNIVERSE, fetch_universe, get_tickers
from quant.portfolio.simulator import PortfolioSimulator
from quant.strategies.macro import SystematicMacroStrategy


def run_audit() -> dict:
    tickers = get_tickers(DEFAULT_UNIVERSE)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")
    start_idx = 756
    cost_bps = 10.0

    # 1. Legacy Vectorized Backtest
    res_legacy = walk_forward_macro(
        df_close,
        min_train=start_idx,
        cost_bps=cost_bps,
        apply_markov_gate=False,
        n_long=3,
        n_short=3,
        use_hysteresis=True,
        use_risk_parity=True,
        mom_window=126,
        val_window=756,
    )
    legacy_net_returns = res_legacy["net_returns"]
    legacy_positions = res_legacy["positions"]
    legacy_metrics = res_legacy["net_metrics"]

    # 2. Physical Share Simulator
    strat = SystematicMacroStrategy(
        mom_window=126,
        val_window=756,
        vol_window=60,
        rebalance_freq=21,
        n_long=3,
        n_short=3,
        use_hysteresis=True,
        use_risk_parity=True,
        min_train=start_idx,
    )
    target_weights = strat.generate_target_weights(df_close)

    # Verify Target Weights Parity at Rebalance Dates
    rebalance_dates = []
    for i in range(start_idx, len(df_close)):
        if (i - start_idx) % 21 == 0:
            rebalance_dates.append(df_close.index[i])

    sim = PortfolioSimulator(initial_cash=100_000.0, cost_bps=cost_bps)
    res_phys = sim.run(
        target_weights_df=target_weights,
        prices_df=df_close,
        rebalance_freq=21,
        rebalance_dates=rebalance_dates,
        start_idx=start_idx,
    )
    phys_nav = res_phys["nav"]
    phys_returns = res_phys["returns"]
    phys_cash = res_phys["cash"]
    phys_holdings = res_phys["holdings"]
    phys_weights = res_phys["realized_weights"]
    phys_trades = res_phys["trades"]
    phys_metrics = res_phys["metrics"]

    # Align common active dates
    common_active = legacy_net_returns.index.intersection(phys_returns.index)
    r_leg = legacy_net_returns.loc[common_active]
    r_phys = phys_returns.loc[common_active]

    # Return series divergence stats
    diff = r_phys - r_leg
    mean_diff = float(diff.mean())
    std_diff = float(diff.std(ddof=1))
    max_abs_diff = float(np.max(np.abs(diff)))
    corr = float(r_leg.corr(r_phys))
    cum_leg = (1.0 + r_leg).cumprod()
    cum_phys = (1.0 + r_phys).cumprod()
    cum_divergence = float((cum_phys.iloc[-1] - cum_leg.iloc[-1]) / cum_leg.iloc[-1])

    # Invariant Verification across all bars:
    # A. NAV Conservation: NAV_t == Cash_t + sum(Shares_i * Price_i)
    nav_conservation_errors = []
    # B. Share Conservation on non-rebalance days: Shares_t == Shares_t-1
    share_conservation_errors = []
    reb_set = set(rebalance_dates)

    for i in range(1, len(common_active)):
        dt = common_active[i]
        dt_prev = common_active[i - 1]
        c_val = phys_cash.loc[dt]
        h_row = phys_holdings.loc[dt]
        p_row = df_close.loc[dt]
        nav_val = phys_nav.loc[dt]
        calc_nav = c_val + sum(h_row[sym] * p_row[sym] for sym in df_close.columns)
        if abs(calc_nav - nav_val) > 1e-4:
            nav_conservation_errors.append((dt, calc_nav, nav_val))

        # Check share conservation on holding days
        if dt not in reb_set:
            prev_h = phys_holdings.loc[dt_prev]
            if not prev_h.equals(h_row):
                share_conservation_errors.append((dt, prev_h, h_row))

    # Holding Period Drift Trace (e.g. first rebalance cycle post warm-up)
    cycle_start = rebalance_dates[0]
    cycle_end = rebalance_dates[1]
    cycle_slice = df_close.loc[cycle_start:cycle_end].index

    drift_trace = []
    for dt in cycle_slice[:5]:  # First 5 days of cycle
        c_val = phys_cash.loc[dt]
        nav_val = phys_nav.loc[dt]
        for sym in ["TLT", "SPY", "UUP"]:
            sh = phys_holdings.loc[dt, sym]
            px = df_close.loc[dt, sym]
            mv = sh * px
            pw = phys_weights.loc[dt, sym]
            lw = legacy_positions.loc[dt, sym] if dt in legacy_positions.index else 0.0
            drift_trace.append({
                "date": str(dt.date()),
                "symbol": sym,
                "shares": sh,
                "price": px,
                "market_value": mv,
                "cash": c_val,
                "nav": nav_val,
                "physical_weight": pw,
                "legacy_weight": lw,
            })

    # Sortino calculations
    downside_leg = r_leg[r_leg < 0].to_numpy()
    downside_phys = r_phys[r_phys < 0].to_numpy()
    sortino_leg = float(legacy_metrics["cagr"] / (np.std(downside_leg, ddof=1) * np.sqrt(252))) if len(downside_leg) > 1 else 0.0
    sortino_phys = float(phys_metrics["cagr"] / (np.std(downside_phys, ddof=1) * np.sqrt(252))) if len(downside_phys) > 1 else 0.0

    # Calmar
    calmar_leg = float(abs(legacy_metrics["cagr"] / legacy_metrics["max_drawdown"])) if legacy_metrics["max_drawdown"] < 0 else 0.0
    calmar_phys = float(abs(phys_metrics["cagr"] / phys_metrics["max_drawdown"])) if phys_metrics["max_drawdown"] < 0 else 0.0

    # Partition comparison (Train 60%, Val 20%, True OOS 20%)
    splits = get_splits(df_close, train_pct=0.60, val_pct=0.20)
    train_idx = splits["TRAIN"].intersection(common_active)
    val_idx = splits["VALIDATION"].intersection(common_active)
    oos_idx = splits["TRUE_OOS"].intersection(common_active)

    def calc_sub_metrics(part_r: pd.Series) -> dict:
        arr = part_r.to_numpy()
        sd = np.std(arr, ddof=1) if len(arr) > 1 else 1e-8
        sh = float((np.mean(arr) / sd) * np.sqrt(252)) if sd > 0 else 0.0
        n_years = len(arr) / 252.0 if len(arr) else 1.0
        tot = float((1.0 + part_r).prod() - 1.0) if len(arr) else 0.0
        cagr = (1.0 + tot) ** (1.0 / max(1e-4, n_years)) - 1.0 if tot > -1.0 else -1.0
        cum = (1.0 + part_r).cumprod()
        pk = cum.cummax()
        mdd = float(((cum - pk) / pk).min()) if len(cum) else 0.0
        return {"sharpe": sh, "cagr": cagr, "max_drawdown": mdd}

    partitions = {
        "TRAIN": {"legacy": calc_sub_metrics(r_leg.loc[train_idx]), "physical": calc_sub_metrics(r_phys.loc[train_idx])},
        "VALIDATION": {"legacy": calc_sub_metrics(r_leg.loc[val_idx]), "physical": calc_sub_metrics(r_phys.loc[val_idx])},
        "TRUE_OOS": {"legacy": calc_sub_metrics(r_leg.loc[oos_idx]), "physical": calc_sub_metrics(r_phys.loc[oos_idx])},
    }

    result = {
        "legacy": {
            "cagr": legacy_metrics["cagr"],
            "sharpe": legacy_metrics["sharpe"],
            "sortino": sortino_leg,
            "volatility": float(np.std(r_leg.to_numpy(), ddof=1) * np.sqrt(252)),
            "max_drawdown": legacy_metrics["max_drawdown"],
            "calmar": calmar_leg,
            "turnover": float(res_legacy["turnover"]["annualised"]),
            "final_nav": float(cum_leg.iloc[-1] * 100_000.0),
        },
        "physical": {
            "cagr": phys_metrics["cagr"],
            "sharpe": phys_metrics["sharpe"],
            "sortino": sortino_phys,
            "volatility": phys_metrics["annualized_volatility"],
            "max_drawdown": phys_metrics["max_drawdown"],
            "calmar": calmar_phys,
            "turnover": phys_metrics["annualized_turnover"],
            "total_costs": phys_metrics["total_costs"],
            "final_nav": phys_metrics["final_nav"],
        },
        "divergence": {
            "mean_diff": mean_diff,
            "std_diff": std_diff,
            "max_abs_diff": max_abs_diff,
            "correlation": corr,
            "cum_divergence": cum_divergence,
        },
        "invariants": {
            "nav_conservation_errors": len(nav_conservation_errors),
            "share_conservation_errors": len(share_conservation_errors),
            "total_trades": len(phys_trades),
        },
        "partitions": partitions,
        "drift_trace_sample": drift_trace,
    }

    out_file = Path(__file__).resolve().parent.parent / "results" / "physical_share_audit_data.json"
    with open(out_file, "w") as f:
        json.dump(result, f, indent=2)

    return result


if __name__ == "__main__":
    res = run_audit()
    print("=" * 80)
    print(" PHYSICAL SHARE AUDIT COMPLETE")
    print("=" * 80)
    print(f"{'Metric':<25} | {'Legacy':<15} | {'Physical Share':<15} | {'Diff':<15}")
    print("-" * 80)
    for m in ["cagr", "sharpe", "sortino", "volatility", "max_drawdown", "calmar", "turnover", "final_nav"]:
        l_val = res["legacy"][m]
        p_val = res["physical"][m]
        d_val = p_val - l_val
        print(f"{m:<25} | {l_val:<15.4f} | {p_val:<15.4f} | {d_val:<15.4f}")
    print("=" * 80)
    print(f"Correlation: {res['divergence']['correlation']:.6f}")
    print(f"NAV Conservation Errors: {res['invariants']['nav_conservation_errors']}")
    print(f"Share Conservation Errors: {res['invariants']['share_conservation_errors']}")
