"""Unit tests for strategy signal parity between legacy markov2 and new quant.strategies."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from markov2.macro import cross_sectional_signals
from quant.strategies.macro import SystematicMacroStrategy

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "synthetic_macro_12etf.csv"


def test_macro_factor_signals_parity():
    """Asserts that factor computations (Momentum + Value + Carry) are identical."""
    df = pd.read_csv(FIXTURE_PATH, index_col=0, parse_dates=True)

    # Legacy
    legacy_factors = cross_sectional_signals(df, min_train=756, mom_window=126, val_window=756)

    # New (with all 3 factors enabled for 3-factor parity)
    strat = SystematicMacroStrategy(min_train=756, mom_window=126, val_window=756, use_value=True, use_carry=True)
    new_factors = strat.compute_factors(df)

    # Compare non-NaN elements
    valid_mask = legacy_factors.notna()
    diff = np.abs(legacy_factors[valid_mask] - new_factors[valid_mask]).max().max()
    assert diff < 1e-7, f"Factor signals diverged by {diff}"


def test_macro_strategy_target_weight_parity():
    """Asserts bit-exact parity of Target Weights between legacy and new macro strategy."""
    df = pd.read_csv(FIXTURE_PATH, index_col=0, parse_dates=True)

    # New Strategy Target Weights with legacy 2.0x Mom+Val+Car parameters
    strat = SystematicMacroStrategy(
        min_train=756,
        mom_window=126,
        val_window=756,
        rebalance_freq=21,
        target_sleeve_gross=1.0,
        max_single_position_weight=1.0,
        use_value=True,
        use_carry=True,
    )
    new_weights = strat.generate_target_weights(df)

    # Reconstruct Legacy Target Weights exactly as in markov2.macro.walk_forward_macro
    rets = df.pct_change().fillna(0.0)
    n, m = df.shape
    macro_signals = cross_sectional_signals(df, 756, mom_window=126, val_window=756)
    legacy_positions = pd.DataFrame(0.0, index=df.index, columns=df.columns)
    current_pos = np.zeros(m)
    prev_long_assets: list[str] = []
    prev_short_assets: list[str] = []

    for i in range(756, n):
        if (i - 756) % 21 == 0:
            row_sig = macro_signals.iloc[i].dropna()
            if len(row_sig) >= 6:
                sorted_sigs = row_sig.sort_values(ascending=False)
                rank_map = {asset: r + 1 for r, (asset, _) in enumerate(sorted_sigs.items())}
                past_rets = rets.iloc[max(0, i - 60):i]
                vols = past_rets.std(ddof=1) * np.sqrt(252.0)
                vols = vols.replace(0, np.nan).fillna(vols.mean()).fillna(0.15)

                # Hysteresis
                if prev_long_assets:
                    retained_longs = [a for a in prev_long_assets if a in rank_map and rank_map[a] <= 6]
                    if len(retained_longs) < 3:
                        candidates = [a for a in sorted_sigs.index if a not in retained_longs]
                        retained_longs.extend(candidates[:3 - len(retained_longs)])
                    long_selected = sorted(retained_longs, key=lambda x: rank_map.get(x, 999))[:3]
                else:
                    long_selected = sorted_sigs.head(3).index.tolist()

                if prev_short_assets:
                    retained_shorts = [a for a in prev_short_assets if a in rank_map and rank_map[a] >= 7]
                    if len(retained_shorts) < 3:
                        candidates = [a for a in sorted_sigs.index[::-1] if a not in retained_shorts]
                        retained_shorts.extend(candidates[:3 - len(retained_shorts)])
                    short_selected = sorted(retained_shorts, key=lambda x: rank_map.get(x, 0), reverse=True)[:3]
                else:
                    short_selected = sorted_sigs.tail(3).index.tolist()

                prev_long_assets = long_selected
                prev_short_assets = short_selected

                new_pos = pd.Series(0.0, index=df.columns)
                inv_v = 1.0 / (vols[long_selected] + 1e-8)
                w_long = inv_v / inv_v.sum()
                for a, w in w_long.items():
                    new_pos[a] = float(w)
                inv_v = 1.0 / (vols[short_selected] + 1e-8)
                w_short = inv_v / inv_v.sum()
                for a, w in w_short.items():
                    new_pos[a] = -float(w)
                current_pos = new_pos.to_numpy()

        legacy_positions.iloc[i] = current_pos

    # Compare from min_train to n-1
    diff = np.abs(legacy_positions.iloc[756:] - new_weights.iloc[756:]).max().max()
    assert diff < 1e-7, f"Target weights diverged by {diff}"
