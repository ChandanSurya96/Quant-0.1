"""Macro Strategy implementation with Rank Hysteresis & Inverse Volatility Risk Parity."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import apply_costs, metrics, turnover, walk_forward_signals
from .states import label_threshold
from .universe_data import approximate_carry


def cross_sectional_signals(
    close: pd.DataFrame,
    min_train: int = 756,
    mom_window: int = 252,
    val_window: int = 756,
) -> pd.DataFrame:
    """
    Computes Mom, Value, and Carry z-scores for each asset at each day.
    To prevent look-ahead bias, this only uses trailing windows.
    Returns the combined z-score signal dataframe.
    """
    # 1. Momentum
    mom = close.pct_change(mom_window)
    
    # 2. Value (negative z-score over val_window)
    mean_val = close.rolling(val_window).mean()
    std_val = close.rolling(val_window).std()
    val = -(close - mean_val) / std_val
    
    # 3. Carry
    car = approximate_carry(list(close.columns))
    car_df = pd.DataFrame(np.tile(car.values, (len(close), 1)), index=close.index, columns=close.columns)
    
    valid = mom.notna() & val.notna()
    combined = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    
    for i in range(min_train, len(close)):
        row_valid = valid.iloc[i]
        valid_cols = row_valid[row_valid].index
        
        if len(valid_cols) < 6:
            continue
            
        mom_row = mom.iloc[i][valid_cols]
        val_row = val.iloc[i][valid_cols]
        car_row = car_df.iloc[i][valid_cols]
        
        mom_z = (mom_row - mom_row.mean()) / (mom_row.std() + 1e-8)
        val_z = (val_row - val_row.mean()) / (val_row.std() + 1e-8)
        car_z = (car_row - car_row.mean()) / (car_row.std() + 1e-8)
        
        combined.iloc[i, combined.columns.get_indexer(valid_cols)] = (mom_z + val_z + car_z) / 3.0
        
    return combined


def walk_forward_macro(
    close: pd.DataFrame,
    window: int = 20,
    threshold: float = 0.05,
    matrix_kind: str = "stride",
    stride: int = 20,
    stride_mode: str = "phase",
    min_train: int = 756,
    signal_threshold: float = 0.10,
    cost_bps: float = 10.0,
    apply_markov_gate: bool = False,  # Deprecated single-asset Markov timing model disabled
    n_long: int = 3,
    n_short: int = 3,
    use_hysteresis: bool = True,
    use_risk_parity: bool = True,
    vol_window: int = 60,
    max_long_exit_rank: int = 6,
    min_short_exit_rank: int = 7,
    mom_window: int = 126,  # 6 Months
    val_window: int = 756,  # 3 Years
) -> dict:
    """
    Multi-asset walk-forward backtest supporting Rank Hysteresis and Inverse-Volatility Risk Parity.
    """
    rets = close.pct_change().fillna(0.0)
    n, m = close.shape
    
    # 1. Compute Macro cross-sectional signals
    macro_signals = cross_sectional_signals(close, min_train, mom_window=mom_window, val_window=val_window)
    
    # 2. Compute Markov signals for all assets (if enabled)
    markov_sigs = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    
    if apply_markov_gate:
        for col in close.columns:
            asset_close = close[col]
            lab = label_threshold(asset_close, window, threshold)
            lab = lab.reindex(close.index).fillna(1).astype(int)
            m_sig = walk_forward_signals(
                lab.to_numpy(), matrix_kind=matrix_kind, stride=stride, 
                stride_mode=stride_mode, min_train=min_train
            )
            markov_sigs[col] = m_sig

    positions = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    
    # 3. Monthly Rebalancing with Hysteresis and Risk Parity
    rebalance_freq = 21
    current_pos = np.zeros(m)
    prev_long_assets: list[str] = []
    prev_short_assets: list[str] = []
    
    for i in range(min_train, n - 1):
        if (i - min_train) % rebalance_freq == 0:
            row_sig = macro_signals.iloc[i]
            valid = row_sig.dropna()
            
            if len(valid) >= (n_long + n_short):
                sorted_sigs = valid.sort_values(ascending=False)
                n_val = len(sorted_sigs)
                rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}
                
                # Calculate trailing Realized Volatility over last vol_window bars
                past_rets = rets.iloc[max(0, i - vol_window):i]
                vols = past_rets.std(ddof=1) * np.sqrt(252.0)
                vols = vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)
                
                # --- A. Rank Hysteresis Selection ---
                if use_hysteresis and prev_long_assets:
                    # Retain previous longs whose current rank <= max_long_exit_rank (6)
                    retained_longs = [a for a in prev_long_assets if a in rank_map and rank_map[a] <= max_long_exit_rank]
                    # Fill remaining long slots with top ranked assets
                    if len(retained_longs) < n_long:
                        candidates = [a for a in sorted_sigs.index if a not in retained_longs]
                        retained_longs.extend(candidates[:n_long - len(retained_longs)])
                    # Sort retained longs by current z-score and pick top n_long
                    long_selected = sorted(retained_longs, key=lambda x: rank_map.get(x, 999))[:n_long]
                else:
                    long_selected = sorted_sigs.head(n_long).index.tolist()

                if use_hysteresis and prev_short_assets:
                    # Retain previous shorts whose current rank >= min_short_exit_rank (7)
                    retained_shorts = [a for a in prev_short_assets if a in rank_map and rank_map[a] >= min_short_exit_rank]
                    # Fill remaining short slots with worst ranked assets
                    if len(retained_shorts) < n_short:
                        candidates = [a for a in sorted_sigs.index[::-1] if a not in retained_shorts]
                        retained_shorts.extend(candidates[:n_short - len(retained_shorts)])
                    # Sort retained shorts by current rank descending and pick bottom n_short
                    short_selected = sorted(retained_shorts, key=lambda x: rank_map.get(x, 0), reverse=True)[:n_short]
                else:
                    short_selected = sorted_sigs.tail(n_short).index.tolist()

                prev_long_assets = long_selected
                prev_short_assets = short_selected

                # --- B. Risk Parity / Inverse Volatility Weighting ---
                new_pos = pd.Series(0.0, index=close.columns)

                # Filter Markov Gating if enabled
                long_active = [a for a in long_selected if not apply_markov_gate or markov_sigs[a].iloc[i] >= -signal_threshold]
                short_active = [a for a in short_selected if not apply_markov_gate or markov_sigs[a].iloc[i] <= signal_threshold]

                if long_active:
                    if use_risk_parity:
                        inv_v = 1.0 / (vols[long_active] + 1e-8)
                        w_long = inv_v / inv_v.sum()
                        for a, w in w_long.items():
                            new_pos[a] = float(w)
                    else:
                        for a in long_active:
                            new_pos[a] = 1.0 / len(long_active)

                if short_active:
                    if use_risk_parity:
                        inv_v = 1.0 / (vols[short_active] + 1e-8)
                        w_short = inv_v / inv_v.sum()
                        for a, w in w_short.items():
                            new_pos[a] = -float(w)
                    else:
                        for a in short_active:
                            new_pos[a] = -1.0 / len(short_active)

                current_pos = new_pos.to_numpy()
                
        positions.iloc[i] = current_pos
        
    # 4. Calculate Equity Curve
    effective = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    effective.iloc[1:] = positions.iloc[:-1].values
    
    # Portfolio daily returns
    strat_returns = (effective * rets).sum(axis=1)
    
    # Calculate costs (sum of absolute changes in weights * cost_bps)
    pos_array = effective.to_numpy()
    deltas = np.abs(np.diff(np.vstack((np.zeros(m), pos_array)), axis=0))
    total_cost = deltas.sum(axis=1) * (cost_bps / 10000.0)
    
    net_returns = strat_returns - total_cost
    
    # Subslice active period
    active = slice(min_train + 1, n)
    s_a = strat_returns.iloc[active]
    net_a = net_returns.iloc[active]
    
    total_gross = np.abs(pos_array).sum(axis=1)
    held_days = (total_gross > 0).astype(float)
    held_a = held_days[active]
    
    turnover_total = float(deltas[active].sum())
    turnover_dict = {
        "total": turnover_total,
        "per_bar": turnover_total / len(s_a) if len(s_a) else 0.0,
        "annualised": turnover_total / len(s_a) * 252.0 if len(s_a) else 0.0
    }
    
    name = "Macro Strategy (Hysteresis + Risk Parity)"
    if apply_markov_gate:
        name += " + Markov Gate"
    
    return {
        "index": s_a.index,
        "strategy_returns": s_a,
        "net_returns": net_a,
        "positions": effective.iloc[active],
        "metrics": metrics(s_a.to_numpy(), held_a),
        "net_metrics": metrics(net_a.to_numpy(), held_a),
        "turnover": turnover_dict,
        "name": name,
    }
