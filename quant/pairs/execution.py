"""Portfolio weighting and execution engine for single-cohort pairs trading."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .signals import PairSignalEngine, PairTradeRecord


class PairExecutionEngine:
    """Calculates weighted buy-and-hold portfolio return R_t^P for a single trading cohort."""

    def __init__(
        self,
        entry_threshold_sigma: float = 2.0,
        wait_one_day: bool = True,
        cost_bps: float = 10.0,
    ) -> None:
        self.signal_engine = PairSignalEngine(
            entry_threshold_sigma=entry_threshold_sigma,
            wait_one_day=wait_one_day,
        )
        self.cost_bps = cost_bps

    def run_cohort_portfolio(
        self,
        pairs_list: list[dict],
        trading_prices: pd.DataFrame,
        cohort_id: str = "cohort_0",
    ) -> tuple[pd.Series, list[PairTradeRecord], pd.Series]:
        """Runs all M pairs in a cohort and aggregates into buy-and-hold return R_t^P.

        Equation (2):
            R_t^P = sum_{k=1}^M w_t^k R_t^k / sum_{k=1}^M w_t^k
            w_t^k = prod_{tau=t_1}^{t-1} (1 + R_tau^k)
        """
        dates = trading_prices.index
        n_days = len(dates)
        M = len(pairs_list)

        if M == 0 or n_days == 0:
            empty_s = pd.Series(0.0, index=dates)
            return empty_s, [], empty_s

        pair_returns_matrix = np.zeros((n_days, M), dtype=float)
        all_trades: list[PairTradeRecord] = []

        for k, p_info in enumerate(pairs_list):
            ret_k, trades_k = self.signal_engine.evaluate_pair_states(
                p_info, trading_prices, cohort_id=cohort_id
            )
            pair_returns_matrix[:, k] = ret_k.to_numpy()
            all_trades.extend(trades_k)

        # Calculate compounded weights w_t^k
        # If trade is inactive, w_t^k = 1.0, R_t^k = 0.0
        weights_matrix = np.ones((n_days, M), dtype=float)
        active_weights = np.ones(M, dtype=float)
        was_active = np.zeros(M, dtype=bool)

        for t in range(n_days):
            r_t = pair_returns_matrix[t, :]
            is_active_t = np.abs(r_t) > 1e-12

            for k in range(M):
                if is_active_t[k]:
                    if not was_active[k]:
                        # Trade newly opened
                        active_weights[k] = 1.0
                        was_active[k] = True
                    else:
                        # Compounded weight from previous day
                        active_weights[k] *= (1.0 + pair_returns_matrix[t - 1, k])
                    weights_matrix[t, k] = active_weights[k]
                else:
                    was_active[k] = False
                    active_weights[k] = 1.0
                    weights_matrix[t, k] = 1.0

        # Calculate gross and net R_t^P
        sum_w = np.sum(weights_matrix, axis=1)
        gross_cohort_return = np.sum(weights_matrix * pair_returns_matrix, axis=1) / np.maximum(1e-8, sum_w)

        # Apply transaction costs on trade entries and exits
        # 10 bps per trade leg (long + short = 2 legs = 20 bps on pair notional when initiated/closed)
        cost_series = np.zeros(n_days, dtype=float)
        for tr in all_trades:
            if tr.entry_exec_date in dates:
                idx_entry = dates.get_loc(tr.entry_exec_date)
                cost_series[idx_entry] += (self.cost_bps / 10_000.0) * (2.0 / M)
            if tr.exit_exec_date is not None and tr.exit_exec_date in dates:
                idx_exit = dates.get_loc(tr.exit_exec_date)
                cost_series[idx_exit] += (self.cost_bps / 10_000.0) * (2.0 / M)

        net_cohort_return = gross_cohort_return - cost_series

        return (
            pd.Series(net_cohort_return, index=dates),
            all_trades,
            pd.Series(gross_cohort_return, index=dates),
        )


PairTrade = PairTradeRecord
