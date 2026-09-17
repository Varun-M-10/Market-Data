"""Tests for candle OHLC calculation and timeframe boundaries."""

import pytest
from datetime import datetime, timedelta

from src.candles.aggregator import CandleAggregator, _floor_to_interval
from src.models import PriceTick


def test_floor_to_interval_1_minute():
    """Test flooring to 1-minute intervals."""
    dt = datetime(2026, 8, 23, 10, 30, 45)  # 10:30:45
    floored = _floor_to_interval(dt, 1)
    assert floored == datetime(2026, 8, 23, 10, 30, 0)


def test_floor_to_interval_5_minute():
    """Test flooring to 5-minute intervals."""
    dt = datetime(2026, 8, 23, 10, 32, 45)  # 10:32:45
    floored = _floor_to_interval(dt, 5)
    assert floored == datetime(2026, 8, 23, 10, 30, 0)


def test_floor_to_interval_15_minute():
    """Test flooring to 15-minute intervals."""
    dt = datetime(2026, 8, 23, 10, 47, 45)  # 10:47:45
    floored = _floor_to_interval(dt, 15)
    assert floored == datetime(2026, 8, 23, 10, 45, 0)


def test_floor_to_interval_exact_boundary():
    """Test flooring when already on interval boundary."""
    dt = datetime(2026, 8, 23, 10, 30, 0)  # Exactly on 5-minute boundary
    floored = _floor_to_interval(dt, 5)
    assert floored == datetime(2026, 8, 23, 10, 30, 0)


def test_candle_aggregator_initialization():
    """Test CandleAggregator initialization with valid intervals."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1, 5, 15])
    assert agg.symbol == "NIFTY"
    assert agg.intervals == [1, 5, 15]
    assert agg.active_candles == {}
    assert 1 in agg.completed_candles
    assert 5 in agg.completed_candles
    assert 15 in agg.completed_candles


def test_candle_aggregator_invalid_intervals():
    """Test CandleAggregator rejects invalid intervals."""
    with pytest.raises(ValueError):
        CandleAggregator(symbol="NIFTY", intervals_minutes=[])

    with pytest.raises(ValueError):
        CandleAggregator(symbol="NIFTY", intervals_minutes=[0])

    with pytest.raises(ValueError):
        CandleAggregator(symbol="NIFTY", intervals_minutes=[-5])


def test_candle_aggregator_duplicate_intervals():
    """Test CandleAggregator deduplicates intervals."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1, 5, 1, 15, 5])
    assert agg.intervals == [1, 5, 15]


def test_first_tick_creates_candle():
    """Test that first tick creates a new candle."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    tick = PriceTick(
        symbol="NIFTY", price=25000.0, timestamp=datetime(2026, 8, 23, 10, 30, 0)
    )

    completed = agg.process_tick(tick)

    assert len(completed) == 0
    assert 1 in agg.active_candles
    candle = agg.active_candles[1]
    assert candle.open == 25000.0
    assert candle.high == 25000.0
    assert candle.low == 25000.0
    assert candle.close == 25000.0
    assert candle.tick_count == 1


def test_candle_ohlc_updates():
    """Test that OHLC values update correctly with multiple ticks."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 23, 10, 30, 0)

    # First tick
    agg.process_tick(PriceTick(symbol="NIFTY", price=25000.0, timestamp=base_time))

    # Second tick - higher price
    agg.process_tick(
        PriceTick(symbol="NIFTY", price=25050.0, timestamp=base_time + timedelta(seconds=10))
    )

    # Third tick - lower price
    agg.process_tick(
        PriceTick(symbol="NIFTY", price=24980.0, timestamp=base_time + timedelta(seconds=20))
    )

    candle = agg.active_candles[1]
    assert candle.open == 25000.0
    assert candle.high == 25050.0
    assert candle.low == 24980.0
    assert candle.close == 24980.0
    assert candle.tick_count == 3


def test_candle_completion_on_interval_boundary():
    """Test that candle completes when crossing interval boundary."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 23, 10, 30, 0)

    # Tick in first minute
    agg.process_tick(PriceTick(symbol="NIFTY", price=25000.0, timestamp=base_time))

    # Tick in next minute
    next_min = base_time + timedelta(minutes=1)
    completed = agg.process_tick(
        PriceTick(symbol="NIFTY", price=25010.0, timestamp=next_min)
    )

    assert len(completed) == 1
    assert completed[0].is_complete == True
    assert completed[0].close == 25000.0  # Last price before boundary

    # New active candle for next interval
    assert 1 in agg.active_candles
    new_candle = agg.active_candles[1]
    assert new_candle.open == 25010.0
    assert new_candle.open_time.replace(tzinfo=None) == next_min.replace(second=0, microsecond=0)


def test_multiple_intervals_independent():
    """Test that multiple intervals work independently."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1, 5])
    base_time = datetime(2026, 8, 23, 10, 30, 0)

    # Process several ticks within the same minute
    for i in range(10):
        tick_time = base_time + timedelta(seconds=i * 5)  # 5 seconds apart, all within same minute
        agg.process_tick(
            PriceTick(symbol="NIFTY", price=25000.0 + i, timestamp=tick_time)
        )

    # Both intervals should have active candles
    assert 1 in agg.active_candles
    assert 5 in agg.active_candles

    # Both intervals should have same number of ticks since they're in the same time period
    assert agg.active_candles[1].tick_count == 10
    assert agg.active_candles[5].tick_count == 10


def test_candle_tick_count():
    """Test that tick count increments correctly."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 23, 10, 30, 0)

    for i in range(5):
        agg.process_tick(
            PriceTick(symbol="NIFTY", price=25000.0, timestamp=base_time + timedelta(seconds=i))
        )

    assert agg.active_candles[1].tick_count == 5


def test_candle_symbol_preserved():
    """Test that candle symbol is preserved from tick."""
    agg = CandleAggregator(symbol="BANKNIFTY", intervals_minutes=[1])
    tick = PriceTick(
        symbol="BANKNIFTY", price=45000.0, timestamp=datetime(2026, 8, 23, 10, 30, 0)
    )

    agg.process_tick(tick)
    assert agg.active_candles[1].symbol == "BANKNIFTY"


def test_candle_close_time_set():
    """Test that candle close_time is set correctly."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[5])
    base_time = datetime(2026, 8, 23, 10, 30, 0)

    agg.process_tick(PriceTick(symbol="NIFTY", price=25000.0, timestamp=base_time))
    candle = agg.active_candles[5]

    expected_close = base_time + timedelta(minutes=5)
    expected_close = expected_close.replace(second=0, microsecond=0)
    assert candle.close_time.replace(tzinfo=None) == expected_close


def test_completed_candles_storage():
    """Test that completed candles are stored correctly."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 23, 10, 30, 0)

    # Complete first candle
    agg.process_tick(PriceTick(symbol="NIFTY", price=25000.0, timestamp=base_time))
    agg.process_tick(
        PriceTick(symbol="NIFTY", price=25010.0, timestamp=base_time + timedelta(minutes=1))
    )

    assert len(agg.completed_candles[1]) == 1
    assert agg.completed_candles[1][0].is_complete == True


def test_snapshot_active():
    """Test that snapshot_active returns copy of active candles."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 23, 10, 30, 0)

    agg.process_tick(PriceTick(symbol="NIFTY", price=25000.0, timestamp=base_time))
    snapshot = agg.snapshot_active()

    assert 1 in snapshot
    # Modifying snapshot should not affect original
    snapshot[1] = None
    assert 1 in agg.active_candles
    assert agg.active_candles[1] is not None
