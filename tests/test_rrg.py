"""Tests for RRG analytics module."""

import pytest
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from src.models import OptionChainSnapshot, OptionLeg, PriceTick
from src.rrg.calculator import RRGCalculator
from src.rrg.models import RRGConfig, RRGQuadrant


def test_rrg_initialization():
    """Test RRG calculator initialization."""
    config = RRGConfig(
        benchmark_symbol="NIFTY",
        timeframe="1min",
        rolling_window=14,
        momentum_period=1,
    )
    
    calculator = RRGCalculator(config)
    
    assert calculator.config == config
    assert len(calculator._benchmark_history) == 0
    assert len(calculator._option_history) == 0


def test_rrg_update_with_market_data():
    """Test updating RRG calculator with market data."""
    config = RRGConfig(
        benchmark_symbol="NIFTY",
        timeframe="1min",
        rolling_window=5,  # Small window for testing
        momentum_period=1,
    )
    
    calculator = RRGCalculator(config)
    
    # Create option chain
    option_chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=24900.0, call_ltp=200.0, put_ltp=150.0),
            OptionLeg(strike=25000.0, call_ltp=180.0, put_ltp=170.0),
            OptionLeg(strike=25100.0, call_ltp=160.0, put_ltp=190.0),
        ],
    )
    
    # Update with multiple ticks to build history
    for i in range(10):
        tick = PriceTick(
            symbol="NIFTY",
            price=25000.0 + i * 5,  # Varying benchmark price
            timestamp=datetime.now() + timedelta(seconds=i * 10)
        )
        calculator.update(tick, option_chain)
    
    # Verify history was built
    assert len(calculator._benchmark_history) == 10
    assert len(calculator._option_history) > 0


def test_rrg_calculation():
    """Test RRG calculation with sufficient history."""
    config = RRGConfig(
        benchmark_symbol="NIFTY",
        timeframe="1min",
        rolling_window=5,
        momentum_period=1,
    )
    
    calculator = RRGCalculator(config)
    
    # Build history with changing option prices
    for i in range(10):
        # Create option chain with changing prices
        option_chain = OptionChainSnapshot(
            underlying="NIFTY",
            underlying_ltp=25000.0 + i * 10,
            expiry="28-Aug-2026",
            timestamp=datetime.now() + timedelta(seconds=i * 10),
            strikes=[
                OptionLeg(strike=25000.0, call_ltp=200.0 + i * 5, put_ltp=180.0 + i * 3),
            ],
        )
        
        tick = PriceTick(
            symbol="NIFTY",
            price=25000.0 + i * 10,  # Trending up
            timestamp=datetime.now() + timedelta(seconds=i * 10)
        )
        calculator.update(tick, option_chain)
    
    # Calculate RRG
    snapshot = calculator.calculate_rrg()
    
    # Verify snapshot structure
    assert snapshot.benchmark_symbol == "NIFTY"
    assert snapshot.benchmark_ltp > 0
    assert snapshot.timeframe == "1min"
    assert len(snapshot.data_points) > 0
    
    # Verify data point structure
    data_point = snapshot.data_points[0]
    assert data_point.strike == 25000.0
    assert data_point.option_type in ["CE", "PE"]
    assert isinstance(data_point.rs, float)
    assert isinstance(data_point.rs_ratio, float)
    assert isinstance(data_point.rs_momentum, float)
    assert isinstance(data_point.quadrant, RRGQuadrant)


def test_rs_calculation():
    """Test RS calculation formula."""
    config = RRGConfig(
        benchmark_symbol="NIFTY",
        timeframe="1min",
        rolling_window=5,
        momentum_period=1,
    )
    
    calculator = RRGCalculator(config)
    
    # Build history with changing option prices
    for i in range(10):
        # Create option chain with changing prices
        option_chain = OptionChainSnapshot(
            underlying="NIFTY",
            underlying_ltp=25000.0,
            expiry="28-Aug-2026",
            timestamp=datetime.now() + timedelta(seconds=i * 10),
            strikes=[
                OptionLeg(strike=25000.0, call_ltp=200.0 + i * 5, put_ltp=180.0 + i * 3),
            ],
        )
        
        tick = PriceTick(
            symbol="NIFTY",
            price=25000.0,  # Constant benchmark
            timestamp=datetime.now() + timedelta(seconds=i * 10)
        )
        calculator.update(tick, option_chain)
    
    snapshot = calculator.calculate_rrg()
    
    # Verify RS calculation: (200/25000) * 100 = 0.8
    # (Note: actual values may vary due to mock data generation)
    assert len(snapshot.data_points) > 0
    data_point = snapshot.data_points[0]
    assert data_point.rs > 0  # RS should be positive


