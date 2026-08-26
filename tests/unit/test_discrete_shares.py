"""Unit tests for discrete physical share sizing in quant.portfolio.sizer."""

import pytest
from quant.portfolio.sizer import target_weights_to_shares


def test_target_weights_to_shares_discrete_integer_shares():
    target_weights = {"SPY": 0.25, "TLT": -0.25, "IEF": 0.05}
    nav = 100_000.0
    prices = {"SPY": 450.32, "TLT": 95.75, "IEF": 92.10}

    shares = target_weights_to_shares(
        target_weights, nav, prices, discrete_shares=True, min_tradeable_notional=50.0
    )

    for sym, q in shares.items():
        assert isinstance(q, float)
        assert q.is_integer()  # Strictly integer share quantities

    assert shares["SPY"] == pytest.approx(55.0)  # floor(25000 / 450.32) = 55
    assert shares["TLT"] == pytest.approx(-261.0)  # ceil(-25000 / 95.75) = -261


def test_target_weights_sub_minimum_notional_rejected():
    target_weights = {"SPY": 0.0001}  # $10 notional on $100k NAV
    nav = 100_000.0
    prices = {"SPY": 500.0}

    shares = target_weights_to_shares(
        target_weights, nav, prices, discrete_shares=True, min_tradeable_notional=100.0
    )
    assert shares["SPY"] == 0.0
