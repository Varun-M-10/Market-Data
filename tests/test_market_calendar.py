"""
Tests for src/market_calendar.py — the NSE Mon-Fri + holiday-table
calendar used by the Date/Session selector's Previous/Next navigation
(see MarketEngine.get_available_trading_dates() / get_historical_session()
in src/engine.py).
"""

from datetime import date

from src.market_calendar import (
    holiday_name,
    is_market_holiday,
    is_trading_day,
    next_trading_day,
    previous_trading_day,
)


def test_weekday_without_holiday_is_a_trading_day():
    # Thursday, 2026-09-17 — not in data/nse_holidays.json.
    assert is_trading_day(date(2026, 9, 17)) is True


def test_weekend_is_never_a_trading_day():
    assert is_trading_day(date(2026, 9, 12)) is False  # Saturday
    assert is_trading_day(date(2026, 9, 13)) is False  # Sunday


def test_known_nse_holiday_on_a_weekday_is_not_a_trading_day():
    # 2026-09-14 (Monday) — Ganesh Chaturthi, per data/nse_holidays.json.
    holiday = date(2026, 9, 14)
    assert is_market_holiday(holiday) is True
    assert holiday_name(holiday) == "Ganesh Chaturthi"
    assert is_trading_day(holiday) is False


def test_previous_trading_day_skips_weekend():
    # Monday 2026-09-14 is itself a holiday too, so the previous trading
    # day from the Tuesday after it must skip both the holiday Monday and
    # the weekend before it, landing on Friday 2026-09-11.
    assert previous_trading_day(date(2026, 9, 15)) == date(2026, 9, 11)


def test_next_trading_day_skips_weekend_and_holiday():
    assert next_trading_day(date(2026, 9, 11)) == date(2026, 9, 15)


def test_previous_and_next_are_inverse_across_a_plain_weekend():
    friday = date(2026, 9, 4)
    monday = next_trading_day(friday)
    assert monday == date(2026, 9, 7)
    assert previous_trading_day(monday) == friday
