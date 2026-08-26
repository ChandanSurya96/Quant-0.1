"""Physical share-based portfolio simulator with realistic holding weight drift, discrete shares, and cash interest."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..statistics.sharpe import calculate_sharpe_statistics
from .drift import calculate_portfolio_nav, calculate_realized_weights
from .sizer import target_weights_to_shares


class PortfolioSimulator:
    """Simulates physical discrete-share and cash portfolio execution with natural weight drift."""

    def __init__(
        self,
        initial_cash: float = 100_000.0,
        cost_bps: float = 10.0,
        commission_per_share: float = 0.0,
        slippage_bps: float = 0.0,
        borrow_cost_annual_bps: float = 0.0,
        risk_free_rate_annual: float | pd.Series = 0.0,
        margin_debit_spread_bps: float = 150.0,
        short_proceeds_credit_pct: float = 0.0,
        discrete_shares: bool = True,
        min_tradeable_notional: float = 10.0,
    ) -> None:
        self.initial_cash = float(initial_cash)
        self.cost_bps = float(cost_bps)
        self.commission_per_share = float(commission_per_share)
        self.slippage_bps = float(slippage_bps)
        self.borrow_cost_annual_bps = float(borrow_cost_annual_bps)
        self.risk_free_rate_annual = risk_free_rate_annual
        self.margin_debit_spread_bps = float(margin_debit_spread_bps)
        self.short_proceeds_credit_pct = float(short_proceeds_credit_pct)
        self.discrete_shares = discrete_shares
        self.min_tradeable_notional = float(min_tradeable_notional)

    def run(
        self,
        target_weights_df: pd.DataFrame,
        prices_df: pd.DataFrame,
        rebalance_freq: int = 21,
        rebalance_dates: list[pd.Timestamp | str] | None = None,
        start_idx: int = 0,
        rf_series: pd.Series | None = None,
    ) -> dict[str, Any]:
        """Runs physical share-tracking simulation over the aligned price history."""
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

            # 1. Daily cash yield / interest & margin debt financing
            if isinstance(self.risk_free_rate_annual, pd.Series):
                rf_ann = float(self.risk_free_rate_annual.get(dt, 0.0))
            elif rf_series is not None and dt in rf_series.index:
                rf_ann = float(rf_series.loc[dt])
            else:
                rf_ann = float(self.risk_free_rate_annual)

            rf_daily = rf_ann / 252.0
            if cash > 0 and rf_daily > 0:
                short_notional = sum(abs(q) * current_prices[s] for s, q in holdings.items() if q < 0)
                unencumbered_cash = max(0.0, cash - short_notional)
                short_proceeds = min(cash, short_notional)
                credit_basis = unencumbered_cash + (self.short_proceeds_credit_pct * short_proceeds)
                cash += credit_basis * rf_daily
            elif cash < 0:
                # Charge margin financing (RF + margin debit spread)
                margin_rate_daily = (rf_ann + (self.margin_debit_spread_bps / 10_000.0)) / 252.0
                cash -= abs(cash) * margin_rate_daily

            # 2. Pre-trade mark-to-market NAV
            pre_nav = calculate_portfolio_nav(cash, holdings, current_prices)

            # 3. Rebalance determination (1-bar lag: target weights generated at t-1)
            is_rebalance = False
            if t > start_idx:
                if reb_date_set is not None:
                    is_rebalance = dt in reb_date_set
                else:
                    is_rebalance = ((t - (start_idx + 1)) % rebalance_freq == 0)

            if is_rebalance:
                # Target weights determined at close of t-1
                target_row = target_w.iloc[t - 1].to_dict()
                target_shares = target_weights_to_shares(
                    target_row,
                    pre_nav,
                    current_prices,
                    discrete_shares=self.discrete_shares,
                    min_tradeable_notional=self.min_tradeable_notional,
                )

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

            # 4. Short borrow cost deduction
            if self.borrow_cost_annual_bps > 0:
                short_mv = sum(abs(q) * current_prices[s] for s, q in holdings.items() if q < 0)
                daily_borrow_fee = short_mv * (self.borrow_cost_annual_bps / 10_000.0) / 252.0
                cash -= daily_borrow_fee

            # 5. Post-trade mark-to-market snapshot
            post_nav, realized_w = calculate_realized_weights(cash, holdings, current_prices)
            nav_series.iloc[t] = post_nav
            cash_series.iloc[t] = cash
            holdings_df.iloc[t] = pd.Series(holdings)
            realized_weights_df.iloc[t] = pd.Series(realized_w)

        # Active evaluation slice
        active_idx = common_idx[start_idx:]
        active_nav = nav_series.loc[active_idx]
        daily_returns = active_nav.pct_change().fillna(0.0)

        # Build aligned daily risk-free series for statistics engine
        if isinstance(self.risk_free_rate_annual, pd.Series):
            rf_daily_active = self.risk_free_rate_annual.reindex(active_idx).fillna(0.0) / 252.0
        elif rf_series is not None:
            rf_daily_active = rf_series.reindex(active_idx).fillna(0.0) / 252.0
        else:
            rf_daily_active = float(self.risk_free_rate_annual) / 252.0

        # Compute summary metrics & statistical uncertainty
        total_ret = (active_nav.iloc[-1] / active_nav.iloc[0]) - 1.0 if len(active_nav) else 0.0
        n_years = len(active_nav) / 252.0 if len(active_nav) else 1.0
        cagr = (active_nav.iloc[-1] / active_nav.iloc[0]) ** (1.0 / max(1e-4, n_years)) - 1.0 if len(active_nav) and active_nav.iloc[0] > 0 else 0.0

        stats_dict = calculate_sharpe_statistics(
            daily_returns,
            rf_daily=rf_daily_active,
            periods_per_year=252,
        )

        # Drawdown calculation
        peak = active_nav.cummax()
        dd = (active_nav - peak) / peak
        max_dd = float(dd.min()) if len(dd) else 0.0

        downside = daily_returns[daily_returns < 0]
        sd_down = float(np.std(downside, ddof=1) * np.sqrt(252.0)) if len(downside) > 1 else 1e-8
        sortino = float(cagr / sd_down) if sd_down > 0 else 0.0
        calmar = float(abs(cagr / max_dd)) if max_dd < 0 else 0.0

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
            "annualized_volatility": stats_dict["annualized_volatility"],
            "sharpe": stats_dict["gross_sharpe"],
            "gross_sharpe": stats_dict["gross_sharpe"],
            "excess_sharpe": stats_dict["excess_sharpe"],
            "sharpe_se": stats_dict["sharpe_se"],
            "sharpe_t_stat": stats_dict["sharpe_t_stat"],
            "sharpe_ci_lower_95": stats_dict["sharpe_ci_lower_95"],
            "sharpe_ci_upper_95": stats_dict["sharpe_ci_upper_95"],
            "max_drawdown": max_dd,
            "sortino": sortino,
            "calmar": calmar,
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
