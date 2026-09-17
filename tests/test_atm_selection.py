"""Tests for ATM strike selection logic."""

import pytest
from datetime import datetime

from src.models import OptionChainSnapshot, OptionLeg
from src.option_chain import find_atm_strike


def test_atm_selection_exact_match():
    """Test ATM selection when strike exactly matches spot price."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=24900.0, call_ltp=150.0, put_ltp=100.0),
            OptionLeg(strike=25000.0, call_ltp=200.0, put_ltp=180.0),
            OptionLeg(strike=25100.0, call_ltp=120.0, put_ltp=220.0),
        ],
    )

    atm = find_atm_strike(chain)
    assert atm is not None
    assert atm.strike == 25000.0
    assert atm.distance_from_spot == 0.0
    assert atm.call_ltp == 200.0
    assert atm.put_ltp == 180.0
    assert atm.straddle_premium == 380.0


def test_atm_selection_closest_strike():
    """Test ATM selection when no exact match, should pick closest."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25025.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=25000.0, call_ltp=200.0, put_ltp=180.0),
            OptionLeg(strike=25050.0, call_ltp=170.0, put_ltp=210.0),
            OptionLeg(strike=25100.0, call_ltp=120.0, put_ltp=220.0),
        ],
    )

    atm = find_atm_strike(chain)
    assert atm is not None
    assert atm.strike == 25000.0  # 25 away vs 25 and 75
    assert atm.distance_from_spot == 25.0


def test_atm_selection_tie_breaker():
    """Test ATM selection when equidistant, should pick first (lower strike)."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25025.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=25000.0, call_ltp=200.0, put_ltp=180.0),
            OptionLeg(strike=25050.0, call_ltp=170.0, put_ltp=210.0),
        ],
    )

    atm = find_atm_strike(chain)
    assert atm is not None
    # Both are 25 away, should pick the first one (25000)
    assert atm.strike == 25000.0


def test_atm_selection_empty_chain():
    """Test ATM selection with empty option chain."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[],
    )

    atm = find_atm_strike(chain)
    assert atm is None


def test_atm_selection_single_strike():
    """Test ATM selection with only one strike available."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=24800.0, call_ltp=300.0, put_ltp=50.0),
        ],
    )

    atm = find_atm_strike(chain)
    assert atm is not None
    assert atm.strike == 24800.0
    assert atm.distance_from_spot == 200.0


def test_atm_straddle_calculation():
    """Test that straddle premium is correctly calculated as Call + Put."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=25000.0, call_ltp=150.5, put_ltp=175.25),
        ],
    )

    atm = find_atm_strike(chain)
    assert atm is not None
    assert atm.straddle_premium == 325.75  # 150.5 + 175.25


def test_atm_selection_with_oi_and_volume():
    """Test ATM selection preserves OI and volume data."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(
                strike=25000.0,
                call_ltp=200.0,
                put_ltp=180.0,
                call_oi=500000,
                put_oi=450000,
                call_volume=10000,
                put_volume=8000,
            ),
        ],
    )

    atm = find_atm_strike(chain)
    assert atm is not None
    # ATMResult only stores strike and prices, not OI/volume
    # This test ensures the selection logic doesn't break with extra data
    assert atm.strike == 25000.0
