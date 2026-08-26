"""Unit tests verifying SystematicMacroStrategy targets pass RiskEngine with production defaults."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from quant.core.interfaces import PortfolioState
from quant.risk.config import RiskConfig
from quant.risk.engine import RiskEngine
from quant.strategies.macro import SystematicMacroStrategy


def test_systematic_macro_strategy_passes_production_default_risk_engine():
    """Verifies that gross 1.0 SystematicMacroStrategy passes production RiskConfig with 0 violations."""
    strat = SystematicMacroStrategy(mom_window=20, val_window=40, vol_window=20, min_train=50)
    dates = pd.date_range("2020-01-01", periods=100, freq="B")
    tickers = ["SPY", "TLT", "IEF", "FXE", "UUP", "EWJ", "EFA", "EEM"]

    # Prices with dispersion
    prices_dict = {t: pd.Series(100.0 + i * np.sin(np.linspace(0, 5, 100)), index=dates) for i, t in enumerate(tickers)}
    df_prices = pd.DataFrame(prices_dict)

    target_portfolio = strat.generate_target_portfolio(df_prices)
    assert len(target_portfolio.target_weights) > 0

    # Test against RiskEngine with STRICT PRODUCTION DEFAULTS
    engine = RiskEngine(config=RiskConfig())
    portfolio_state = PortfolioState(
        timestamp=datetime.now(timezone.utc),
        nav=100_000.0,
        cash=100_000.0,
        holdings={},
        realized_weights={},
    )
    decision = engine.evaluate(target_portfolio, portfolio_state)

    assert decision.approved is True
    assert len(decision.violations) == 0
    assert decision.metadata["was_scaled"] is False
    assert decision.metrics["gross_exposure"] == pytest.approx(1.0, abs=1e-4)
    assert decision.metrics["max_position_weight"] <= 0.25 + 1e-6
