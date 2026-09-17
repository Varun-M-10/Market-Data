"""Tests for the Asia/Kolkata trading-date-scoped persistence added for the
historical Date/Session selector: candle/option-chain/paper-trade rows
grouped by IST trading date, strike-candle retrieval, and the old-schema
migration path."""

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.models import Candle, OptionChainSnapshot, OptionLeg, ATMResult
from src.paper_trading import PaperPosition
from src.persistence import PersistenceStore
from src.timeutil import IST

UTC = ZoneInfo("UTC")


def make_candle(open_time, close_time, symbol="NIFTY", o=100.0, h=110.0, l=95.0, c=105.0, ticks=5, interval=1):
    return Candle(
        symbol=symbol,
        interval_minutes=interval,
        open_time=open_time,
        close_time=close_time,
        open=o,
        high=h,
        low=l,
        close=c,
        tick_count=ticks,
        is_complete=True,
    )


@pytest.fixture
def store(tmp_path):
    s = PersistenceStore(tmp_path / "test.db")
    yield s
    s.close()


def test_save_candle_computes_ist_trading_date(store):
    open_time = datetime(2026, 9, 15, 10, 30, 0, tzinfo=IST)
    store.save_candle(make_candle(open_time, open_time))
    rows = store.get_candles_for_date("NIFTY", 1, "2026-09-15")
    assert len(rows) == 1


def test_trading_date_uses_ist_across_utc_midnight_boundary(store):
    # 23:00 UTC on the 15th is 04:30 IST on the 16th.
    open_time = datetime(2026, 9, 15, 23, 0, 0, tzinfo=UTC)
    store.save_candle(make_candle(open_time, open_time))
    assert store.get_candles_for_date("NIFTY", 1, "2026-09-16") != []
    assert store.get_candles_for_date("NIFTY", 1, "2026-09-15") == []


def test_get_candles_for_date_filters_by_date_and_orders_ascending(store):
    day1 = datetime(2026, 9, 15, 10, 30, 0, tzinfo=IST)
    day2 = datetime(2026, 9, 16, 10, 30, 0, tzinfo=IST)
    store.save_candle(make_candle(day1.replace(minute=31), day1.replace(minute=32), o=100.0))
    store.save_candle(make_candle(day1.replace(minute=30), day1.replace(minute=31), o=99.0))
    store.save_candle(make_candle(day2, day2, o=200.0))

    rows = store.get_candles_for_date("NIFTY", 1, "2026-09-15")
    assert [r["open"] for r in rows] == [99.0, 100.0]
    assert len(store.get_candles_for_date("NIFTY", 1, "2026-09-16")) == 1


def test_list_trading_dates_is_distinct_and_newest_first(store):
    for day in (15, 16, 17):
        ts = datetime(2026, 9, day, 10, 0, 0, tzinfo=IST)
        store.save_candle(make_candle(ts, ts))
    assert store.list_trading_dates() == ["2026-09-17", "2026-09-16", "2026-09-15"]


def test_no_data_for_a_date_returns_empty_not_error(store):
    assert store.get_candles_for_date("NIFTY", 1, "2026-01-01") == []
    assert store.get_option_chain_snapshots_for_date("NIFTY", "2026-01-01") == []
    assert store.get_paper_trades_for_date("2026-01-01") == []
    assert store.list_trading_dates() == []


def test_strike_candles_persisted_and_retrieved_by_date(store):
    """StrikeStraddleCandleEngine persists CE/PE/Straddle legs as
    "<strike>_ce" / "_pe" / "_straddle" symbols (see engine.py); the store
    must be able to find them back out by strike + date."""
    ts = datetime(2026, 9, 15, 10, 30, 0, tzinfo=IST)
    for leg in ("ce", "pe", "straddle"):
        store.save_candle(make_candle(ts, ts, symbol=f"24800.0_{leg}", interval=1))

    assert store.list_strikes_for_date("2026-09-15") == [24800.0]
    by_interval = store.get_strike_candles_for_date(24800.0, [1, 5], "2026-09-15")
    assert len(by_interval["1"]["ce"]) == 1
    assert len(by_interval["1"]["pe"]) == 1
    assert len(by_interval["1"]["straddle"]) == 1
    assert by_interval["5"]["ce"] == []  # no 5m candle was saved


