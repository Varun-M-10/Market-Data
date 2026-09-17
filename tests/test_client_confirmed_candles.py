"""Verification suite for client-confirmed candle requirements."""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.candles.aggregator import CandleAggregator, _floor_to_interval
from src.models import PriceTick


def test_controlled_price_sequence_100_102_98_105_103():
    """
    Test exact controlled sequence: 100, 102, 98, 105, 103
    Expected candle: Open = 100, High = 105, Low = 98, Close = 103
    """
    agg = CandleAggregator(
        symbol="NIFTY",
        intervals_minutes=[1, 5, 15],
        timezone="Asia/Kolkata",
        session_start="09:15",
    )
    base_time = datetime(2026, 8, 26, 9, 15, 0, tzinfo=ZoneInfo("Asia/Kolkata"))

    price_sequence = [100.0, 102.0, 98.0, 105.0, 103.0]

    for i, price in enumerate(price_sequence):
        tick = PriceTick(
            symbol="NIFTY",
            price=price,
            timestamp=base_time + timedelta(seconds=i * 10),
        )
        agg.process_tick(tick)

    # Verify for all three timeframes: 1m, 5m, 15m
    for interval in [1, 5, 15]:
        assert interval in agg.active_candles
        candle = agg.active_candles[interval]
        assert candle.open == 100.0, f"[{interval}m] Open must be first valid price 100"
        assert candle.high == 105.0, f"[{interval}m] High must be highest price 105"
        assert candle.low == 98.0, f"[{interval}m] Low must be lowest price 98"
        assert candle.close == 103.0, f"[{interval}m] Close must be latest price 103"
        assert candle.tick_count == 5


def test_timeframe_boundaries_1m_5m_15m():
    """
    Verify exact boundaries:
    1m: 09:15:00–09:15:59
    5m: 09:15:00–09:19:59, 09:20:00–09:24:59
    15m: 09:15:00–09:29:59, 09:30:00–09:44:59
    """
    tz = ZoneInfo("Asia/Kolkata")
    
    # 1m boundary tests
    dt_1m_in = datetime(2026, 8, 26, 9, 15, 59, tzinfo=tz)
    dt_1m_next = datetime(2026, 8, 26, 9, 16, 0, tzinfo=tz)
    assert _floor_to_interval(dt_1m_in, 1, timezone=tz, session_start="09:15") == datetime(2026, 8, 26, 9, 15, 0, tzinfo=tz)
    assert _floor_to_interval(dt_1m_next, 1, timezone=tz, session_start="09:15") == datetime(2026, 8, 26, 9, 16, 0, tzinfo=tz)

    # 5m boundary tests
    dt_5m_1 = datetime(2026, 8, 26, 9, 19, 59, tzinfo=tz)
    dt_5m_2 = datetime(2026, 8, 26, 9, 20, 0, tzinfo=tz)
    dt_5m_3 = datetime(2026, 8, 26, 9, 24, 59, tzinfo=tz)
    assert _floor_to_interval(dt_5m_1, 5, timezone=tz, session_start="09:15") == datetime(2026, 8, 26, 9, 15, 0, tzinfo=tz)
    assert _floor_to_interval(dt_5m_2, 5, timezone=tz, session_start="09:15") == datetime(2026, 8, 26, 9, 20, 0, tzinfo=tz)
    assert _floor_to_interval(dt_5m_3, 5, timezone=tz, session_start="09:15") == datetime(2026, 8, 26, 9, 20, 0, tzinfo=tz)

    # 15m boundary tests
    dt_15m_1 = datetime(2026, 8, 26, 9, 29, 59, tzinfo=tz)
    dt_15m_2 = datetime(2026, 8, 26, 9, 30, 0, tzinfo=tz)
    dt_15m_3 = datetime(2026, 8, 26, 9, 44, 59, tzinfo=tz)
    assert _floor_to_interval(dt_15m_1, 15, timezone=tz, session_start="09:15") == datetime(2026, 8, 26, 9, 15, 0, tzinfo=tz)
    assert _floor_to_interval(dt_15m_2, 15, timezone=tz, session_start="09:15") == datetime(2026, 8, 26, 9, 30, 0, tzinfo=tz)
    assert _floor_to_interval(dt_15m_3, 15, timezone=tz, session_start="09:15") == datetime(2026, 8, 26, 9, 30, 0, tzinfo=tz)


