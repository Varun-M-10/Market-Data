"""
Lightweight SQLite persistence for completed candles and option chain / ATM
snapshots.

This is a purely additive layer: nothing in the candle aggregator, ATM
resolver, or paper trading engine depends on it. It is safe to disable via
config (`persistence.enabled: false`) without touching any pipeline logic.
Uses Python's stdlib `sqlite3` — no new dependency.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from src.models import ATMResult, Candle, OptionChainSnapshot


class PersistenceStore:
    """Thread-safe SQLite-backed store for completed candles and option chain snapshots."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    interval_minutes INTEGER NOT NULL,
                    open_time TEXT NOT NULL,
                    close_time TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    tick_count INTEGER NOT NULL,
                    UNIQUE(symbol, interval_minutes, open_time)
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_candles_lookup "
                "ON candles(symbol, interval_minutes, open_time)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS option_chain_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    underlying TEXT NOT NULL,
                    underlying_ltp REAL,
                    expiry TEXT,
                    atm_strike REAL,
                    atm_call_ltp REAL,
                    atm_put_ltp REAL,
                    straddle_premium REAL,
                    timestamp TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chain_snapshots_lookup "
                "ON option_chain_snapshots(underlying, timestamp)"
            )
            self._conn.commit()

    # -- writes ---------------------------------------------------------

    def save_candle(self, candle: Candle) -> None:
        """Upsert a completed candle keyed on (symbol, interval, open_time)."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO candles
                    (symbol, interval_minutes, open_time, close_time, open, high, low, close, tick_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, interval_minutes, open_time) DO UPDATE SET
                    close_time=excluded.close_time,
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    tick_count=excluded.tick_count
                """,
                (
                    candle.symbol,
                    candle.interval_minutes,
                    candle.open_time.isoformat(),
                    candle.close_time.isoformat(),
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.tick_count,
                ),
            )
            self._conn.commit()

    def save_option_chain_snapshot(
        self, chain: OptionChainSnapshot, atm: ATMResult | None
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO option_chain_snapshots
                    (underlying, underlying_ltp, expiry, atm_strike, atm_call_ltp,
                     atm_put_ltp, straddle_premium, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chain.underlying,
                    chain.underlying_ltp,
                    chain.expiry,
                    atm.strike if atm else None,
                    atm.call_ltp if atm else None,
                    atm.put_ltp if atm else None,
                    atm.straddle_premium if atm else None,
                    chain.timestamp.isoformat(),
                ),
            )
            self._conn.commit()

    # -- reads ------------------------------------------------------------

    def get_recent_candles(
        self, symbol: str, interval_minutes: int, limit: int = 100
    ) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT symbol, interval_minutes, open_time, close_time, open, high, low, close, tick_count
                FROM candles
                WHERE symbol = ? AND interval_minutes = ?
                ORDER BY open_time DESC
                LIMIT ?
                """,
                (symbol, interval_minutes, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_recent_option_chain_snapshots(self, underlying: str, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT underlying, underlying_ltp, expiry, atm_strike, atm_call_ltp,
                       atm_put_ltp, straddle_premium, timestamp
                FROM option_chain_snapshots
                WHERE underlying = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (underlying, limit),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
