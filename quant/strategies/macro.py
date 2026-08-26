"""Systematic Macro Cross-Sectional Strategy with gross 1.0 normalization and position clipping."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from markov2.universe_data import approximate_carry

from ..core.interfaces import TargetPortfolio
from .base import BaseStrategy


def size_sleeve(
    selected_assets: list[str],
    vols: pd.Series,
    target_gross: float = 0.50,
    max_single: float = 0.25,
    use_risk_parity: bool = True,
) -> dict[str, float]:
    """Computes sleeve weights normalized to target_gross with strict max_single clipping."""
    if not selected_assets:
        return {}
    if not use_risk_parity:
        equal_w = min(target_gross / len(selected_assets), max_single)
        return {a: equal_w for a in selected_assets}

    inv_v = 1.0 / (vols[selected_assets] + 1e-8)
    raw_w = (inv_v / inv_v.sum()) * target_gross
    weights = raw_w.to_dict()

    for _ in range(len(selected_assets)):
        capped = {a: min(w, max_single) for a, w in weights.items()}
        excess = target_gross - sum(capped.values())
        uncapped = [a for a, w in capped.items() if w < max_single - 1e-6]
        if excess <= 1e-6 or not uncapped:
            weights = capped
            break
        uncapped_inv_v = inv_v[uncapped]
        redist = (uncapped_inv_v / uncapped_inv_v.sum()) * excess
        for a in uncapped:
            capped[a] += float(redist[a])
        weights = capped

    return weights


class SystematicMacroStrategy(BaseStrategy):
    """Systematic Macro multi-asset cross-sectional momentum strategy.

    Canonical Gross 1.0 Dollar-Neutral Mandate:
    - Long Sleeve: 50% NAV across top n_long assets (max single position 25%)
    - Short Sleeve: -50% NAV across bottom n_short assets (max single position 25%)
    - Total Gross Exposure: 1.0x NAV
    """

    def __init__(
        self,
        strategy_id: str = "systematic_macro_v1",
        mom_window: int = 126,
        val_window: int = 756,
        vol_window: int = 60,
        rebalance_cadence_days: int = 21,
        rebalance_freq: int | None = None,
        min_train: int = 756,
        n_long: int = 3,
        n_short: int = 3,
        use_momentum: bool = True,
        use_value: bool = False,
        use_carry: bool = False,
        use_hysteresis: bool = True,
        use_risk_parity: bool = True,
        max_long_entry_rank: int = 3,
        min_long_exit_rank: int = 6,
        min_short_entry_rank: int = 10,
        min_short_exit_rank: int = 7,
        target_sleeve_gross: float = 0.50,
        max_single_position_weight: float = 0.25,
    ) -> None:
        self._strategy_id = str(strategy_id)
        self._rebalance_cadence_days = int(rebalance_freq if rebalance_freq is not None else rebalance_cadence_days)
        self.rebalance_freq = self._rebalance_cadence_days
        self.mom_window = int(mom_window)
        self.val_window = int(val_window)
        self.vol_window = int(vol_window)
        self.min_train = int(min_train)
        self.n_long = int(n_long)
        self.n_short = int(n_short)
        self.use_momentum = bool(use_momentum)
        self.use_value = bool(use_value)
        self.use_carry = bool(use_carry)
        self.use_hysteresis = bool(use_hysteresis)
        self.use_risk_parity = bool(use_risk_parity)
        self.max_long_entry_rank = int(max_long_entry_rank)
        self.min_long_exit_rank = int(min_long_exit_rank)
        self.min_short_entry_rank = int(min_short_entry_rank)
        self.min_short_exit_rank = int(min_short_exit_rank)
        self.target_sleeve_gross = float(target_sleeve_gross)
        self.max_single_position_weight = float(max_single_position_weight)

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def rebalance_cadence_days(self) -> int:
        return self._rebalance_cadence_days

    def compute_factors(self, close_df: pd.DataFrame) -> pd.DataFrame:
        """Computes factor signals matching legacy markov2.macro.cross_sectional_signals."""
        mom = close_df.pct_change(self.mom_window)
        mean_val = close_df.rolling(self.val_window).mean()
        std_val = close_df.rolling(self.val_window).std()
        val = -(close_df - mean_val) / std_val
        car = approximate_carry(list(close_df.columns))
        car_df = pd.DataFrame(np.tile(car.values, (len(close_df), 1)), index=close_df.index, columns=close_df.columns)

        valid = mom.notna() & val.notna()
        combined = pd.DataFrame(np.nan, index=close_df.index, columns=close_df.columns)

        for i in range(self.min_train, len(close_df)):
            row_valid = valid.iloc[i]
            valid_cols = row_valid[row_valid].index

            if len(valid_cols) < (self.n_long + self.n_short):
                continue

            signals = []
            if self.use_momentum:
                mom_row = mom.iloc[i][valid_cols]
                mom_z = (mom_row - mom_row.mean()) / (mom_row.std() + 1e-8)
                signals.append(mom_z)
            if self.use_value:
                val_row = val.iloc[i][valid_cols]
                val_z = (val_row - val_row.mean()) / (val_row.std() + 1e-8)
                signals.append(val_z)
            if self.use_carry:
                car_row = car_df.iloc[i][valid_cols]
                car_z = (car_row - car_row.mean()) / (car_row.std() + 1e-8)
                signals.append(car_z)

            if not signals:
                # Default 3-factor parity if none selected
                mom_row = mom.iloc[i][valid_cols]
                val_row = val.iloc[i][valid_cols]
                car_row = car_df.iloc[i][valid_cols]
                mom_z = (mom_row - mom_row.mean()) / (mom_row.std() + 1e-8)
                val_z = (val_row - val_row.mean()) / (val_row.std() + 1e-8)
                car_z = (car_row - car_row.mean()) / (car_row.std() + 1e-8)
                combined.iloc[i, combined.columns.get_indexer(valid_cols)] = (mom_z + val_z + car_z) / 3.0
            else:
                combined.iloc[i, combined.columns.get_indexer(valid_cols)] = sum(signals) / len(signals)

        return combined

    def generate_target_weights(self, close_df: pd.DataFrame) -> pd.DataFrame:
        """Computes target weight history over close_df."""
        n = len(close_df)
        rets = close_df.pct_change().fillna(0.0)
        mom = close_df.pct_change(self.mom_window)

        mean_val = close_df.rolling(self.val_window).mean()
        std_val = close_df.rolling(self.val_window).std()
        val = -(close_df - mean_val) / std_val

        car = approximate_carry(list(close_df.columns))
        car_df = pd.DataFrame(np.tile(car.values, (len(close_df), 1)), index=close_df.index, columns=close_df.columns)

        target_weights = pd.DataFrame(0.0, index=close_df.index, columns=close_df.columns)
        current_weights = pd.Series(0.0, index=close_df.columns)
        prev_long_assets: list[str] = []
        prev_short_assets: list[str] = []

        start_idx = min(self.min_train, n)

        for i in range(start_idx, n):
            if (i - start_idx) % self.rebalance_freq == 0:
                signals = []
                if self.use_momentum:
                    m_row = mom.iloc[i]
                    signals.append((m_row - m_row.mean()) / (m_row.std() + 1e-8))
                if self.use_value:
                    v_row = val.iloc[i]
                    signals.append((v_row - v_row.mean()) / (v_row.std() + 1e-8))
                if self.use_carry:
                    c_row = car_df.iloc[i]
                    signals.append((c_row - c_row.mean()) / (c_row.std() + 1e-8))

                if signals:
                    combined_sig = sum(signals) / len(signals)
                else:
                    combined_sig = pd.Series(0.0, index=close_df.columns)

                valid = combined_sig.dropna()
                if len(valid) >= (self.n_long + self.n_short):
                    sorted_sigs = valid.sort_values(ascending=False)
                    rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}

                    past_rets = rets.iloc[max(0, i - self.vol_window):i]
                    vols = past_rets.std(ddof=1) * np.sqrt(252.0)
                    vols = vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)

                    if self.use_hysteresis and prev_long_assets:
                        retained_longs = [a for a in prev_long_assets if a in rank_map and rank_map[a] <= self.min_long_exit_rank]
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

                    # Sizing with target_sleeve_gross and max_single_position_weight
                    long_weights = size_sleeve(
                        long_selected,
                        vols,
                        target_gross=self.target_sleeve_gross,
                        max_single=self.max_single_position_weight,
                        use_risk_parity=self.use_risk_parity,
                    )
                    short_weights = size_sleeve(
                        short_selected,
                        vols,
                        target_gross=self.target_sleeve_gross,
                        max_single=self.max_single_position_weight,
                        use_risk_parity=self.use_risk_parity,
                    )

                    new_w = pd.Series(0.0, index=close_df.columns)
                    for a, w in long_weights.items():
                        new_w[a] = float(w)
                    for a, w in short_weights.items():
                        new_w[a] = -float(w)

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
