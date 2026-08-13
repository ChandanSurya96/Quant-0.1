"""Macro Strategy implementation with Markov Gating."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import apply_costs, metrics, turnover, walk_forward_signals
from .states import label_threshold
from .universe_data import approximate_carry


def cross_sectional_signals(close: pd.DataFrame, min_train: int = 756) -> pd.DataFrame:
    """
    Computes Mom, Value, and Carry z-scores for each asset at each day.
    To prevent look-ahead bias, this only uses trailing windows.
    Returns the combined z-score signal dataframe.
    """
    # 1. Momentum (12-month return ~ 252 days)
    mom = close.pct_change(252)
    
    # 2. Value (3-year negative z-score)
    mean_3y = close.rolling(252 * 3).mean()
    std_3y = close.rolling(252 * 3).std()
    val = -(close - mean_3y) / std_3y
    
    # 3. Carry
    car = approximate_carry(list(close.columns))
    # Expand carry to match dataframe shape
    car_df = pd.DataFrame(np.tile(car.values, (len(close), 1)), index=close.index, columns=close.columns)
    
    # We must only rank assets that have valid data for mom and val
    valid = mom.notna() & val.notna()
    
    # Initialize combined signals
    combined = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    
    # Fast cross-sectional z-score computation
    for i in range(min_train, len(close)):
        # Get valid row
        row_valid = valid.iloc[i]
        valid_cols = row_valid[row_valid].index
        
        if len(valid_cols) < 8:
            continue
            
        mom_row = mom.iloc[i][valid_cols]
        val_row = val.iloc[i][valid_cols]
        car_row = car_df.iloc[i][valid_cols]
        
        # Cross-sectional z-scores
        mom_z = (mom_row - mom_row.mean()) / (mom_row.std() + 1e-8)
        val_z = (val_row - val_row.mean()) / (val_row.std() + 1e-8)
        car_z = (car_row - car_row.mean()) / (car_row.std() + 1e-8)
        
        # Combine
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
    apply_markov_gate: bool = True,
    n_long: int = 4,
    n_short: int = 4
) -> dict:
    """
    Multi-asset walk-forward backtest.
    If apply_markov_gate is True, an asset's position is zeroed out if:
      - It's a Long candidate but its Markov signal is < -signal_threshold (BEAR)
      - It's a Short candidate but its Markov signal is > signal_threshold (BULL)
    """
    rets = close.pct_change().fillna(0.0)
    n, m = close.shape
    
    # 1. Compute Macro cross-sectional signals
    macro_signals = cross_sectional_signals(close, min_train)
    
    # 2. Compute Markov signals for all assets
    markov_sigs = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    
    if apply_markov_gate:
        for col in close.columns:
            asset_close = close[col]
            # Label
            lab = label_threshold(asset_close, window, threshold)
            # Reindex to match the main df index perfectly, filling SIDEWAYS (1)
            lab = lab.reindex(close.index).fillna(1).astype(int)
            # Get Markov signals
            m_sig = walk_forward_signals(
                lab.to_numpy(), matrix_kind=matrix_kind, stride=stride, 
                stride_mode=stride_mode, min_train=min_train
            )
            markov_sigs[col] = m_sig

    positions = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    
    # 3. Monthly Rebalancing
    # We only update positions every 21 days
    rebalance_freq = 21
    current_pos = np.zeros(m)
    
    for i in range(min_train, n - 1):
        if (i - min_train) % rebalance_freq == 0:
            row_sig = macro_signals.iloc[i]
            valid = row_sig.dropna()
            
            if len(valid) >= (n_long + n_short):
                sorted_sigs = valid.sort_values(ascending=False)
                
                # Identify candidates
                long_candidates = sorted_sigs.head(n_long).index
                short_candidates = sorted_sigs.tail(n_short).index
                
                new_pos = pd.Series(0.0, index=close.columns)
                
                for asset in long_candidates:
                    # Gating: don't buy if Markov predicts BEAR
                    if not apply_markov_gate or markov_sigs[asset].iloc[i] >= -signal_threshold:
                        new_pos[asset] = 1.0 / n_long
                        
                for asset in short_candidates:
                    # Gating: don't short if Markov predicts BULL
                    if not apply_markov_gate or markov_sigs[asset].iloc[i] <= signal_threshold:
                        new_pos[asset] = -1.0 / n_short
                        
                current_pos = new_pos.to_numpy()
                
        positions.iloc[i] = current_pos
        
    # 4. Calculate Equity Curve
    # Position set at close of t earns return of t+1
    effective = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    effective.iloc[1:] = positions.iloc[:-1].values
    
    # Portfolio daily returns (sum of position * asset return)
    strat_returns = (effective * rets).sum(axis=1)
    
    # Calculate costs (sum of absolute changes in weights * cost_bps)
    pos_array = effective.to_numpy()
    deltas = np.abs(np.diff(np.vstack((np.zeros(m), pos_array)), axis=0))
    total_cost = deltas.sum(axis=1) * (cost_bps / 10000.0)
    
    net_returns = strat_returns - total_cost
    
    # Subslice the active period
    active = slice(min_train + 1, n)
    s_a = strat_returns.iloc[active]
    net_a = net_returns.iloc[active]
    
    # For metrics compatibility, exposure is ratio of days where at least 1 asset is held
    total_gross = np.abs(pos_array).sum(axis=1)
    held_days = (total_gross > 0).astype(float)
    held_a = held_days[active]
    
    turnover_total = float(deltas[active].sum())
    turnover_dict = {
        "total": turnover_total,
        "per_bar": turnover_total / len(s_a) if len(s_a) else 0.0,
        "annualised": turnover_total / len(s_a) * 252.0 if len(s_a) else 0.0
    }
    
    name = "Macro Strategy + Markov Gate" if apply_markov_gate else "Macro Strategy (Baseline)"
    
    return {
        "index": s_a.index,
        "strategy_returns": s_a,
        "net_returns": net_a,
        "positions": effective.iloc[active],  # DataFrame of weights
        "metrics": metrics(s_a.to_numpy(), held_a),
        "net_metrics": metrics(net_a.to_numpy(), held_a),
        "turnover": turnover_dict,
        "name": name,
    }
