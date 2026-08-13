"""Integration of Cointegration Subsystem with Markov 2.0 Regime Framework."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .pipeline import walk_forward_cointegration
from ..backtest import apply_costs, metrics, turnover, walk_forward_signals
from ..states import label_threshold


def run_cointegration_markov_hybrid(
    prices: pd.DataFrame,
    *,
    train_window: int = 504,
    rebalance_freq: int = 21,
    window: int = 20,
    threshold: float = 0.05,
    signal_threshold: float = 0.10,
    cost_bps: float = 10.0,
    z_threshold: float = 1.5,
) -> dict:
    """Combines Cointegration Spread Trading with Markov 2.0 Regime Filtering.

    Architecture:
    1. Cointegration model generates mean-reverting spread u_t between pair assets.
    2. Trading signal: Long spread if z-score(u_t) < -z_threshold, Short if > +z_threshold.
    3. Markov 2.0 gating: Evaluates regime state on the spread series.
       - Rejects Long spread entries if Markov signal is BEAR (< -signal_threshold).
       - Rejects Short spread entries if Markov signal is BULL (> +signal_threshold).
    """
    # 1. Compute walk-forward cointegrated spread
    wf_res = walk_forward_cointegration(prices, train_window=train_window, rebalance_freq=rebalance_freq)
    spread = wf_res["spread"]
    is_coint = wf_res["is_cointegrated"]
    active_idx = wf_res["index"]

    # 2. Spread z-score (rolling 60 bars)
    spread_mean = spread.rolling(60).mean().fillna(0.0)
    spread_std = spread.rolling(60).std().fillna(1.0)
    z_score = (spread - spread_mean) / (spread_std + 1e-8)

    # 3. Compute Markov 2.0 regime signals on the spread
    lab = label_threshold(spread, window=window, threshold=threshold)
    lab_reindexed = lab.reindex(active_idx).fillna(1).astype(int)
    m_signals = walk_forward_signals(lab_reindexed.to_numpy(), min_train=252)

    # 4. Hybrid position sizing
    positions = pd.Series(0.0, index=active_idx)
    raw_positions = pd.Series(0.0, index=active_idx)

    for i in range(len(active_idx)):
        if not is_coint.iloc[i]:
            continue

        z = z_score.iloc[i]
        ms = m_signals[i]

        # Raw cointegration entry rule
        raw_pos = 0.0
        if z < -z_threshold:
            raw_pos = 1.0  # Long spread
        elif z > z_threshold:
            raw_pos = -1.0  # Short spread

        raw_positions.iloc[i] = raw_pos

        # Markov Regime Gate
        gated_pos = raw_pos
        if raw_pos == 1.0 and ms < -signal_threshold:
            gated_pos = 0.0  # Gate out Long entry during BEAR regime
        elif raw_pos == -1.0 and ms > signal_threshold:
            gated_pos = 0.0  # Gate out Short entry during BULL regime

        positions.iloc[i] = gated_pos

    # 5. Compute returns and apply costs
    # Approximate spread daily change return
    spread_diff = spread.diff().fillna(0.0)
    
    # Strategy return = position_{t-1} * delta_spread_t
    effective_pos = positions.shift(1).fillna(0.0)
    effective_raw = raw_positions.shift(1).fillna(0.0)

    strat_ret = effective_pos * spread_diff
    raw_ret = effective_raw * spread_diff

    net_strat_ret = apply_costs(strat_ret.to_numpy(), effective_pos.to_numpy(), cost_bps)
    net_raw_ret = apply_costs(raw_ret.to_numpy(), effective_raw.to_numpy(), cost_bps)

    return {
        "index": active_idx,
        "spread": spread,
        "z_score": z_score,
        "raw_returns": pd.Series(raw_ret, index=active_idx),
        "gated_returns": pd.Series(strat_ret, index=active_idx),
        "net_gated_returns": pd.Series(net_strat_ret, index=active_idx),
        "positions": effective_pos,
        "raw_metrics": metrics(raw_ret.to_numpy(), effective_raw.to_numpy()),
        "net_gated_metrics": metrics(net_strat_ret, effective_pos.to_numpy()),
        "turnover": turnover(effective_pos.to_numpy()),
    }
