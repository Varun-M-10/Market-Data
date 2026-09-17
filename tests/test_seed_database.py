"""
Tests for `ensure_seeded()` (src/persistence.py) — the deploy-time bootstrap
that restores a committed seed copy of historical MOCK data into the runtime
SQLite path, but ONLY when that path doesn't already exist.

Why this exists: on a host with an ephemeral container filesystem (e.g.
Railway without a mounted Volume), the runtime DB starts out missing on
every deploy/restart, so previously-recorded trading sessions localhost has
never reach the deployed app. This is a pure file-copy bootstrap — no new
database, no schema change, no change to any read/write API.
"""

from datetime import datetime

import pytest

from src.engine import MarketEngine
from src.models import Candle
from src.persistence import PersistenceStore, ensure_seeded
from src.timeutil import IST


def make_candle(open_time, close_time=None):
    return Candle(
        symbol="NIFTY", interval_minutes=1, open_time=open_time, close_time=close_time or open_time,
        open=100.0, high=110.0, low=95.0, close=105.0, tick_count=5, is_complete=True,
    )


@pytest.fixture
def seed_db(tmp_path):
    """A populated 'committed seed' DB, standing in for data/seed/market_data.seed.db."""
    path = tmp_path / "seed.db"
    store = PersistenceStore(path)
    store.save_candle(make_candle(datetime(2026, 9, 10, 10, 0, 0, tzinfo=IST)))
    store.close()
    return path


def test_seeds_runtime_db_when_missing(tmp_path, seed_db):
    runtime_path = tmp_path / "runtime" / "market_data.db"
    assert not runtime_path.exists()

    ensure_seeded(runtime_path, seed_db)

    assert runtime_path.exists()
    store = PersistenceStore(runtime_path)
    try:
        assert store.list_trading_dates() == ["2026-09-10"]
    finally:
        store.close()


def test_never_overwrites_an_already_existing_runtime_db(tmp_path, seed_db):
    """The core safety guarantee: localhost (and a Railway container that's
    already been running) must never have its own accumulated data clobbered
    by the seed."""
    runtime_path = tmp_path / "market_data.db"
    store = PersistenceStore(runtime_path)
    store.save_candle(make_candle(datetime(2026, 9, 16, 10, 0, 0, tzinfo=IST)))
    store.close()

    ensure_seeded(runtime_path, seed_db)

    store = PersistenceStore(runtime_path)
    try:
        # Only the runtime DB's own date — the seed's 2026-09-10 never got copied in.
        assert store.list_trading_dates() == ["2026-09-16"]
    finally:
        store.close()


def test_noop_when_seed_path_is_none_or_blank(tmp_path):
    runtime_path = tmp_path / "market_data.db"
    ensure_seeded(runtime_path, None)
    assert not runtime_path.exists()
    ensure_seeded(runtime_path, "")
    assert not runtime_path.exists()


def test_noop_when_seed_file_does_not_exist(tmp_path):
    runtime_path = tmp_path / "market_data.db"
    missing_seed = tmp_path / "does" / "not" / "exist.db"
    ensure_seeded(runtime_path, missing_seed)
    assert not runtime_path.exists()


def test_creates_parent_directory_of_runtime_path(tmp_path, seed_db):
    runtime_path = tmp_path / "nested" / "dir" / "market_data.db"
    ensure_seeded(runtime_path, seed_db)
    assert runtime_path.exists()


def test_engine_bootstraps_from_seed_on_a_fresh_ephemeral_like_environment(tmp_path, seed_db):
    """End-to-end: MarketEngine, configured exactly like a fresh Railway
    container (persistence enabled, runtime db_path doesn't exist yet, a
    seed_db_path is configured), must have the seeded historical date
    available through the same get_historical_session()/
    get_available_trading_dates() API used everywhere else — no special
    "seeded" code path in the read side at all."""
    runtime_path = tmp_path / "runtime" / "market_data.db"
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 5,
        "candle_intervals": [1, 5, 15],
        "price_calculator": "mock",
        "persistence": {
            "enabled": True,
            "db_path": str(runtime_path),
            "seed_db_path": str(seed_db),
        },
    }
    engine = MarketEngine(cfg)
    try:
        dates = engine.get_available_trading_dates()
        assert "2026-09-10" in dates["dates"]
        session = engine.get_historical_session("2026-09-10")
        assert session["has_data"] is True
    finally:
        engine.close()


def test_engine_does_not_seed_when_seed_db_path_unset(tmp_path):
    """No seed_db_path configured (e.g. explicitly disabled) -> behaves
    exactly as before this feature existed: a fresh empty DB, no error."""
    runtime_path = tmp_path / "runtime" / "market_data.db"
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 5,
        "candle_intervals": [1, 5, 15],
        "price_calculator": "mock",
        "persistence": {"enabled": True, "db_path": str(runtime_path)},
    }
    engine = MarketEngine(cfg)
    try:
        assert engine.get_available_trading_dates()["dates"] == []
    finally:
        engine.close()