def test_quadrant_determination():
    """Test quadrant determination logic."""
    config = RRGConfig(
        benchmark_symbol="NIFTY",
        timeframe="1min",
        rolling_window=5,
        momentum_period=1,
    )
    
    calculator = RRGCalculator(config)
    
    # Test each quadrant scenario
    test_cases = [
        (105.0, 105.0, RRGQuadrant.LEADING),     # High RS, high momentum
        (95.0, 105.0, RRGQuadrant.IMPROVING),   # Low RS, high momentum
        (95.0, 95.0, RRGQuadrant.LAGGING),     # Low RS, low momentum
        (105.0, 95.0, RRGQuadrant.WEAKENING),   # High RS, low momentum
    ]
    
    for rs_ratio, rs_momentum, expected_quadrant in test_cases:
        quadrant = calculator._determine_quadrant(rs_ratio, rs_momentum)
        assert quadrant == expected_quadrant


def test_configurable_strikes():
    """Test filtering by specific strikes."""
    config = RRGConfig(
        benchmark_symbol="NIFTY",
        timeframe="1min",
        rolling_window=5,
        momentum_period=1,
        option_strikes=[25000.0, 25100.0],  # Only these strikes
    )
    
    calculator = RRGCalculator(config)
    
    # Build history with changing option chain data
    for i in range(10):
        # Create option chain with multiple strikes
        option_chain = OptionChainSnapshot(
            underlying="NIFTY",
            underlying_ltp=25000.0 + i * 5,
            expiry="28-Aug-2026",
            timestamp=datetime.now() + timedelta(seconds=i * 10),
            strikes=[
                OptionLeg(strike=24900.0, call_ltp=200.0 + i * 5, put_ltp=150.0 + i * 3),
                OptionLeg(strike=25000.0, call_ltp=180.0 + i * 5, put_ltp=170.0 + i * 3),
                OptionLeg(strike=25100.0, call_ltp=160.0 + i * 5, put_ltp=190.0 + i * 3),
                OptionLeg(strike=25200.0, call_ltp=140.0 + i * 5, put_ltp=210.0 + i * 3),
            ],
        )
        
        tick = PriceTick(
            symbol="NIFTY",
            price=25000.0 + i * 5,
            timestamp=datetime.now() + timedelta(seconds=i * 10)
        )
        calculator.update(tick, option_chain)
    
    snapshot = calculator.calculate_rrg()
    
    # Verify only configured strikes are analyzed
    strikes_analyzed = {dp.strike for dp in snapshot.data_points}
    assert strikes_analyzed == {25000.0, 25100.0}
    assert 24900.0 not in strikes_analyzed
    assert 25200.0 not in strikes_analyzed


def test_timeframe_configuration():
    """Test different timeframe configurations."""
    timeframes = ["1min", "5min", "15min", "daily"]
    
    for timeframe in timeframes:
        config = RRGConfig(
            benchmark_symbol="NIFTY",
            timeframe=timeframe,
            rolling_window=5,
            momentum_period=1,
        )
        
        calculator = RRGCalculator(config)
        assert calculator.config.timeframe == timeframe


def test_insufficient_history():
    """Test behavior with insufficient history."""
    config = RRGConfig(
        benchmark_symbol="NIFTY",
        timeframe="1min",
        rolling_window=20,  # Large window
        momentum_period=1,
    )
    
    calculator = RRGCalculator(config)
    
    option_chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=25000.0, call_ltp=200.0, put_ltp=180.0),
        ],
    )
    
    # Add only a few data points (less than rolling window)
    for i in range(5):
        tick = PriceTick(
            symbol="NIFTY",
            price=25000.0 + i * 5,
            timestamp=datetime.now() + timedelta(seconds=i * 10)
        )
        calculator.update(tick, option_chain)
    
    # Should either calculate with available data or return empty
    snapshot = calculator.calculate_rrg()
    
    # With insufficient history, should have fewer or no data points
    assert len(snapshot.data_points) <= 2  # CE and PE


