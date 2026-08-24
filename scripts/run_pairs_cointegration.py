"""Executes Cointegration Pairs Experiments (PAIRS-005 to PAIRS-007)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from markov2.data import filter_vendor_artifacts
from markov2.universe_data import DEFAULT_UNIVERSE, fetch_universe, get_tickers
from quant.pairs.backtest import YalePairsBacktester
from quant.pairs.cointegration import CointegrationPairEngine
from quant.pairs.cohorts import OverlappingCohortManager


def run_cointegration_experiments() -> dict:
    tickers = get_tickers(DEFAULT_UNIVERSE)
    df_raw = fetch_universe(tickers, years=10)

    df_clean_cols = {}
    for col in df_raw.columns:
        col_df = pd.DataFrame({"Close": df_raw[col], "Volume": 1000})
        filtered, _ = filter_vendor_artifacts(col_df)
        df_clean_cols[col] = filtered["Close"]

    df_close = pd.DataFrame(df_clean_cols).ffill().dropna(how="all")

    # 1. PAIRS-005: Engle-Granger Cointegration
    # Custom runner using CointegrationPairEngine
    class CointegrationCohortManager(OverlappingCohortManager):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.c_engine = CointegrationPairEngine(alpha_significance=0.05, top_m=20)

        def run_overlapping_simulation(self, prices, volumes=None):
            N = len(prices)
            cohort_starts = list(range(self.formation_bars, N, self.step_bars))
            cohort_returns_dict = {}
            cohort_gross_dict = {}
            all_trades = []

            for idx_c, start_i in enumerate(cohort_starts):
                formation_slice = prices.iloc[start_i - self.formation_bars:start_i]
                pairs = self.c_engine.form_cointegrated_pairs(formation_slice)
                if not pairs:
                    continue

                end_i = min(N, start_i + self.trading_bars)
                trading_slice = prices.iloc[start_i:end_i]
                cohort_id = f"cohort_eg_{idx_c:03d}"

                net_r, trades_c, gross_r = self.execution_engine.run_cohort_portfolio(
                    pairs_list=pairs,
                    trading_prices=trading_slice,
                    cohort_id=cohort_id,
                )
                cohort_returns_dict[cohort_id] = net_r
                cohort_gross_dict[cohort_id] = gross_r
                all_trades.extend(trades_c)

            df_net_cohorts = pd.DataFrame(cohort_returns_dict).reindex(prices.index)
            first_trading_dt = prices.index[self.formation_bars]
            df_active_net = df_net_cohorts.loc[first_trading_dt:]
            daily_net_strategy = df_active_net.mean(axis=1).fillna(0.0)

            return {
                "daily_strategy_returns": daily_net_strategy,
                "all_trades": all_trades,
            }

    # Run Distance T20
    dist_bt = YalePairsBacktester(top_m=20, cost_bps=10.0)
    dist_res = dist_bt.run(df_close)

    # Run Cointegration
    c_mgr = CointegrationCohortManager(top_m=20, cost_bps=10.0)
    c_sim = c_mgr.run_overlapping_simulation(df_close)
    c_net_r = c_sim["daily_strategy_returns"]
    c_trades = c_sim["all_trades"]

    arr_c = c_net_r.to_numpy()
    n_years = len(arr_c) / 252.0
    cum_c = (1.0 + c_net_r).cumprod()
    cagr_c = (1.0 + float(cum_c.iloc[-1] - 1.0)) ** (1.0 / n_years) - 1.0 if len(cum_c) else 0.0
    vol_c = float(np.std(arr_c, ddof=1) * np.sqrt(252.0))
    sh_c = float((np.mean(arr_c) / max(1e-8, np.std(arr_c, ddof=1))) * np.sqrt(252.0))
    pk_c = cum_c.cummax()
    mdd_c = float(((cum_c - pk_c) / pk_c).min())

    results = {
        "PAIRS-001 (Gatev Distance T20)": {
            "sharpe": dist_res["sharpe_net"],
            "cagr": dist_res["cagr_net"],
            "max_drawdown": dist_res["max_drawdown"],
            "volatility": dist_res["volatility"],
            "trade_count": dist_res["trade_count"],
            "win_rate": dist_res["win_rate"],
            "convergence_rate": dist_res["convergence_rate"],
        },
        "PAIRS-005 (Engle-Granger Cointegration)": {
            "sharpe": sh_c,
            "cagr": cagr_c,
            "max_drawdown": mdd_c,
            "volatility": vol_c,
            "trade_count": len(c_trades),
            "win_rate": float(np.mean([-t.leader * (t.exit_spread - t.entry_spread) > 0 for t in c_trades])) if c_trades else 0.0,
            "convergence_rate": float(np.mean([t.exit_reason == "CONVERGENCE" for t in c_trades])) if c_trades else 0.0,
        },
    }

    out_file = Path(__file__).resolve().parent.parent / "results" / "pairs_cointegration_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    res = run_cointegration_experiments()
    print("=" * 80)
    print(" DISTANCE VS COINTEGRATION EXPERIMENT COMPLETE")
    print("=" * 80)
    for name, m in res.items():
        print(f"{name:<45} | Sharpe={m['sharpe']:<7.4f} | CAGR={m['cagr']*100:<6.2f}% | MaxDD={m['max_drawdown']*100:<6.2f}% | Trades={m['trade_count']}")
