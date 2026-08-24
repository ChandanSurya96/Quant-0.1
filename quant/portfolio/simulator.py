"""Physical share-based portfolio simulator with realistic holding weight drift."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .drift import calculate_market_values, calculate_portfolio_nav, calculate_realized_weights
from .sizer import target_weights_to_shares


class PortfolioSimulator:
    """Simulates physical share and cash portfolio execution with natural weight drift."""

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        cost_bps: float = 10.0,
        commission_per_share: float = 0.0,
        slippage_bps: float = 0.0,
        borrow_cost_annual_bps: float = 0.0,
    ) -> None:
        self.initial_cash = float(initial_cash)
        self.cost_bps = float(cost_bps)
        self.commission_per_share = float(commission_per_share)
        self.slippage_bps = float(slippage_bps)
        self.borrow_cost_annual_bps = float(borrow_cost_annual_bps)

    def run(
        self,
        target_weights_df: pd.DataFrame,
        prices_df: pd.DataFrame,
        rebalance_freq: int = 21,
        rebalance_dates: list[pd.Timestamp | str] | None = None,
        start_idx: int = 0,
    ) -> dict:
        """Runs physical share-tracking simulation over the aligned price history.

        Parameters
        ----------
        target_weights_df : pd.DataFrame
            Target portfolio weights generated at the close of bar t (index: dates, cols: symbols).
        prices_df : pd.DataFrame
            Daily closing prices (index: dates, cols: symbols).
        rebalance_freq : int
            Rebalance interval in trading days (default 21).
        rebalance_dates : list, optional
            Explicit list of rebalance timestamps. If provided, overrides rebalance_freq.
        start_idx : int
            Warm-up index where trading begins (default 0).

        Returns
        -------
        dict containing daily NAV series, returns, holdings, trades, and summary metrics.
        """
        # Align indexes
        common_idx = target_weights_df.index.intersection(prices_df.index)
        if len(common_idx) < start_idx + 2:
            raise ValueError(f"Insufficient aligned bars: {len(common_idx)}, need at least {start_idx + 2}")

        target_w = target_weights_df.reindex(common_idx).fillna(0.0)
        prices = prices_df.reindex(common_idx).ffill()
        symbols = list(prices.columns)

        n = len(common_idx)
        cash = self.initial_cash
        holdings: dict[str, float] = {s: 0.0 for s in symbols}

        nav_series = pd.Series(index=common_idx, dtype=float)
        cash_series = pd.Series(index=common_idx, dtype=float)
        realized_weights_df = pd.DataFrame(index=common_idx, columns=symbols, dtype=float)
        holdings_df = pd.DataFrame(index=common_idx, columns=symbols, dtype=float)

        trades_list: list[dict] = []
        reb_date_set = set(pd.to_datetime(rebalance_dates)) if rebalance_dates is not None else None

        # Pre-start: fill initial state
        for t in range(start_idx):
            dt = common_idx[t]
            nav_series.iloc[t] = cash
            cash_series.iloc[t] = cash
            realized_weights_df.iloc[t] = 0.0
            holdings_df.iloc[t] = 0.0

        # Main walk-forward execution loop
        for t in range(start_idx, n):
            dt = common_idx[t]
            current_prices = prices.iloc[t].to_dict()

            # 1. Pre-trade mark-to-market NAV
            pre_nav = calculate_portfolio_nav(cash, holdings, current_prices)

            # 2. Rebalance determination (1-bar lag: target weights generated at t-1)
            is_rebalance = False
            if t > start_idx:
                if reb_date_set is not None:
                    is_rebalance = dt in reb_date_set
                else:
                    is_rebalance = ((t - (start_idx + 1)) % rebalance_freq == 0)

            if is_rebalance:
                # Target weights determined at close of t-1
                target_row = target_w.iloc[t - 1].to_dict()
                target_shares = target_weights_to_shares(target_row, pre_nav, current_prices)

                for sym in symbols:
                    target_q = target_shares.get(sym, 0.0)
                    current_q = holdings.get(sym, 0.0)
                    delta_q = target_q - current_q

                    if abs(delta_q) > 1e-6:
                        px = current_prices[sym]
                        traded_notional = abs(delta_q) * px

                        # Friction calculation
                        cost_turnover = traded_notional * (self.cost_bps / 10_000.0)
                        cost_comm = abs(delta_q) * self.commission_per_share
                        cost_slip = traded_notional * (self.slippage_bps / 10_000.0)
                        total_trade_cost = cost_turnover + cost_comm + cost_slip

                        if delta_q > 0:
                            # Buy or Cover Short: cash decreases
                            cash -= (delta_q * px + total_trade_cost)
                        else:
                            # Sell or Open Short: cash increases from proceeds
                            cash += (abs(delta_q) * px - total_trade_cost)

                        holdings[sym] = target_q
                        trades_list.append({
                            "date": dt,
                            "symbol": sym,
                            "side": "BUY" if delta_q > 0 else "SELL",
                            "delta_shares": delta_q,
                            "fill_price": px,
                            "traded_notional": traded_notional,
                            "cost": total_trade_cost,
                        })

            # 3. Short borrow cost deduction (if configured)
            if self.borrow_cost_annual_bps > 0:
                short_mv = sum(abs(q) * current_prices[s] for s, q in holdings.items() if q < 0)
                daily_borrow_fee = short_mv * (self.borrow_cost_annual_bps / 10_000.0) / 252.0
                cash -= daily_borrow_fee

            # 4. Post-trade mark-to-market snapshot
            post_nav, realized_w = calculate_realized_weights(cash, holdings, current_prices)
            nav_series.iloc[t] = post_nav
            cash_series.iloc[t] = cash
            holdings_df.iloc[t] = pd.Series(holdings)
            realized_weights_df.iloc[t] = pd.Series(realized_w)

        # Active evaluation slice
        active_idx = common_idx[start_idx:]
        active_nav = nav_series.loc[active_idx]
        daily_returns = active_nav.pct_change().fillna(0.0)

        # Compute summary metrics
        total_ret = (active_nav.iloc[-1] / active_nav.iloc[0]) - 1.0 if len(active_nav) else 0.0
        n_years = len(active_nav) / 252.0 if len(active_nav) else 1.0
        cagr = (active_nav.iloc[-1] / active_nav.iloc[0]) ** (1.0 / max(1e-4, n_years)) - 1.0 if len(active_nav) and active_nav.iloc[0] > 0 else 0.0

        r_arr = daily_returns.to_numpy()
        sd = np.std(r_arr, ddof=1) if len(r_arr) > 1 else 0.0
        vol = float(sd * np.sqrt(252.0)) if sd > 0 else 0.0
        sharpe = float((np.mean(r_arr) / sd) * np.sqrt(252.0)) if sd > 0 else 0.0

        # Drawdown calculation
        peak = active_nav.cummax()
        dd = (active_nav - peak) / peak
        max_dd = float(dd.min()) if len(dd) else 0.0

        trades_df = pd.DataFrame(trades_list)
        total_costs = float(trades_df["cost"].sum()) if not trades_df.empty else 0.0
        total_traded_notional = float(trades_df["traded_notional"].sum()) if not trades_df.empty else 0.0
        avg_nav = float(active_nav.mean()) if len(active_nav) else self.initial_cash
        annualized_turnover = (total_traded_notional / max(1.0, avg_nav)) / max(1e-4, n_years)

        metrics_dict = {
            "initial_cash": self.initial_cash,
            "final_nav": float(active_nav.iloc[-1]),
            "total_return": total_ret,
            "cagr": cagr,
            "annualized_volatility": vol,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "total_costs": total_costs,
            "total_traded_notional": total_traded_notional,
            "annualized_turnover": annualized_turnover,
            "total_trades": len(trades_df),
        }

        return {
            "index": active_idx,
            "nav": active_nav,
            "returns": daily_returns,
            "cash": cash_series.loc[active_idx],
            "holdings": holdings_df.loc[active_idx],
            "realized_weights": realized_weights_df.loc[active_idx],
            "trades": trades_df,
            "metrics": metrics_dict,
        }
