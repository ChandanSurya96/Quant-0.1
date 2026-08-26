"""Unit tests for CAND-012 Survivorship & Borrow Robustness Research Engine."""

from quant.pairs.backtest import YalePairsBacktester
from scripts.run_cand012_research import (
    SECTOR_MAP,
    generate_sp500_robust_panel,
)


def test_sp500_robust_panel_and_sector_coverage():
    df_p, df_v = generate_sp500_robust_panel(n_bars=300, random_seed=42)
    assert len(df_p) == 300
    assert df_p.shape[1] == len(SECTOR_MAP)
    assert set(df_p.columns) == set(SECTOR_MAP.keys())
    assert not df_p.isna().any().any()


def test_cand012_sector_matched_backtest():
    df_p, df_v = generate_sp500_robust_panel(n_bars=450, random_seed=42)
    bt = YalePairsBacktester(
        formation_bars=252,
        trading_bars=126,
        step_bars=21,
        top_m=10,
        entry_threshold_sigma=2.0,
        wait_one_day=True,
        sector_map=SECTOR_MAP,
        cost_bps=10.0,
    )
    res = bt.run(df_p, df_v)
    assert "daily_returns" in res
    assert "sharpe_net" in res
    assert len(res["daily_returns"]) > 0