def test_option_chain_snapshot_trading_date(store):
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime(2026, 9, 15, 10, 30, 0, tzinfo=IST),
        strikes=[OptionLeg(strike=25000.0, call_ltp=150.0, put_ltp=140.0)],
    )
    atm = ATMResult(
        strike=25000.0, call_ltp=150.0, put_ltp=140.0, straddle_premium=290.0,
        underlying_ltp=25000.0, distance_from_spot=0.0,
    )
    store.save_option_chain_snapshot(chain, atm)
    rows = store.get_option_chain_snapshots_for_date("NIFTY", "2026-09-15")
    assert len(rows) == 1
    assert rows[0]["atm_strike"] == 25000.0


def test_save_and_read_paper_trade_by_date(store):
    position = PaperPosition(
        id="abc123",
        option_type="CE",
        strike=25000.0,
        quantity=50,
        entry_price=100.0,
        entry_time=datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST),
        take_profit_percent=10.0,
        stop_loss_percent=5.0,
    )
    position.close(110.0, datetime(2026, 9, 15, 10, 5, 0, tzinfo=IST), "TAKE_PROFIT")

    store.save_paper_trade(position)
    rows = store.get_paper_trades_for_date("2026-09-15")
    assert len(rows) == 1
    assert rows[0]["id"] == "abc123"
    assert rows[0]["exit_reason"] == "TAKE_PROFIT"
    assert rows[0]["pnl"] == pytest.approx(500.0)


def test_save_paper_trade_is_idempotent_upsert(store):
    position = PaperPosition(
        id="dup1", option_type="PE", strike=25000.0, quantity=50, entry_price=100.0,
        entry_time=datetime(2026, 9, 15, 10, 0, 0, tzinfo=IST),
        take_profit_percent=10.0, stop_loss_percent=5.0,
    )
    position.close(90.0, datetime(2026, 9, 15, 10, 5, 0, tzinfo=IST), "STOP_LOSS")
    store.save_paper_trade(position)
    store.save_paper_trade(position)  # re-save (shouldn't happen normally, must not duplicate)
    assert len(store.get_paper_trades_for_date("2026-09-15")) == 1


def test_migration_backfills_trading_date_on_an_old_schema_db(tmp_path):
    """A DB created before trading_date columns existed must still work:
    the column gets added and every existing row backfilled."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE candles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            interval_minutes INTEGER NOT NULL,
            open_time TEXT NOT NULL,
            close_time TEXT NOT NULL,
            open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
            tick_count INTEGER NOT NULL,
            UNIQUE(symbol, interval_minutes, open_time)
        )
        """
    )
    old_open_time = datetime(2026, 9, 10, 10, 30, 0, tzinfo=IST).isoformat()
    conn.execute(
        "INSERT INTO candles (symbol, interval_minutes, open_time, close_time, open, high, low, close, tick_count) "
        "VALUES ('NIFTY', 1, ?, ?, 100, 110, 95, 105, 5)",
        (old_open_time, old_open_time),
    )
    conn.execute(
        """
        CREATE TABLE option_chain_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            underlying TEXT NOT NULL, underlying_ltp REAL, expiry TEXT,
            atm_strike REAL, atm_call_ltp REAL, atm_put_ltp REAL, straddle_premium REAL,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    store = PersistenceStore(path)
    try:
        rows = store.get_candles_for_date("NIFTY", 1, "2026-09-10")
        assert len(rows) == 1
        assert rows[0]["open"] == 100.0
        assert store.list_trading_dates() == ["2026-09-10"]
    finally:
        store.close()
