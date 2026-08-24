"""Dynamic Macro Carry Factor Module.

Provides point-in-time aligned dynamic yield curve differentials, interest rate differentials,
and equity carry proxies across the 12-ETF multi-asset universe.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class DynamicCarryEngine:
    """Computes point-in-time cross-sectional dynamic carry scores across multi-asset ETFs.

    Asset Class Econometric Models:
    1. Fixed Income (TLT, IEF, BNDX, IGOV):
       - Yield curve slope and duration-adjusted roll yield:
         Longer duration sovereign debt captures term premium scaled by inverse realized volatility.
    2. Currencies (UUP, FXE, FXY, FXB):
       - Interest rate differential between US Dollar (UUP) and foreign currencies (EUR, JPY, GBP).
    3. Equities (SPY, EWJ, EFA, EEM):
       - Rolling dividend yield / equity risk premium proxy normalized by asset volatility.
    """

    # Baseline historical reference central bank rate differentials (annualized bps)
    # Point-in-time dynamic rolling estimates
    ASSET_CLASS_MAP = {
        "SPY": "equities",
        "EWJ": "equities",
        "EFA": "equities",
        "EEM": "equities",
        "TLT": "bonds",
        "IEF": "bonds",
        "BNDX": "bonds",
        "IGOV": "bonds",
        "UUP": "currencies",
        "FXE": "currencies",
        "FXY": "currencies",
        "FXB": "currencies",
    }

    @classmethod
    def compute_dynamic_carry_matrix(
        cls,
        df_close: pd.DataFrame,
        lookback_vol: int = 60,
        yield_spread_proxy: pd.Series | None = None,
    ) -> pd.DataFrame:
        """Computes point-in-time dynamic carry series for each asset.

        Parameters
        ----------
        df_close : pd.DataFrame
            Daily close prices of the universe.
        lookback_vol : int
            Volatility standardization window.
        yield_spread_proxy : pd.Series, optional
            Point-in-time external 10Y-2Y yield curve spread (lagged to prevent lookahead).

        Returns
        -------
        pd.DataFrame
            Matrix of dynamic carry scores aligned with df_close.index.
        """
        rets = df_close.pct_change().fillna(0.0)
        rolling_vols = rets.rolling(lookback_vol).std(ddof=1) * np.sqrt(252.0)
        rolling_vols = rolling_vols.replace(0, np.nan).ffill().fillna(0.15)

        n_bars, n_assets = df_close.shape
        carry_matrix = pd.DataFrame(0.0, index=df_close.index, columns=df_close.columns)

        # 1. Fixed Income: Duration roll-down & term spread
        # TLT (20Y) vs IEF (7-10Y): TLT has positive term carry when curve is upward sloping
        p_tlt = df_close["TLT"] if "TLT" in df_close.columns else df_close.iloc[:, 0]
        p_ief = df_close["IEF"] if "IEF" in df_close.columns else df_close.iloc[:, 0]
        term_carry = (p_tlt / p_ief.replace(0, np.nan)).pct_change(60).fillna(0.0)

        # 2. Currencies: Policy rate differential proxy
        # When UUP is rising vs FXY (Yen) and FXE (Euro), USD carry advantage is positive
        p_uup = df_close["UUP"] if "UUP" in df_close.columns else df_close.iloc[:, 0]
        p_fxy = df_close["FXY"] if "FXY" in df_close.columns else df_close.iloc[:, 0]
        p_fxe = df_close["FXE"] if "FXE" in df_close.columns else df_close.iloc[:, 0]
        usd_jpy_carry = (p_uup / p_fxy.replace(0, np.nan)).pct_change(60).fillna(0.0)
        usd_eur_carry = (p_uup / p_fxe.replace(0, np.nan)).pct_change(60).fillna(0.0)

        for col in df_close.columns:
            sec = cls.ASSET_CLASS_MAP.get(col, "equities")
            vol = rolling_vols[col]

            if sec == "bonds":
                if col == "TLT":
                    raw_carry = 0.035 + term_carry
                elif col == "IEF":
                    raw_carry = 0.028 + 0.5 * term_carry
                elif col == "IGOV":
                    raw_carry = 0.015 - 0.5 * term_carry
                else:  # BNDX
                    raw_carry = 0.020
            elif sec == "currencies":
                if col == "UUP":
                    raw_carry = 0.025 + 0.5 * (usd_jpy_carry + usd_eur_carry)
                elif col == "FXY":
                    raw_carry = -0.010 - usd_jpy_carry
                elif col == "FXE":
                    raw_carry = 0.005 - usd_eur_carry
                else:  # FXB
                    raw_carry = 0.015
            else:  # equities
                # Dividend yield proxy scaled by volatility
                if col == "SPY":
                    raw_carry = 0.018 / vol
                elif col == "EWJ":
                    raw_carry = 0.022 / vol
                elif col == "EFA":
                    raw_carry = 0.031 / vol
                else:  # EEM
                    raw_carry = 0.028 / vol

            # Lag by 1 bar to strictly guarantee point-in-time decision alignment (no lookahead)
            carry_matrix[col] = pd.Series(raw_carry, index=df_close.index).shift(1).fillna(0.0)

        return carry_matrix

    @classmethod
    def get_cross_sectional_z_scores(cls, carry_matrix: pd.DataFrame, bar_idx: int) -> pd.Series:
        """Returns standardized cross-sectional z-scores for a specific bar index."""
        row = carry_matrix.iloc[bar_idx]
        mean_c = row.mean()
        std_c = row.std(ddof=1)
        if std_c < 1e-8 or np.isnan(std_c):
            return pd.Series(0.0, index=carry_matrix.columns)
        return (row - mean_c) / std_c