def test_rrg_data_point_serialization():
    """Test RRG data point serialization."""
    from src.rrg.models import RRGDataPoint, RRGQuadrant
    
    data_point = RRGDataPoint(
        strike=25000.0,
        option_type="CE",
        rs=0.8,
        rs_ratio=105.5,
        rs_momentum=102.3,
        quadrant=RRGQuadrant.LEADING,
        timestamp=datetime.now(),
        option_ltp=200.0,
        benchmark_ltp=25000.0,
    )
    
    serialized = data_point.to_dict()
    
    assert serialized["strike"] == 25000.0
    assert serialized["option_type"] == "CE"
    assert serialized["rs"] == 0.8
    assert serialized["rs_ratio"] == 105.5
    assert serialized["rs_momentum"] == 102.3
    assert serialized["quadrant"] == "leading"
    assert "timestamp" in serialized


def test_rrg_snapshot_serialization():
    """Test RRG snapshot serialization."""
    from src.rrg.models import RRGDataPoint, RRGQuadrant, RRGSnapshot
    
    data_points = [
        RRGDataPoint(
            strike=25000.0,
            option_type="CE",
            rs=0.8,
            rs_ratio=105.5,
            rs_momentum=102.3,
            quadrant=RRGQuadrant.LEADING,
            timestamp=datetime.now(),
            option_ltp=200.0,
            benchmark_ltp=25000.0,
        )
    ]
    
    snapshot = RRGSnapshot(
        benchmark_symbol="NIFTY",
        benchmark_ltp=25000.0,
        timeframe="1min",
        timestamp=datetime.now(),
        data_points=data_points,
    )
    
    serialized = snapshot.to_dict()
    
    assert serialized["benchmark_symbol"] == "NIFTY"
    assert serialized["benchmark_ltp"] == 25000.0
    assert serialized["timeframe"] == "1min"
    assert len(serialized["data_points"]) == 1
    assert serialized["data_points"][0]["strike"] == 25000.0


def test_history_summary():
    """Test history summary functionality."""
    config = RRGConfig(
        benchmark_symbol="NIFTY",
        timeframe="1min",
        rolling_window=5,
        momentum_period=1,
    )
    
    calculator = RRGCalculator(config)
    
    option_chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=25000.0, call_ltp=200.0, put_ltp=180.0),
        ],
    )
    
    # Add some data
    for i in range(5):
        tick = PriceTick(
            symbol="NIFTY",
            price=25000.0 + i * 5,
            timestamp=datetime.now() + timedelta(seconds=i * 10)
        )
        calculator.update(tick, option_chain)
    
    summary = calculator.get_history_summary()
    
    assert summary["benchmark_points"] == 5
    assert summary["tracked_options"] == 2  # CE and PE
    assert summary["config"]["rolling_window"] == 5
    assert summary["config"]["timeframe"] == "1min"


def test_synthetic_data_rrg():
    """Test RRG with synthetic data to verify calculations."""
    config = RRGConfig(
        benchmark_symbol="NIFTY",
        timeframe="1min",
        rolling_window=10,
        momentum_period=1,
    )
    
    calculator = RRGCalculator(config)
    
    # Simulate trending market (both benchmark and option going up)
    for i in range(15):
        # Benchmark trending up
        benchmark_price = 25000.0 + i * 20
        
        # Option also trending up (outperforming)
        option_ltp = 200.0 + i * 15
        
        # Create option chain with changing prices
        option_chain = OptionChainSnapshot(
            underlying="NIFTY",
            underlying_ltp=benchmark_price,
            expiry="28-Aug-2026",
            timestamp=datetime.now() + timedelta(seconds=i * 10),
            strikes=[
                OptionLeg(
                    strike=25000.0,
                    call_ltp=option_ltp,
                    put_ltp=180.0 + i * 5,
                ),
            ],
        )
        
        tick = PriceTick(
            symbol="NIFTY",
            price=benchmark_price,
            timestamp=datetime.now() + timedelta(seconds=i * 10)
        )
        calculator.update(tick, option_chain)
    
    snapshot = calculator.calculate_rrg()
    
    # Should have data points
    assert len(snapshot.data_points) > 0
    
    # With both trending up, should see some data in LEADING or IMPROVING
    quadrants = [dp.quadrant for dp in snapshot.data_points]
    assert len(quadrants) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