def test_automatic_rollover_all_three_timeframes():
    """
    Test automatic rollover for 1m, 5m, and 15m timeframes:
    1. Finalize current candle.
    2. Store/emit completed candle.
    3. Start next candle automatically.
    4. First valid tick in new interval becomes its Open.
    """
    agg = CandleAggregator(
        symbol="NIFTY",
        intervals_minutes=[1, 5, 15],
        timezone="Asia/Kolkata",
        session_start="09:15",
    )
    tz = ZoneInfo("Asia/Kolkata")

    # Sequence of ticks across 1m, 5m, 15m boundaries
    # Ticks in 09:15:00 - 09:15:59
    agg.process_tick(PriceTick(symbol="NIFTY", price=100.0, timestamp=datetime(2026, 8, 26, 9, 15, 10, tzinfo=tz)))
    agg.process_tick(PriceTick(symbol="NIFTY", price=105.0, timestamp=datetime(2026, 8, 26, 9, 15, 30, tzinfo=tz)))

    # Cross 1m boundary -> 09:16:00
    comp_1m = agg.process_tick(PriceTick(symbol="NIFTY", price=110.0, timestamp=datetime(2026, 8, 26, 9, 16, 5, tzinfo=tz)))
    assert len(comp_1m) == 1
    assert comp_1m[0].interval_minutes == 1
    assert comp_1m[0].is_complete is True
    assert comp_1m[0].open == 100.0
    assert comp_1m[0].high == 105.0
    assert comp_1m[0].close == 105.0  # Last tick in 09:15 bucket
    assert agg.active_candles[1].open == 110.0  # First tick in 09:16 bucket

    # Cross 5m boundary -> 09:20:00
    comp_5m = agg.process_tick(PriceTick(symbol="NIFTY", price=120.0, timestamp=datetime(2026, 8, 26, 9, 20, 2, tzinfo=tz)))
    # Should finalize previous 1m candle and 5m candle
    completed_intervals = [c.interval_minutes for c in comp_5m]
    assert 5 in completed_intervals
    c_5m = [c for c in comp_5m if c.interval_minutes == 5][0]
    assert c_5m.is_complete is True
    assert c_5m.open == 100.0
    assert c_5m.high == 110.0
    assert c_5m.close == 110.0
    assert agg.active_candles[5].open == 120.0  # First tick in 09:20 5m bucket

    # Cross 15m boundary -> 09:30:00
    comp_15m = agg.process_tick(PriceTick(symbol="NIFTY", price=130.0, timestamp=datetime(2026, 8, 26, 9, 30, 1, tzinfo=tz)))
    completed_intervals_15m = [c.interval_minutes for c in comp_15m]
    assert 15 in completed_intervals_15m
    c_15m = [c for c in comp_15m if c.interval_minutes == 15][0]
    assert c_15m.is_complete is True
    assert c_15m.open == 100.0
    assert c_15m.high == 120.0
    assert c_15m.close == 120.0
    assert agg.active_candles[15].open == 130.0  # First tick in 09:30 15m bucket


def test_configurable_timezone_utc_handling():
    """Verify explicit non-local timezone configuration (e.g., UTC input converted to Asia/Kolkata)."""
    agg = CandleAggregator(
        symbol="NIFTY",
        intervals_minutes=[5],
        timezone="Asia/Kolkata",
        session_start="09:15",
    )
    # 03:45 UTC is 09:15 IST
    utc_dt = datetime(2026, 8, 26, 3, 45, 10, tzinfo=ZoneInfo("UTC"))
    agg.process_tick(PriceTick(symbol="NIFTY", price=25000.0, timestamp=utc_dt))

    candle = agg.active_candles[5]
    expected_open_time = datetime(2026, 8, 26, 9, 15, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert candle.open_time == expected_open_time
