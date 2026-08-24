"""Systematic Global Macro Strategy implementation."""

from datetime import datetime, timezone
from typing import Any
import numpy as np
import pandas as pd

from markov2.universe_data import approximate_carry
from ..core.interfaces import TargetPortfolio
from .base import AbstractStrategy


class SystematicMacroStrategy(AbstractStrategy):
    """Systematic Global Macro Strategy.

    Multi-asset cross-sectional factor allocation (Momentum + Value + Carry)
    with Rank Hysteresis and Inverse-Volatility Risk Parity.
    """

    def __init__(
        self,
        mom_window: int = 126,
        val_window: int = 756,
        vol_window: int = 60,
        rebalance_freq: int = 21,
        rebalance_cadence_days: int | None = None,
        n_long: int = 3,
        n_short: int = 3,
        max_long_exit_rank: int = 6,
        min_short_exit_rank: int = 7,
        use_hysteresis: bool = True,
        use_risk_parity: bool = True,
        min_train: int = 756,
    ) -> None:
        self.mom_window = mom_window
        self.val_window = val_window
        self.vol_window = vol_window
        self.rebalance_freq = rebalance_cadence_days if rebalance_cadence_days is not None else rebalance_freq
        self.n_long = n_long
        self.n_short = n_short
        self.max_long_exit_rank = max_long_exit_rank
        self.min_short_exit_rank = min_short_exit_rank
        self.use_hysteresis = use_hysteresis
        self.use_risk_parity = use_risk_parity
        self.min_train = min_train

    @property
    def strategy_id(self) -> str:
        return "systematic_macro_v1"

    def compute_factors(self, close: pd.DataFrame) -> pd.DataFrame:
        """Computes cross-sectional composite z-score signal."""
        # 1. Momentum
        mom = close.pct_change(self.mom_window)

        # 2. Value (negative z-score over val_window)
        mean_val = close.rolling(self.val_window).mean()
        std_val = close.rolling(self.val_window).std()
        val = -(close - mean_val) / (std_val + 1e-8)

        # 3. Carry
        car = approximate_carry(list(close.columns))
        car_df = pd.DataFrame(np.tile(car.values, (len(close), 1)), index=close.index, columns=close.columns)

        valid = mom.notna() & val.notna()
        combined = pd.DataFrame(np.nan, index=close.index, columns=close.columns)

        for i in range(self.min_train, len(close)):
            row_valid = valid.iloc[i]
            valid_cols = row_valid[row_valid].index

            if len(valid_cols) < (self.n_long + self.n_short):
                continue

            mom_row = mom.iloc[i][valid_cols]
            val_row = val.iloc[i][valid_cols]
            car_row = car_df.iloc[i][valid_cols]

            mom_z = (mom_row - mom_row.mean()) / (mom_row.std() + 1e-8)
            val_z = (val_row - val_row.mean()) / (val_row.std() + 1e-8)
            car_z = (car_row - car_row.mean()) / (car_row.std() + 1e-8)

            combined.iloc[i, combined.columns.get_indexer(valid_cols)] = (mom_z + val_z + car_z) / 3.0

        return combined

    def generate_target_weights(self, close_df: pd.DataFrame) -> pd.DataFrame:
        """Generates target weight matrix for each date t."""
        n, m = close_df.shape
        rets = close_df.pct_change().fillna(0.0)
        macro_signals = self.compute_factors(close_df)

        target_weights = pd.DataFrame(0.0, index=close_df.index, columns=close_df.columns)
        current_weights = pd.Series(0.0, index=close_df.columns)
        prev_long_assets: list[str] = []
        prev_short_assets: list[str] = []

        for i in range(self.min_train, n):
            if (i - self.min_train) % self.rebalance_freq == 0:
                row_sig = macro_signals.iloc[i]
                valid = row_sig.dropna()

                if len(valid) >= (self.n_long + self.n_short):
                    sorted_sigs = valid.sort_values(ascending=False)
                    rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}

                    # Volatility calculation over vol_window
                    past_rets = rets.iloc[max(0, i - self.vol_window):i]
                    vols = past_rets.std(ddof=1) * np.sqrt(252.0)
                    vols = vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)

                    # --- A. Rank Hysteresis Selection ---
                    if self.use_hysteresis and prev_long_assets:
                        retained_longs = [a for a in prev_long_assets if a in rank_map and rank_map[a] <= self.max_long_exit_rank]
                        if len(retained_longs) < self.n_long:
                            candidates = [a for a in sorted_sigs.index if a not in retained_longs]
                            retained_longs.extend(candidates[:self.n_long - len(retained_longs)])
                        long_selected = sorted(retained_longs, key=lambda x: rank_map.get(x, 999))[:self.n_long]
                    else:
                        long_selected = sorted_sigs.head(self.n_long).index.tolist()

                    if self.use_hysteresis and prev_short_assets:
                        retained_shorts = [a for a in prev_short_assets if a in rank_map and rank_map[a] >= self.min_short_exit_rank]
                        if len(retained_shorts) < self.n_short:
                            candidates = [a for a in sorted_sigs.index[::-1] if a not in retained_shorts]
                            retained_shorts.extend(candidates[:self.n_short - len(retained_shorts)])
                        short_selected = sorted(retained_shorts, key=lambda x: rank_map.get(x, 0), reverse=True)[:self.n_short]
                    else:
                        short_selected = sorted_sigs.tail(self.n_short).index.tolist()

                    prev_long_assets = long_selected
                    prev_short_assets = short_selected

                    # --- B. Risk Parity Sizing ---
                    new_w = pd.Series(0.0, index=close_df.columns)
                    if long_selected:
                        if self.use_risk_parity:
                            inv_v = 1.0 / (vols[long_selected] + 1e-8)
                            w_long = inv_v / inv_v.sum()
                            for a, w in w_long.items():
                                new_w[a] = float(w)
                        else:
                            for a in long_selected:
                                new_w[a] = 1.0 / len(long_selected)

                    if short_selected:
                        if self.use_risk_parity:
                            inv_v = 1.0 / (vols[short_selected] + 1e-8)
                            w_short = inv_v / inv_v.sum()
                            for a, w in w_short.items():
                                new_w[a] = -float(w)
                        else:
                            for a in short_selected:
                                new_w[a] = -1.0 / len(short_selected)

                    current_weights = new_w

            target_weights.iloc[i] = current_weights

        return target_weights

    def generate_target_portfolio(
        self,
        close_df: pd.DataFrame,
        as_of_date: Any = None,
    ) -> TargetPortfolio:
        """Generates a point-in-time TargetPortfolio from latest close prices."""
        weights_df = self.generate_target_weights(close_df)
        if as_of_date is not None:
            dt = pd.Timestamp(as_of_date)
            if dt in weights_df.index:
                row = weights_df.loc[dt]
            else:
                row = weights_df.iloc[-1]
        else:
            row = weights_df.iloc[-1]
            dt = pd.Timestamp(weights_df.index[-1])

        weights_dict = {sym: float(w) for sym, w in row.items() if abs(w) > 1e-6}
        ts = dt.to_pydatetime() if hasattr(dt, "to_pydatetime") else datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        return TargetPortfolio(
            timestamp=ts,
            strategy_id=self.strategy_id,
            target_weights=weights_dict,
            rebalance_horizon=self.rebalance_freq,
            metadata={"strategy": self.strategy_id, "as_of_date": str(dt)},
        )
