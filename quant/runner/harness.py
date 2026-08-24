"""Deterministic 30-day paper trading simulation and validation harness."""

from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd

from ..broker.paper_broker import PaperBroker
from ..persistence.database import DatabaseManager
from ..strategies.base import BaseStrategy
from .models import DailyPaperReport, PaperRunRecord, ValidationLedgerSummary
from .runner import PaperTradingRunner


class Deterministic30DayHarness:
    """Accelerated 30-day paper trading simulation harness across consecutive daily bars."""

    def __init__(
        self,
        runner: PaperTradingRunner,
        rebalance_cadence_days: int = 21,
    ) -> None:
        self.runner = runner
        self.cadence = rebalance_cadence_days

    def run_validation(
        self,
        daily_prices_df: pd.DataFrame,
        lookback_bars: int = 756,
        total_days: int = 30,
        expected_universe: list[str] | None = None,
    ) -> tuple[list[tuple[PaperRunRecord, DailyPaperReport]], ValidationLedgerSummary]:
        """Executes 30 consecutive daily trading cycles with holding weight drift and scheduled rebalancing."""
        if len(daily_prices_df) < lookback_bars + total_days:
            raise ValueError(
                f"daily_prices_df has {len(daily_prices_df)} bars, but requires at least "
                f"{lookback_bars + total_days} bars for lookback + 30 days validation."
            )

        results: list[tuple[PaperRunRecord, DailyPaperReport]] = []
        start_idx = len(daily_prices_df) - total_days

        for day_num in range(1, total_days + 1):
            curr_idx = start_idx + day_num
            window_df = daily_prices_df.iloc[:curr_idx]
            as_of_date = window_df.index[-1]
            is_rebalance_day = (day_num == 1) or ((day_num - 1) % self.cadence == 0)

            run_id = f"p6_val_day_{day_num:02d}_{pd.Timestamp(as_of_date).strftime('%Y%m%d')}"

            record, report = self.runner.run_once(
                run_id=run_id,
                as_of_date=as_of_date,
                market_data=window_df,
                expected_universe=expected_universe,
                is_rebalance_day=is_rebalance_day,
            )
            results.append((record, report))

        summary = self.runner.ledger.get_summary()
        return results, summary
