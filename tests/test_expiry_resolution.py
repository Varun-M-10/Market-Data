"""
Expiry resolution — MOCK/Replay expiry must never be a stale hard-coded
date, must be configurable, and must be the same value everywhere it's
surfaced (Option Chain / Selected Contract / Paper Trading / Straddle Chart
all read the one `option_chain.expiry` field off a single snapshot).
"""

from __future__ import annotations

from datetime import date

from src.data_sources.mock import MockDataSource
from src.data_sources.replay import ReplayDataSource
from src.engine import build_data_source
from src.option_chain.expiry import resolve_mock_expiry


def test_configured_expiry_is_returned_verbatim():
    assert resolve_mock_expiry("30-Oct-2026") == "30-Oct-2026"


def test_none_configured_expiry_computes_next_thursday():
    # 2026-09-05 is a Saturday; the next Thursday is 2026-09-10.
    assert resolve_mock_expiry(None, today=date(2026, 9, 5)) == "10-Sep-2026"


def test_configured_expiry_takes_priority_over_auto_compute():
    # Even if "today" would auto-compute to something else, an explicit pin wins.
    assert resolve_mock_expiry("01-Jan-2027", today=date(2026, 9, 5)) == "01-Jan-2027"


def test_on_expiry_day_itself_returns_today():
    # 2026-09-10 is itself a Thursday.
    assert resolve_mock_expiry(None, today=date(2026, 9, 10)) == "10-Sep-2026"


def test_empty_string_configured_expiry_falls_back_to_auto_compute():
    # "" is falsy — same as unset, not a literal (invalid) expiry value.
    assert resolve_mock_expiry("", today=date(2026, 9, 5)) == "10-Sep-2026"


def test_mock_data_source_never_reports_the_old_hardcoded_date():
    source = MockDataSource(underlying="NIFTY", poll_interval=0.1)
    chain = source.fetch_option_chain()
    expiry = chain["records"]["expiryDates"][0]
    assert expiry != "28-Aug-2026"
    assert expiry  # non-empty


def test_mock_data_source_honors_a_configured_expiry():
    source = MockDataSource(underlying="NIFTY", poll_interval=0.1, expiry="15-Jan-2027")
    chain = source.fetch_option_chain()
    assert chain["records"]["expiryDates"] == ["15-Jan-2027"]


def test_mock_data_source_expiry_is_stable_across_calls():
    """Every consumer (Option Chain, Paper Trading, Straddle Chart) reads the
    same live chain, but this guards the underlying invariant directly: one
    MockDataSource instance always reports the same expiry, tick to tick."""
    source = MockDataSource(underlying="NIFTY", poll_interval=0.1)
    first = source.fetch_option_chain()["records"]["expiryDates"][0]
    second = source.fetch_option_chain()["records"]["expiryDates"][0]
    assert first == second


def test_replay_data_source_never_reports_the_old_hardcoded_date():
    source = ReplayDataSource(underlying="NIFTY", poll_interval=0.1)
    chain = source.fetch_option_chain()
    expiry = chain["records"]["expiryDates"][0]
    assert expiry != "28-Aug-2026"
    assert expiry


def test_replay_data_source_honors_a_configured_expiry():
    source = ReplayDataSource(underlying="NIFTY", poll_interval=0.1, expiry="15-Jan-2027")
    chain = source.fetch_option_chain()
    assert chain["records"]["expiryDates"] == ["15-Jan-2027"]


def test_build_data_source_wires_configured_expiry_through_to_mock():
    """config.yaml's `expiry` key (or the EXPIRY env var, via load_config)
    must reach MockDataSource — this is the whole chain from config file to
    the value the UI ends up displaying."""
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 0.1,
        "expiry": "22-Dec-2026",
    }
    source = build_data_source(cfg)
    assert isinstance(source, MockDataSource)
    assert source.expiry == "22-Dec-2026"


def test_build_data_source_auto_computes_when_expiry_not_configured():
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 0.1,
        "expiry": None,
    }
    source = build_data_source(cfg)
    assert isinstance(source, MockDataSource)
    assert source.expiry != "28-Aug-2026"
    assert source.expiry
