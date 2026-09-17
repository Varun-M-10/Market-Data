"""End-to-end test using mock data provider."""

import pytest
import time
from datetime import datetime

from src.config import load_config
from src.engine import MarketEngine


def test_end_to_end_mock_pipeline():
    """Test complete pipeline with mock data provider."""
    # Configure for mock data with fast polling
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 0.1,  # Fast for testing
        "candle_intervals": [1],
        "price_calculator": "mock",
    }

    engine = MarketEngine(cfg)
    snapshots = []

    def capture_snapshot(snapshot):
        snapshots.append(snapshot)

    engine.subscribe(capture_snapshot)
    engine.start()

    try:
        # Wait for a few ticks
        time.sleep(0.5)

        # Verify we received snapshots
        assert len(snapshots) > 0, "Should receive at least one snapshot"

        # Verify snapshot structure
        latest = snapshots[-1]
        assert "underlying" in latest
        assert "price" in latest
        assert "atm" in latest
        assert "candles" in latest
        assert "tick_count" in latest
        assert "data_source" in latest

        # Verify data content
        assert latest["underlying"] == "NIFTY"
        assert latest["data_source"] == "mock"
        assert latest["price"] is not None
        assert latest["price"] > 0
        assert latest["tick_count"] > 0

        # Verify ATM data
        if latest["atm"] is not None:
            assert "strike" in latest["atm"]
            assert "call_ltp" in latest["atm"]
            assert "put_ltp" in latest["atm"]
            assert "straddle_premium" in latest["atm"]

        # Verify candle data
        assert "1" in latest["candles"]
        candle_data = latest["candles"]["1"]
        assert "active" in candle_data
        assert "completed" in candle_data

        # Verify calculated prices
        assert "calculated_prices" in latest
        if latest["calculated_prices"] is not None:
            assert "straddle_premium" in latest["calculated_prices"]
            assert "calculation_method" in latest["calculated_prices"]

    finally:
        engine.stop()


def test_end_to_end_multiple_intervals():
    """Test pipeline with multiple candle intervals."""
    cfg = {
        "underlying": "BANKNIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 0.1,
        "candle_intervals": [1, 5, 15],
        "price_calculator": "mock",
    }

    engine = MarketEngine(cfg)
    snapshots = []

    engine.subscribe(lambda s: snapshots.append(s))
    engine.start()

    try:
        time.sleep(0.5)

        assert len(snapshots) > 0
        latest = snapshots[-1]

        # Verify all intervals are present
        assert "1" in latest["candles"]
        assert "5" in latest["candles"]
        assert "15" in latest["candles"]

        # Verify each interval has data structure
        for interval in ["1", "5", "15"]:
            assert "active" in latest["candles"][interval]
            assert "completed" in latest["candles"][interval]

    finally:
        engine.stop()


def test_end_to_end_config_loading():
    """Test pipeline using configuration from file."""
    cfg = load_config()
    # Override for testing
    cfg["poll_interval_seconds"] = 0.1
    cfg["data_source"] = "mock"

    engine = MarketEngine(cfg)
    snapshots = []

    engine.subscribe(lambda s: snapshots.append(s))
    engine.start()

    try:
        time.sleep(0.5)

        assert len(snapshots) > 0
        latest = snapshots[-1]

        # Verify config is applied
        assert latest["underlying"] == cfg["underlying"]
        assert latest["data_source"] == cfg["data_source"]

    finally:
        engine.stop()


def test_end_to_end_price_updates():
    """Test that prices update over time."""
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 0.1,
        "candle_intervals": [1],
        "price_calculator": "mock",
    }

    engine = MarketEngine(cfg)
    snapshots = []

    engine.subscribe(lambda s: snapshots.append(s))
    engine.start()

    try:
        time.sleep(0.5)

        # Check that prices are changing (mock data varies)
        prices = [s["price"] for s in snapshots if s["price"] is not None]
        assert len(prices) > 1

        # Mock data should have some variation
        price_variance = max(prices) - min(prices)
        assert price_variance > 0, "Mock prices should vary"

    finally:
        engine.stop()


def test_end_to_end_atm_updates():
    """Test that ATM data updates with new option chains."""
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 0.1,
        "candle_intervals": [1],
        "price_calculator": "mock",
    }

    engine = MarketEngine(cfg)
    snapshots = []

    engine.subscribe(lambda s: snapshots.append(s))
    engine.start()

    try:
        time.sleep(0.5)

        # Check that we have ATM data
        atm_snapshots = [s["atm"] for s in snapshots if s["atm"] is not None]
        assert len(atm_snapshots) > 0, "Should have ATM data"

        # Verify ATM structure
        latest_atm = atm_snapshots[-1]
        assert latest_atm["strike"] > 0
        assert latest_atm["call_ltp"] >= 0
        assert latest_atm["put_ltp"] >= 0
        assert latest_atm["straddle_premium"] >= 0

    finally:
        engine.stop()


def test_end_to_end_candle_building():
    """Test that candles build and complete over time."""
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 0.1,
        "candle_intervals": [1],
        "price_calculator": "mock",
    }

    engine = MarketEngine(cfg)
    snapshots = []

    engine.subscribe(lambda s: snapshots.append(s))
    engine.start()

    try:
        time.sleep(0.5)

        # Check that active candle is building
        latest = snapshots[-1]
        active_candle = latest["candles"]["1"]["active"]

        if active_candle is not None:
            assert "open" in active_candle
            assert "high" in active_candle
            assert "low" in active_candle
            assert "close" in active_candle
            assert "tick_count" in active_candle
            assert active_candle["tick_count"] > 0

    finally:
        engine.stop()


def test_end_to_end_error_recovery():
    """Test that engine continues after temporary errors."""
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 0.1,
        "candle_intervals": [1],
        "price_calculator": "mock",
    }

    engine = MarketEngine(cfg)
    snapshots = []

    def capture_with_error(snapshot):
        snapshots.append(snapshot)
        # Simulate occasional callback error
        if len(snapshots) % 3 == 0:
            raise Exception("Simulated callback error")

    engine.subscribe(capture_with_error)
    engine.start()

    try:
        time.sleep(0.5)

        # Engine should continue despite callback errors
        assert len(snapshots) > 0
        assert engine.is_running

    finally:
        engine.stop()


def test_end_to_end_subscription_management():
    """Test subscribe/unsubscribe functionality."""
    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 0.1,
        "candle_intervals": [1],
        "price_calculator": "mock",
    }

    engine = MarketEngine(cfg)
    snapshots1 = []
    snapshots2 = []

    callback1 = lambda s: snapshots1.append(s)
    callback2 = lambda s: snapshots2.append(s)

    engine.subscribe(callback1)
    engine.subscribe(callback2)
    engine.start()

    try:
        time.sleep(0.3)

        # Both should receive updates
        assert len(snapshots1) > 0
        assert len(snapshots2) > 0

        # Unsubscribe first callback
        engine.unsubscribe(callback1)
        count1 = len(snapshots1)
        count2 = len(snapshots2)

        time.sleep(0.3)

        # First should stop receiving, second should continue
        assert len(snapshots1) == count1
        assert len(snapshots2) > count2

    finally:
        engine.stop()
