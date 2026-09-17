"""Tests for tick reliability: timestamp validation, duplicate/out-of-order
detection, and market-session classification."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.models import PriceTick
from src.tick_validation import get_market_session_status, validate_tick


def make_tick(ts, price=25000.0):
    return PriceTick(symbol="NIFTY", price=price, timestamp=ts)


# -- validate_tick --------------------------------------------------------


def test_first_tick_with_no_prior_is_valid():
    result = validate_tick(make_tick(datetime(2026, 8, 23, 10, 0, 0)), None)
    assert result.is_valid is True
    assert result.is_duplicate is False
    assert result.is_out_of_order is False


def test_tick_strictly_after_last_is_valid():
    last = datetime(2026, 8, 23, 10, 0, 0)
    result = validate_tick(make_tick(datetime(2026, 8, 23, 10, 0, 1)), last)
    assert result.is_valid is True


def test_missing_timestamp_is_rejected():
    result = validate_tick(make_tick(None), None)
    assert result.is_valid is False
    assert result.reason == "missing_timestamp"


def test_none_tick_is_rejected():
    result = validate_tick(None, None)
    assert result.is_valid is False


def test_non_positive_price_is_rejected():
    ts = datetime(2026, 8, 23, 10, 0, 0)
    assert validate_tick(make_tick(ts, price=0.0), None).is_valid is False
    assert validate_tick(make_tick(ts, price=-5.0), None).is_valid is False
    assert validate_tick(make_tick(ts, price=None), None).is_valid is False


def test_exact_duplicate_timestamp_is_rejected_as_duplicate():
    ts = datetime(2026, 8, 23, 10, 0, 0)
    result = validate_tick(make_tick(ts), ts)
    assert result.is_valid is False
    assert result.is_duplicate is True
    assert result.is_out_of_order is False
    assert result.reason == "duplicate_timestamp"


def test_earlier_timestamp_is_rejected_as_out_of_order():
    last = datetime(2026, 8, 23, 10, 0, 5)
    earlier = datetime(2026, 8, 23, 10, 0, 1)
    result = validate_tick(make_tick(earlier), last)
    assert result.is_valid is False
    assert result.is_out_of_order is True
    assert result.is_duplicate is False
    assert result.reason == "out_of_order_timestamp"


def test_sequence_of_ticks_with_a_duplicate_and_an_out_of_order_tick():
    """Simulates a realistic tick stream and confirms only the bad ones are flagged."""
    from datetime import timedelta

    t0 = datetime(2026, 8, 23, 10, 0, 0)
    stream = [
        t0,
        t0 + timedelta(seconds=1),
        t0 + timedelta(seconds=1),  # duplicate of previous
        t0,  # out of order (older than last accepted)
        t0 + timedelta(seconds=2),  # valid again
    ]

    last_accepted = None
    outcomes = []
    for ts in stream:
        result = validate_tick(make_tick(ts), last_accepted)
        outcomes.append(result)
        if result.is_valid:
            last_accepted = ts

    assert [o.is_valid for o in outcomes] == [True, True, False, False, True]
    assert outcomes[2].is_duplicate is True
    assert outcomes[3].is_out_of_order is True
    assert last_accepted == t0 + timedelta(seconds=2)


# -- get_market_session_status --------------------------------------------


def test_session_open_during_market_hours():
    ts = datetime(2026, 8, 24, 11, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))  # Monday
    assert get_market_session_status(ts, "09:15", "15:30", "Asia/Kolkata") == "OPEN"


def test_session_pre_open_before_start():
    ts = datetime(2026, 8, 24, 8, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert get_market_session_status(ts, "09:15", "15:30", "Asia/Kolkata") == "PRE_OPEN"


def test_session_closed_after_end():
    ts = datetime(2026, 8, 24, 16, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert get_market_session_status(ts, "09:15", "15:30", "Asia/Kolkata") == "CLOSED"


def test_session_weekend_saturday_and_sunday():
    saturday = datetime(2026, 8, 22, 11, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    sunday = datetime(2026, 8, 23, 11, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert get_market_session_status(saturday) == "WEEKEND"
    assert get_market_session_status(sunday) == "WEEKEND"


def test_session_boundaries_are_inclusive():
    start = datetime(2026, 8, 24, 9, 15, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    end = datetime(2026, 8, 24, 15, 30, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert get_market_session_status(start, "09:15", "15:30") == "OPEN"
    assert get_market_session_status(end, "09:15", "15:30") == "OPEN"


def test_session_handles_naive_datetime():
    """A naive timestamp is treated as already being in the configured timezone."""
    ts = datetime(2026, 8, 24, 11, 0, 0)
    assert get_market_session_status(ts, "09:15", "15:30", "Asia/Kolkata") == "OPEN"
