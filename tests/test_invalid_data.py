"""Tests for handling invalid and missing data."""

import pytest
from datetime import datetime, timedelta

from src.candles.aggregator import CandleAggregator
from src.models import OptionChainSnapshot, OptionLeg, PriceTick
from src.option_chain import find_atm_strike, parse_option_chain


def test_missing_option_chain_data():
    """Test handling of missing fields in option chain data."""
    raw = {
        "records": {
            "underlyingValue": 25000.0,
            "expiryDates": ["28-Aug-2026"],
            "timestamp": "23-Aug-2026 10:30:00",
            "data": [
                {
                    "strikePrice": 25000.0,
                    "CE": {"lastPrice": 200.0},
                    "PE": {"lastPrice": 180.0},
                }
            ],
        }
    }

    chain = parse_option_chain(raw, "NIFTY")
    assert chain.underlying_ltp == 25000.0
    assert len(chain.strikes) == 1
    assert chain.strikes[0].call_oi is None  # Missing OI
    assert chain.strikes[0].put_oi is None


def test_empty_option_chain_records():
    """Test handling of empty records in option chain."""
    raw = {"records": {"underlyingValue": 25000.0, "expiryDates": [], "data": []}}

    chain = parse_option_chain(raw, "NIFTY")
    assert chain.underlying_ltp == 25000.0
    assert chain.expiry == ""
    assert len(chain.strikes) == 0


def test_missing_strike_price():
    """Test handling of missing strike price in option chain."""
    raw = {
        "records": {
            "underlyingValue": 25000.0,
            "expiryDates": ["28-Aug-2026"],
            "data": [
                {
                    "CE": {"lastPrice": 200.0},
                    "PE": {"lastPrice": 180.0},
                }
            ],
        }
    }

    chain = parse_option_chain(raw, "NIFTY")
    # Should handle missing strikePrice gracefully
    assert len(chain.strikes) == 1
    assert chain.strikes[0].strike == 0.0


def test_zero_option_prices():
    """Test handling of zero option prices."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=25000.0, call_ltp=0.0, put_ltp=0.0),
        ],
    )

    atm = find_atm_strike(chain)
    assert atm is not None
    assert atm.call_ltp == 0.0
    assert atm.put_ltp == 0.0
    assert atm.straddle_premium == 0.0


def test_negative_option_prices():
    """Test handling of negative option prices (invalid but should not crash)."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=25000.0, call_ltp=-10.0, put_ltp=-5.0),
        ],
    )

    atm = find_atm_strike(chain)
    assert atm is not None
    # System should handle negative values without crashing
    assert atm.call_ltp == -10.0
    assert atm.put_ltp == -5.0


def test_missing_ce_pe_data():
    """Test handling of missing CE/PE data in option chain."""
    raw = {
        "records": {
            "underlyingValue": 25000.0,
            "expiryDates": ["28-Aug-2026"],
            "data": [
                {
                    "strikePrice": 25000.0,
                    "CE": {"lastPrice": 200.0},
                    # Missing PE
                }
            ],
        }
    }

    chain = parse_option_chain(raw, "NIFTY")
    assert len(chain.strikes) == 1
    assert chain.strikes[0].call_ltp == 200.0
    assert chain.strikes[0].put_ltp == 0.0  # Should default to 0


def test_invalid_timestamp_format():
    """Test handling of invalid timestamp format."""
    raw = {
        "records": {
            "underlyingValue": 25000.0,
            "expiryDates": ["28-Aug-2026"],
            "timestamp": "invalid-timestamp",
            "data": [],
        }
    }

    chain = parse_option_chain(raw, "NIFTY")
    # Should default to current time
    assert chain.timestamp is not None
    assert isinstance(chain.timestamp, datetime)


def test_candle_with_zero_price():
    """Test candle aggregator with zero price."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    tick = PriceTick(
        symbol="NIFTY", price=0.0, timestamp=datetime(2026, 8, 23, 10, 30, 0)
    )

    agg.process_tick(tick)
    candle = agg.active_candles[1]
    assert candle.open == 0.0
    assert candle.high == 0.0
    assert candle.low == 0.0
    assert candle.close == 0.0


def test_candle_with_negative_price():
    """Test candle aggregator with negative price (invalid but should not crash)."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    tick = PriceTick(
        symbol="NIFTY", price=-100.0, timestamp=datetime(2026, 8, 23, 10, 30, 0)
    )

    agg.process_tick(tick)
    candle = agg.active_candles[1]
    assert candle.open == -100.0
    assert candle.high == -100.0
    assert candle.low == -100.0
    assert candle.close == -100.0


def test_candle_with_extreme_prices():
    """Test candle aggregator with extreme price values."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 23, 10, 30, 0)

    # Very high price
    agg.process_tick(
        PriceTick(symbol="NIFTY", price=1_000_000.0, timestamp=base_time)
    )
    # Very low price
    agg.process_tick(
        PriceTick(symbol="NIFTY", price=1.0, timestamp=base_time + timedelta(seconds=1))
    )

    candle = agg.active_candles[1]
    assert candle.high == 1_000_000.0
    assert candle.low == 1.0


def test_missing_underlying_value():
    """Test handling of missing underlying value in option chain."""
    raw = {
        "records": {
            "expiryDates": ["28-Aug-2026"],
            "data": [],
        }
    }

    chain = parse_option_chain(raw, "NIFTY")
    assert chain.underlying_ltp == 0.0


def test_atm_with_none_chain():
    """Test ATM selection with None chain."""
    atm = find_atm_strike(None)
    assert atm is None


def test_price_tick_with_none_timestamp():
    """Test that PriceTick handles None timestamp gracefully."""
    # Dataclasses don't enforce type validation at runtime
    # This test documents current behavior
    tick = PriceTick(symbol="NIFTY", price=25000.0, timestamp=None)
    assert tick.timestamp is None


def test_candle_aggregator_with_no_ticks():
    """Test candle aggregator state before any ticks."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1, 5])
    assert agg.active_candles == {}
    assert agg.completed_candles == {1: [], 5: []}


def test_serializers_with_none_values():
    """Test serializers handle None values gracefully."""
    from src.serializers import serialize_atm, serialize_chain

    # Serialize None ATM
    result = serialize_atm(None)
    assert result is None

    # Serialize None chain
    result = serialize_chain(None, None)
    assert result is None
