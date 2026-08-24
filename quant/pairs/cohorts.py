"""Overlapping Monthly Cohort Manager for Yale Pairs Trading."""

from __future__ import annotations

import pandas as pd

from .execution import PairExecutionEngine, PairTradeRecord
from .formation import PairFormationEngine


class OverlappingCohortManager:
    """Manages overlapping monthly 6-month trading cohorts per Gatev et al. (2006).

    Formation Window: 12 months (e.g. 252 bars).
    Trading Window: 6 months (e.g. 126 bars).
    Rebalance Schedule: Monthly (e.g. every 21 bars a new cohort opens).
    Simultaneous Active Cohorts: 6 active cohorts at any time.
    Daily Strategy Return: Equal-weighted average of all currently active cohorts.
    """

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
        self.formation_bars = formation_bars
        self.trading_bars = trading_bars
        self.step_bars = step_bars
        self.top_m = top_m
        self.formation_engine = PairFormationEngine(
            formation_window=formation_bars,
            top_m=top_m,
            liquidity_percentile=liquidity_percentile,
            sector_map=sector_map,
        )
        self.execution_engine = PairExecutionEngine(
            entry_threshold_sigma=entry_threshold_sigma,
            wait_one_day=wait_one_day,
            cost_bps=cost_bps,
        )

    def run_overlapping_simulation(
        self,
        prices: pd.DataFrame,
        volumes: pd.DataFrame | None = None,
    ) -> dict:
        """Executes full walk-forward overlapping cohort simulation.

        Returns dict with:
            - daily_strategy_returns (pd.Series)
            - gross_strategy_returns (pd.Series)
            - all_trades (list[PairTradeRecord])
            - cohort_returns_df (pd.DataFrame)
            - cohort_metadata (list[dict])
        """
        N = len(prices)
        if N < self.formation_bars + self.trading_bars:
            raise ValueError(f"Prices length {N} is shorter than formation ({self.formation_bars}) + trading ({self.trading_bars}).")

        # Determine cohort start indices
        cohort_starts = list(range(self.formation_bars, N, self.step_bars))
        cohort_returns_dict: dict[str, pd.Series] = {}
        cohort_gross_dict: dict[str, pd.Series] = {}
        all_trades: list[PairTradeRecord] = []
        cohort_metadata: list[dict] = []

        for idx_c, start_i in enumerate(cohort_starts):
            formation_slice = prices.iloc[start_i - self.formation_bars:start_i]
            formation_vol_slice = volumes.iloc[start_i - self.formation_bars:start_i] if volumes is not None else None

            pairs = self.formation_engine.form_pairs(formation_slice, formation_vol_slice)
            if not pairs:
                continue

            end_i = min(N, start_i + self.trading_bars)
            trading_slice = prices.iloc[start_i:end_i]
            cohort_id = f"cohort_{idx_c:03d}_{str(prices.index[start_i].date())}"

            net_r, trades_c, gross_r = self.execution_engine.run_cohort_portfolio(
                pairs_list=pairs,
                trading_prices=trading_slice,
                cohort_id=cohort_id,
            )

            cohort_returns_dict[cohort_id] = net_r
            cohort_gross_dict[cohort_id] = gross_r
            all_trades.extend(trades_c)
            cohort_metadata.append({
                "cohort_id": cohort_id,
                "formation_start": str(prices.index[start_i - self.formation_bars].date()),
                "formation_end": str(prices.index[start_i - 1].date()),
                "trading_start": str(prices.index[start_i].date()),
                "trading_end": str(prices.index[end_i - 1].date()),
                "pair_count": len(pairs),
                "pairs": [p["pair"] for p in pairs],
            })

        # Combine overlapping cohorts by aligning on daily timestamps and computing mean across active cohorts
        df_net_cohorts = pd.DataFrame(cohort_returns_dict).reindex(prices.index)
        df_gross_cohorts = pd.DataFrame(cohort_gross_dict).reindex(prices.index)

        # Slice to active evaluation period (from first cohort trading_start)
        first_trading_dt = prices.index[self.formation_bars]
        df_active_net = df_net_cohorts.loc[first_trading_dt:]
        df_active_gross = df_gross_cohorts.loc[first_trading_dt:]

        # Mean across active cohorts on each day (ignoring NaNs for inactive cohorts)
        daily_net_strategy = df_active_net.mean(axis=1).fillna(0.0)
        daily_gross_strategy = df_active_gross.mean(axis=1).fillna(0.0)

        return {
            "daily_strategy_returns": daily_net_strategy,
            "gross_strategy_returns": daily_gross_strategy,
            "all_trades": all_trades,
            "cohort_returns_df": df_active_net,
            "cohort_metadata": cohort_metadata,
        }
