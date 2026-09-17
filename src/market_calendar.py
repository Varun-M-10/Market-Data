"""
NSE trading-calendar awareness: Monday-Friday, minus a maintained table of
official NSE trading holidays (data/nse_holidays.json).

This is deliberately a plain, committed JSON data file rather than a
database or a live network fetch: NSE holiday lists are published/revised
a handful of times a year, so "current" here means "update the data file
when NSE publishes or revises one" (a data change, not a code change) —
not an API call on every date-navigation click, which would make basic
calendar navigation depend on a third-party site being reachable from
wherever this app is deployed.

Used by MarketEngine.get_available_trading_dates() to keep the Date/
Session selector's Previous/Next navigation from ever landing on a
weekend or a known market holiday, on top of (not instead of) only ever
selecting dates that actually have persisted MOCK data — see engine.py.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

_HOLIDAYS_PATH = Path(__file__).resolve().parent.parent / "data" / "nse_holidays.json"

# Calendar-walk safety bound: a date this far from a known trading day is
# almost certainly a corrupt/empty holiday file, not a real gap — stop and
# fall back rather than looping indefinitely.
_MAX_SCAN_DAYS = 30


@lru_cache(maxsize=1)
def _load_holidays() -> dict[str, str]:
    """ISO date -> holiday name, loaded once from the committed data file.
    A missing or unparseable file degrades to "no known holidays" (weekday-
    only calendar) rather than crashing date navigation."""
    try:
        raw = json.loads(_HOLIDAYS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for key, entries in raw.items():
        if key.startswith("_") or not isinstance(entries, list):
            continue
        for entry in entries:
            try:
                out[entry["date"]] = entry["name"]
            except (KeyError, TypeError):
                continue
    return out


def holiday_name(d: date) -> str | None:
    """The NSE holiday name on `d`, or None if it isn't a known holiday."""
    return _load_holidays().get(d.isoformat())


def is_market_holiday(d: date) -> bool:
    return d.isoformat() in _load_holidays()


def is_trading_day(d: date) -> bool:
    """Monday-Friday and not a known NSE holiday."""
    return d.weekday() < 5 and not is_market_holiday(d)


def previous_trading_day(d: date) -> date:
    """Nearest earlier calendar date that is Mon-Fri and not a known
    holiday. Calendar-only: does not check for persisted MOCK data (see
    MarketEngine.get_available_trading_dates for that layer)."""
    cur = d
    for _ in range(_MAX_SCAN_DAYS):
        cur -= timedelta(days=1)
        if is_trading_day(cur):
            return cur
    return d - timedelta(days=1)


def next_trading_day(d: date) -> date:
    cur = d
    for _ in range(_MAX_SCAN_DAYS):
        cur += timedelta(days=1)
        if is_trading_day(cur):
            return cur
    return d + timedelta(days=1)
