"""Tests for Delta-based ATM strike selection (Call/Put Delta closest to threshold)."""

from datetime import datetime

import pytest

from src.models import OptionChainSnapshot, OptionLeg
from src.option_chain import find_atm_strike, find_atm_strike_delta


def make_chain(underlying_ltp, legs):
    return OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=underlying_ltp,
        expiry="28-Aug-2026",
        timestamp=datetime(2026, 8, 23, 10, 0, 0),
        strikes=legs,
    )


def test_delta_atm_picks_strike_with_call_delta_closest_to_threshold():
    chain = make_chain(
        25025.0,
        [
            OptionLeg(strike=24900.0, call_ltp=250.0, put_ltp=60.0, call_delta=0.72, put_delta=-0.28),
            OptionLeg(strike=25000.0, call_ltp=180.0, put_ltp=130.0, call_delta=0.53, put_delta=-0.47),
            OptionLeg(strike=25100.0, call_ltp=110.0, put_ltp=210.0, call_delta=0.31, put_delta=-0.69),
        ],
    )

    atm = find_atm_strike_delta(chain, delta_threshold=0.5)
    assert atm is not None
    assert atm.strike == 25000.0  # call_delta=0.53 is closest to 0.50
    assert atm.method == "delta"
    assert atm.call_delta == 0.53
    assert atm.put_delta == -0.47
    assert atm.delta_threshold == 0.5


def test_delta_atm_differs_from_price_based_and_reports_comparison():
    """Construct a case where nearest-to-spot != nearest-to-0.50-delta strike."""
    chain = make_chain(
        25000.0,  # price-based ATM would be exactly 25000
        [
            OptionLeg(strike=25000.0, call_ltp=180.0, put_ltp=130.0, call_delta=0.62, put_delta=-0.38),
            OptionLeg(strike=25050.0, call_ltp=150.0, put_ltp=160.0, call_delta=0.49, put_delta=-0.51),
        ],
    )

    delta_atm = find_atm_strike_delta(chain, delta_threshold=0.5)
    price_atm = find_atm_strike(chain)

    assert price_atm.strike == 25000.0
    assert delta_atm.strike == 25050.0  # call_delta=0.49 beats 0.62
    assert delta_atm.strike != price_atm.strike
    # The Delta result carries the price-based strike for on-screen comparison.
    assert delta_atm.price_based_strike == 25000.0


def test_delta_atm_uses_put_delta_when_it_is_closer():
    """A leg can win purely on Put Delta proximity even with a poor Call Delta."""
    chain = make_chain(
        25000.0,
        [
            # call_delta is 0.30 off, but |put_delta| is only 0.05 off -> best score 0.05
            OptionLeg(strike=25000.0, call_ltp=180.0, put_ltp=130.0, call_delta=0.80, put_delta=-0.55),
            # call_delta is 0.30 off, |put_delta| is 0.40 off -> best score 0.30 (loses)
            OptionLeg(strike=25050.0, call_ltp=150.0, put_ltp=160.0, call_delta=0.20, put_delta=-0.90),
        ],
    )
    atm = find_atm_strike_delta(chain, delta_threshold=0.5)
    assert atm.strike == 25000.0
    assert atm.put_delta == -0.55


def test_delta_threshold_is_configurable():
    chain = make_chain(
        25000.0,
        [
            OptionLeg(strike=24950.0, call_ltp=200.0, put_ltp=110.0, call_delta=0.65, put_delta=-0.35),
            OptionLeg(strike=25000.0, call_ltp=180.0, put_ltp=130.0, call_delta=0.50, put_delta=-0.50),
        ],
    )

    # With threshold 0.50, the exact-0.50 leg wins.
    atm_default = find_atm_strike_delta(chain, delta_threshold=0.5)
    assert atm_default.strike == 25000.0

    # With threshold 0.65, the other leg wins instead — proves it's configurable.
    atm_custom = find_atm_strike_delta(chain, delta_threshold=0.65)
    assert atm_custom.strike == 24950.0
    assert atm_custom.delta_threshold == 0.65


def test_delta_atm_falls_back_to_none_when_chain_has_no_greeks():
    """A chain with no delta data anywhere can't be scored -> caller should fall back to price-based."""
    chain = make_chain(
        25000.0,
        [OptionLeg(strike=25000.0, call_ltp=180.0, put_ltp=130.0)],  # no call_delta/put_delta
    )
    assert find_atm_strike_delta(chain) is None
    assert find_atm_strike(chain) is not None  # price-based still works as the fallback


def test_delta_atm_skips_legs_missing_greeks_when_others_have_them():
    chain = make_chain(
        25000.0,
        [
            OptionLeg(strike=24950.0, call_ltp=200.0, put_ltp=110.0),  # no Greeks -> not a candidate
            OptionLeg(strike=25050.0, call_ltp=150.0, put_ltp=160.0, call_delta=0.50, put_delta=-0.50),
        ],
    )
    atm = find_atm_strike_delta(chain)
    assert atm.strike == 25050.0  # the only leg with Greeks


def test_delta_atm_empty_and_none_chain():
    assert find_atm_strike_delta(None) is None
    assert find_atm_strike_delta(make_chain(25000.0, [])) is None


def test_straddle_and_call_put_from_delta_selected_strike():
    """Combined value (Call+Put) must come from the Delta-selected strike, not price-based."""
    chain = make_chain(
        25000.0,
        [
            OptionLeg(strike=25000.0, call_ltp=180.0, put_ltp=130.0, call_delta=0.70, put_delta=-0.30),
            OptionLeg(strike=25050.0, call_ltp=150.0, put_ltp=160.0, call_delta=0.50, put_delta=-0.50),
        ],
    )
    atm = find_atm_strike_delta(chain)
    assert atm.strike == 25050.0
    assert atm.call_ltp == 150.0
    assert atm.put_ltp == 160.0
    assert atm.straddle_premium == 310.0
