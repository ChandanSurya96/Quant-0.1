"""Unit tests for CAND-008 S&P 500 Single-Stock Pairs Trading Engine."""

from quant.pairs.backtest import YalePairsBacktester
from scripts.run_cand008_research import generate_sp500_equity_dataset


def test_generate_sp500_equity_dataset_structure():
    df_prices, df_volumes = generate_sp500_equity_dataset(n_bars=300, random_seed=42)
    assert len(df_prices) == 300
    assert len(df_volumes) == 300
    assert df_prices.shape[1] == 100
    assert not df_prices.isna().any().any()
    assert (df_prices > 0).all().all()


def test_cand008_backtester_execution_deterministic():
    df_prices, df_volumes = generate_sp500_equity_dataset(n_bars=450, random_seed=42)
    bt = YalePairsBacktester(
        formation_bars=252,
        trading_bars=126,
        step_bars=21,
        top_m=10,
        entry_threshold_sigma=2.0,
        wait_one_day=True,
        cost_bps=10.0,
    )
    res = bt.run(df_prices, df_volumes, initial_capital=100_000.0)
    assert "sharpe_net" in res
    assert "cagr_net" in res
    assert "daily_returns" in res
    assert len(res["daily_returns"]) > 0
    assert not res["daily_returns"].isna().any()
