"""Trading signal and trade-state generation per Gatev et al. (2006)."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class PairTradeRecord:
    """State record for a single pair trade round-trip."""
    pair_id: tuple[str, str]
    cohort_id: str
    asset_i: str
    asset_j: str
    entry_signal_date: pd.Timestamp
    entry_exec_date: pd.Timestamp
    exit_signal_date: pd.Timestamp | None = None
    exit_exec_date: pd.Timestamp | None = None
    leader: int = 1  # +1 if i is leader (short i, long j), -1 if j is leader (long i, short j)
    entry_spread: float = 0.0
    exit_spread: float = 0.0
    exit_reason: str = "OPEN"  # CONVERGENCE, HORIZON_END, DELISTING
    gross_return: float = 0.0
    net_return: float = 0.0
    is_active: bool = True


class PairSignalEngine:
    """Evaluates spread divergence signals with wait-one-day execution rule and exit hysteresis."""

    def __init__(
        self,
        entry_threshold_sigma: float = 2.0,
        exit_threshold_sigma: float = 0.0,
        wait_one_day: bool = True,
    ) -> None:
        self.entry_threshold_sigma = entry_threshold_sigma
        self.exit_threshold_sigma = exit_threshold_sigma
        self.wait_one_day = wait_one_day

    def evaluate_pair_states(
        self,
        pair_info: dict,
        trading_prices: pd.DataFrame,
        cohort_id: str = "cohort_0",
    ) -> tuple[pd.Series, list[PairTradeRecord]]:
        """Simulates single-pair trading signals and returns daily trade returns.

        Parameters:
            pair_info: Dict containing asset_i, asset_j, spread_std, p_i_init, p_j_init.
            trading_prices: Close prices of constituents during 6-month trading period.
            cohort_id: Identifier for trading cohort.

        Returns:
            daily_returns: pd.Series of daily pair returns R_t^k
            trade_records: List of completed/active PairTradeRecord
        """
        sym_i = pair_info["asset_i"]
        sym_j = pair_info["asset_j"]
        p_i_init = pair_info["p_i_init"]
        p_j_init = pair_info["p_j_init"]
        s_ij = pair_info["spread_std"]
        threshold = self.entry_threshold_sigma * s_ij
        exit_thresh = self.exit_threshold_sigma * s_ij

        # Normalized prices using initial formation base
        norm_i = trading_prices[sym_i] / p_i_init
        norm_j = trading_prices[sym_j] / p_j_init
        spread = norm_i - norm_j

        rets_i = trading_prices[sym_i].pct_change().fillna(0.0)
        rets_j = trading_prices[sym_j].pct_change().fillna(0.0)

        n_days = len(trading_prices)
        dates = trading_prices.index
        daily_pair_returns = pd.Series(0.0, index=dates, dtype=float)

        trades: list[PairTradeRecord] = []
        current_trade: PairTradeRecord | None = None
        pending_entry: dict | None = None
        pending_exit: dict | None = None

        for t in range(n_days):
            dt = dates[t]

            # 1. Execute pending entry if wait-one-day rule applies
            if pending_entry is not None:
                current_trade = PairTradeRecord(
                    pair_id=(sym_i, sym_j),
                    cohort_id=cohort_id,
                    asset_i=sym_i,
                    asset_j=sym_j,
                    entry_signal_date=pending_entry["signal_date"],
                    entry_exec_date=dt,
                    leader=pending_entry["leader"],
                    entry_spread=pending_entry["spread"],
                    is_active=True,
                )
                trades.append(current_trade)
                pending_entry = None

            # 2. Execute pending exit if wait-one-day rule applies
            if pending_exit is not None and current_trade is not None and current_trade.is_active:
                current_trade.exit_exec_date = dt
                current_trade.exit_spread = float(spread.iloc[t])
                current_trade.exit_reason = pending_exit["reason"]
                current_trade.is_active = False
                current_trade = None
                pending_exit = None

            # 3. Accrue returns if position is active on day t
            if current_trade is not None and current_trade.is_active:
                eps = current_trade.leader
                # R_t^k = -eps * (R_i,t - R_j,t)
                r_k_t = -float(eps) * float(rets_i.iloc[t] - rets_j.iloc[t])
                daily_pair_returns.iloc[t] = r_k_t

            # 4. Check for exit or entry signals at close of day t
            curr_spread = float(spread.iloc[t])
            if current_trade is not None and current_trade.is_active:
                eps = current_trade.leader
                # Convergence test: sgn(P_i,t - P_j,t) != eps or spread inside exit hysteresis threshold
                curr_sign = 1 if curr_spread > 0 else (-1 if curr_spread < 0 else 0)
                is_converged = (curr_sign != eps) or (abs(curr_spread) <= exit_thresh) or (curr_spread == 0.0)
                if is_converged:
                    if self.wait_one_day:
                        pending_exit = {"signal_date": dt, "reason": "CONVERGENCE"}
                    else:
                        current_trade.exit_signal_date = dt
                        current_trade.exit_exec_date = dt
                        current_trade.exit_spread = curr_spread
                        current_trade.exit_reason = "CONVERGENCE"
                        current_trade.is_active = False
                        current_trade = None
                elif t == n_days - 1:
                    # Horizon end exit
                    current_trade.exit_signal_date = dt
                    current_trade.exit_exec_date = dt
                    current_trade.exit_spread = curr_spread
                    current_trade.exit_reason = "HORIZON_END"
                    current_trade.is_active = False
                    current_trade = None
            elif current_trade is None and pending_entry is None:
                # Entry test: |P_i,t - P_j,t| > 2 * s_ij
                if abs(curr_spread) > threshold and t < n_days - 1:
                    leader_sign = 1 if curr_spread > 0 else -1
                    if self.wait_one_day:
                        pending_entry = {
                            "signal_date": dt,
                            "leader": leader_sign,
                            "spread": curr_spread,
                        }
                    else:
                        current_trade = PairTradeRecord(
                            pair_id=(sym_i, sym_j),
                            cohort_id=cohort_id,
                            asset_i=sym_i,
                            asset_j=sym_j,
                            entry_signal_date=dt,
                            entry_exec_date=dt,
                            leader=leader_sign,
                            entry_spread=curr_spread,
                            is_active=True,
                        )
                        trades.append(current_trade)

        return daily_pair_returns, trades
