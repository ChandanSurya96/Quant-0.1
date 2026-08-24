"""Executes Yale / Gatev Distance Pairs Strategy Experiments (PAIRS-001 to PAIRS-004)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from markov2.data import filter_vendor_artifacts
from markov2.splits import get_splits
from markov2.universe_data import DEFAULT_UNIVERSE, fetch_universe, get_tickers
from quant.pairs.backtest import YalePairsBacktester


def run_distance_experiments() -> dict:
    tickers = get_tickers(DEFAULT_UNIVERSE)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")

    # Sector map for 12-ETF universe
    sector_map = {
        "TLT": "BONDS", "IEF": "BONDS", "BNDX": "BONDS", "IGOV": "BONDS",
        "UUP": "FX", "FXE": "FX", "FXY": "FX", "FXB": "FX",
        "SPY": "EQUITY", "EWJ": "EQUITY", "EFA": "EQUITY", "EEM": "EQUITY",
    }

    # Configurations
    configs = {
        "PAIRS-001 (Yale Distance T20)": {
            "top_m": 20, "liquidity": 0.0, "sector_map": None, "threshold": 2.0, "cost_bps": 10.0
        },
        "PAIRS-002 (Yale Distance T100 / All Pairs)": {
            "top_m": 100, "liquidity": 0.0, "sector_map": None, "threshold": 2.0, "cost_bps": 10.0
        },
        "PAIRS-003 (Yale Distance R20 - Same Sector)": {
            "top_m": 20, "liquidity": 0.0, "sector_map": sector_map, "threshold": 2.0, "cost_bps": 10.0
        },
        "PAIRS-004 (Yale Distance L50 - Liquid)": {
            "top_m": 20, "liquidity": 0.50, "sector_map": None, "threshold": 2.0, "cost_bps": 10.0
        },
    }

    results = {}
    for name, cfg in configs.items():
        bt = YalePairsBacktester(
            formation_bars=252,
            trading_bars=126,
            step_bars=21,
            top_m=cfg["top_m"],
            entry_threshold_sigma=cfg["threshold"],
            liquidity_percentile=cfg["liquidity"],
            sector_map=cfg["sector_map"],
            cost_bps=cfg["cost_bps"],
        )
        res = bt.run(df_close)
        results[name] = {
            "cagr_net": res["cagr_net"],
            "cagr_gross": res["cagr_gross"],
            "sharpe_net": res["sharpe_net"],
            "sharpe_gross": res["sharpe_gross"],
            "sortino": res["sortino"],
            "volatility": res["volatility"],
            "max_drawdown": res["max_drawdown"],
            "calmar": res["calmar"],
            "trade_count": res["trade_count"],
            "win_rate": res["win_rate"],
            "convergence_rate": res["convergence_rate"],
            "forced_close_rate": res["forced_close_rate"],
            "avg_trade_return": res["avg_trade_return"],
            "median_trade_return": res["median_trade_return"],
            "worst_trade": res["worst_trade"],
            "best_trade": res["best_trade"],
            "avg_holding_period_days": res["avg_holding_period_days"],
            "annualized_turnover": res["annualized_turnover"],
            "final_nav": res["final_nav"],
            "daily_returns": res["daily_returns"],
        }

    # Friction sensitivity sweep for PAIRS-001 (T20)
    cost_sweep = {}
    for c_bps in [0.0, 5.0, 10.0, 20.0, 30.0, 50.0]:
        bt_c = YalePairsBacktester(
            formation_bars=252, trading_bars=126, step_bars=21,
            top_m=20, entry_threshold_sigma=2.0, cost_bps=c_bps,
        )
        res_c = bt_c.run(df_close)
        cost_sweep[f"{int(c_bps)} bps"] = {
            "sharpe_net": res_c["sharpe_net"],
            "cagr_net": res_c["cagr_net"],
            "max_drawdown": res_c["max_drawdown"],
        }

    # Walk-forward analysis on PAIRS-001
    t20_rets = results["PAIRS-001 (Yale Distance T20)"]["daily_returns"]
    splits = get_splits(df_close, train_pct=0.60, val_pct=0.20)
    train_idx = splits["TRAIN"].intersection(t20_rets.index)
    val_idx = splits["VALIDATION"].intersection(t20_rets.index)
    oos_idx = splits["TRUE_OOS"].intersection(t20_rets.index)

    def eval_sub(r_s: pd.Series) -> dict:
        arr = r_s.to_numpy()
        sd = np.std(arr, ddof=1) if len(arr) > 1 else 1e-8
        sh = float((np.mean(arr) / sd) * np.sqrt(252)) if sd > 0 else 0.0
        n_years = len(arr) / 252.0 if len(arr) else 1.0
        tot = float((1.0 + r_s).prod() - 1.0) if len(arr) else 0.0
        cagr = (1.0 + tot) ** (1.0 / max(1e-4, n_years)) - 1.0 if tot > -1.0 else -1.0
        cum = (1.0 + r_s).cumprod()
        pk = cum.cummax()
        mdd = float(((cum - pk) / pk).min()) if len(cum) else 0.0
        return {"sharpe": sh, "cagr": cagr, "max_drawdown": mdd}

    walk_forward = {
        "TRAIN": eval_sub(t20_rets.loc[train_idx]),
        "VALIDATION": eval_sub(t20_rets.loc[val_idx]),
        "TRUE_OOS": eval_sub(t20_rets.loc[oos_idx]),
    }

    summary = {
        "configurations": {
            name: {k: v for k, v in res.items() if k != "daily_returns"}
            for name, res in results.items()
        },
        "cost_sweep": cost_sweep,
        "walk_forward": walk_forward,
    }

    out_file = Path(__file__).resolve().parent.parent / "results" / "pairs_distance_results.json"
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    res = run_distance_experiments()
    print("=" * 80)
    print(" YALE DISTANCE PAIRS EXPERIMENTS COMPLETE")
    print("=" * 80)
    for name, m in res["configurations"].items():
        print(f"{name:<45} | Sharpe={m['sharpe_net']:<7.4f} | CAGR={m['cagr_net']*100:<6.2f}% | MaxDD={m['max_drawdown']*100:<6.2f}% | Trades={m['trade_count']}")
