"""High-level backtester and performance reporting for Yale Pairs Trading."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .cohorts import OverlappingCohortManager
from .execution import PairTradeRecord


class YalePairsBacktester:
    """End-to-end backtester executing Yale / Gatev Overlapping Pairs Trading."""

    def __init__(
        self,
        formation_bars: int = 252,
        trading_bars: int = 126,
        step_bars: int = 21,
        top_m: int = 20,
        entry_threshold_sigma: float = 2.0,
        wait_one_day: bool = True,
        liquidity_percentile: float = 0.0,
        sector_map: dict[str, str] | None = None,
        cost_bps: float = 10.0,
    ) -> None:
        self.manager = OverlappingCohortManager(
            formation_bars=formation_bars,
            trading_bars=trading_bars,
            step_bars=step_bars,
            top_m=top_m,
            entry_threshold_sigma=entry_threshold_sigma,
            wait_one_day=wait_one_day,
            liquidity_percentile=liquidity_percentile,
            sector_map=sector_map,
            cost_bps=cost_bps,
        )

    def run(
        self,
        prices: pd.DataFrame,
        volumes: pd.DataFrame | None = None,
        initial_capital: float = 100_000.0,
    ) -> dict:
        """Runs the overlapping simulation and computes comprehensive performance metrics."""
        sim_res = self.manager.run_overlapping_simulation(prices, volumes)

        net_r = sim_res["daily_strategy_returns"]
        gross_r = sim_res["gross_strategy_returns"]
        trades: list[PairTradeRecord] = sim_res["all_trades"]

        arr_net = net_r.to_numpy()
        arr_gross = gross_r.to_numpy()
        n_bars = len(arr_net)
        n_years = max(1e-4, n_bars / 252.0)

        # Cumulative NAV
        cum_net = (1.0 + net_r).cumprod()
        cum_gross = (1.0 + gross_r).cumprod()
        final_nav = initial_capital * float(cum_net.iloc[-1]) if len(cum_net) else initial_capital

        # CAGR
        tot_net_ret = float(cum_net.iloc[-1] - 1.0) if len(cum_net) else 0.0
        tot_gross_ret = float(cum_gross.iloc[-1] - 1.0) if len(cum_gross) else 0.0
        cagr_net = (1.0 + tot_net_ret) ** (1.0 / n_years) - 1.0 if tot_net_ret > -1.0 else -1.0
        cagr_gross = (1.0 + tot_gross_ret) ** (1.0 / n_years) - 1.0 if tot_gross_ret > -1.0 else -1.0

        # Volatility & Sharpe
        ann_vol = float(np.std(arr_net, ddof=1) * np.sqrt(252.0)) if len(arr_net) > 1 else 1e-8
        gross_vol = float(np.std(arr_gross, ddof=1) * np.sqrt(252.0)) if len(arr_gross) > 1 else 1e-8
        sharpe_net = float((np.mean(arr_net) / max(1e-8, np.std(arr_net, ddof=1))) * np.sqrt(252.0)) if len(arr_net) > 1 else 0.0
        sharpe_gross = float((np.mean(arr_gross) / max(1e-8, np.std(arr_gross, ddof=1))) * np.sqrt(252.0)) if len(arr_gross) > 1 else 0.0

        # Downside / Sortino
        downside = arr_net[arr_net < 0]
        downside_std = float(np.std(downside, ddof=1) * np.sqrt(252.0)) if len(downside) > 1 else 1e-8
        sortino = float(cagr_net / downside_std) if downside_std > 0 else 0.0

        # Drawdown / Calmar
        pk = cum_net.cummax()
        dd = (cum_net - pk) / pk
        max_dd = float(dd.min()) if len(dd) else 0.0
        calmar = float(abs(cagr_net / max_dd)) if max_dd < 0 else 0.0

        # Trade Analytics
        completed_trades = [t for t in trades if t.exit_exec_date is not None]
        n_trades = len(completed_trades)
        convergences = [t for t in completed_trades if t.exit_reason == "CONVERGENCE"]
        horizon_closes = [t for t in completed_trades if t.exit_reason == "HORIZON_END"]

        convergence_rate = len(convergences) / max(1, n_trades)
        forced_close_rate = len(horizon_closes) / max(1, n_trades)

        trade_returns = []
        holding_days = []
        for t in completed_trades:
            # Approximate trade return from spread narrowing
            spread_ret = -t.leader * (t.exit_spread - t.entry_spread)
            trade_returns.append(spread_ret)
            if t.exit_exec_date is not None and t.entry_exec_date is not None:
                h_days = (t.exit_exec_date - t.entry_exec_date).days
                holding_days.append(h_days)

        win_rate = float(np.mean(np.array(trade_returns) > 0)) if trade_returns else 0.0
        avg_trade_ret = float(np.mean(trade_returns)) if trade_returns else 0.0
        med_trade_ret = float(np.median(trade_returns)) if trade_returns else 0.0
        worst_trade = float(np.min(trade_returns)) if trade_returns else 0.0
        best_trade = float(np.max(trade_returns)) if trade_returns else 0.0
        avg_holding_period = float(np.mean(holding_days)) if holding_days else 0.0

        # Turnover estimation: 2 trades (entry + exit) * $1 / (6 months)
        ann_turnover = float((n_trades * 2.0) / (n_years * max(1, self.manager.top_m)))

        return {
            "cagr_net": cagr_net,
            "cagr_gross": cagr_gross,
            "sharpe_net": sharpe_net,
            "sharpe_gross": sharpe_gross,
            "sortino": sortino,
            "volatility": ann_vol,
            "gross_volatility": gross_vol,
            "max_drawdown": max_dd,
            "calmar": calmar,
            "final_nav": final_nav,
            "annualized_turnover": ann_turnover,
            "trade_count": n_trades,
            "win_rate": win_rate,
            "convergence_rate": convergence_rate,
            "forced_close_rate": forced_close_rate,
            "avg_trade_return": avg_trade_ret,
            "median_trade_return": med_trade_ret,
            "worst_trade": worst_trade,
            "best_trade": best_trade,
            "avg_holding_period_days": avg_holding_period,
            "daily_returns": net_r,
            "gross_returns": gross_r,
            "cumulative_nav": cum_net,
            "cohort_metadata": sim_res["cohort_metadata"],
            "trades": completed_trades,
        }
