"""Controlled verification tests for backend behavior against requirements."""

import pytest
from datetime import datetime, timedelta

from src.candles.aggregator import CandleAggregator
from src.models import OptionChainSnapshot, OptionLeg, PriceTick
from src.option_chain import find_atm_strike, parse_option_chain
from src.price_calculator import MockPriceCalculator


def test_1_continuous_price_data():
    """Verify continuous price data from configured source."""
    from src.data_sources import MockDataSource

    source = MockDataSource(underlying="NIFTY", poll_interval=0.1)
    ticks = []
    
    # Collect 5 ticks
    for i, tick in enumerate(source.stream_ticks()):
        ticks.append(tick)
        if i >= 4:
            break
    
    # Verify continuous data
    assert len(ticks) == 5
    assert all(tick.symbol == "NIFTY" for tick in ticks)
    assert all(tick.price > 0 for tick in ticks)
    assert all(tick.timestamp is not None for tick in ticks)
    
    # Verify timestamps are increasing
    timestamps = [tick.timestamp for tick in ticks]
    assert timestamps == sorted(timestamps)
    
    print("✅ Test 1 PASSED: Continuous price data working")


def test_2_atm_calculation_correctness():
    """Verify ATM calculated correctly from underlying price and strikes."""
    # Create controlled scenario
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=24800.0, call_ltp=200.0, put_ltp=150.0),
            OptionLeg(strike=24900.0, call_ltp=180.0, put_ltp=170.0),
            OptionLeg(strike=25000.0, call_ltp=160.0, put_ltp=190.0),  # Exact ATM
            OptionLeg(strike=25100.0, call_ltp=140.0, put_ltp=210.0),
            OptionLeg(strike=25200.0, call_ltp=120.0, put_ltp=230.0),
        ],
    )
    
    atm = find_atm_strike(chain)
    
    # Verify ATM is 25000 (exact match)
    assert atm is not None
    assert atm.strike == 25000.0
    assert atm.call_ltp == 160.0
    assert atm.put_ltp == 190.0
    assert atm.distance_from_spot == 0.0
    
    # Test with non-exact match
    chain2 = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25025.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=25000.0, call_ltp=160.0, put_ltp=190.0),
            OptionLeg(strike=25100.0, call_ltp=140.0, put_ltp=210.0),
        ],
    )
    
    atm2 = find_atm_strike(chain2)
    assert atm2.strike == 25000.0  # 25 away vs 75 away
    assert atm2.distance_from_spot == 25.0
    
    print("✅ Test 2 PASSED: ATM calculation correct")


def test_3_atm_call_put_from_option_chain():
    """Verify ATM Call and Put values from correct Option Chain contracts."""
    # Create specific option chain scenario
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=24900.0, call_ltp=175.0, put_ltp=185.0),
            OptionLeg(strike=25000.0, call_ltp=165.5, put_ltp=195.25),  # ATM
            OptionLeg(strike=25100.0, call_ltp=155.0, put_ltp=205.0),
        ],
    )
    
    atm = find_atm_strike(chain)
    
    # Verify values come from correct strike (25000)
    assert atm.strike == 25000.0
    assert atm.call_ltp == 165.5  # From 25000 CE
    assert atm.put_ltp == 195.25   # From 25000 PE
    
    # Verify NOT from neighboring strikes
    assert atm.call_ltp != 175.0  # Not from 24900
    assert atm.call_ltp != 155.0  # Not from 25100
    
    print("✅ Test 3 PASSED: ATM Call/Put from correct contracts")


def test_4_ohlc_calculation_correctness():
    """Verify candle OHLC calculated correctly from incoming prices."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 24, 10, 30, 0)
    
    # Simulate price sequence: 25000, 25050, 24980, 25100, 24950
    prices = [25000.0, 25050.0, 24980.0, 25100.0, 24950.0]
    
    for i, price in enumerate(prices):
        tick = PriceTick(
            symbol="NIFTY",
            price=price,
            timestamp=base_time + timedelta(seconds=i * 10)
        )
        agg.process_tick(tick)
    
    candle = agg.active_candles[1]
    
    # Verify OHLC
    assert candle.open == 25000.0   # First price
    assert candle.high == 25100.0   # Highest price
    assert candle.low == 24950.0    # Lowest price
    assert candle.close == 24950.0   # Last price
    assert candle.tick_count == 5
    
    print("✅ Test 4 PASSED: OHLC calculation correct")


def test_5_realtime_high_low_updates():
    """Verify High/Low update immediately as new prices arrive."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 24, 10, 30, 0)
    
    # First tick
    tick1 = PriceTick(symbol="NIFTY", price=25000.0, timestamp=base_time)
    agg.process_tick(tick1)
    candle = agg.active_candles[1]
    
    assert candle.high == 25000.0
    assert candle.low == 25000.0
    
    # Higher price
    tick2 = PriceTick(symbol="NIFTY", price=25050.0, timestamp=base_time + timedelta(seconds=5))
    agg.process_tick(tick2)
    candle = agg.active_candles[1]
    
    assert candle.high == 25050.0  # Updated immediately
    assert candle.low == 25000.0   # Unchanged
    
    # Lower price
    tick3 = PriceTick(symbol="NIFTY", price=24980.0, timestamp=base_time + timedelta(seconds=10))
    agg.process_tick(tick3)
    candle = agg.active_candles[1]
    
    assert candle.high == 25050.0  # Unchanged
    assert candle.low == 24980.0   # Updated immediately
    
    print("✅ Test 5 PASSED: Real-time High/Low updates working")


def test_6_candle_rollover_boundary():
    """Verify candle automatically closes at correct 1m/5m/15m boundary."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 24, 10, 30, 0)
    expected_close = (base_time + timedelta(minutes=1)).replace(second=0, microsecond=0)
    
    # Tick in first minute (10:30:00)
    tick1 = PriceTick(symbol="NIFTY", price=25000.0, timestamp=base_time)
    agg.process_tick(tick1)
    
    # Tick in next minute (10:31:00) - should trigger rollover
    tick2 = PriceTick(symbol="NIFTY", price=25010.0, timestamp=base_time + timedelta(minutes=1))
    completed = agg.process_tick(tick2)
    
    # Verify rollover
    assert len(completed) == 1
    assert completed[0].is_complete == True
    assert completed[0].open_time.replace(tzinfo=None) == base_time.replace(second=0, microsecond=0)
    assert completed[0].close_time.replace(tzinfo=None) == expected_close
    
    # Verify new candle started
    new_candle = agg.active_candles[1]
    assert new_candle.open == 25010.0
    assert new_candle.open_time.replace(tzinfo=None) == expected_close
    
    print("✅ Test 6 PASSED: Candle rollover at boundary working")


def test_7_new_candle_after_rollover():
    """Verify new candle automatically starts after rollover."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base_time = datetime(2026, 8, 24, 10, 30, 0)
    
    # Build first candle
    for i in range(3):
        tick = PriceTick(
            symbol="NIFTY",
            price=25000.0 + i,
            timestamp=base_time + timedelta(seconds=i * 10)
        )
        agg.process_tick(tick)
    
    # Trigger rollover
    tick_rollover = PriceTick(
        symbol="NIFTY",
        price=25010.0,
        timestamp=base_time + timedelta(minutes=1)
    )
    completed = agg.process_tick(tick_rollover)
    
    # Verify new candle exists and is separate
    assert len(completed) == 1
    assert agg.active_candles[1] is not None
    assert agg.active_candles[1] != completed[0]
    assert agg.active_candles[1].tick_count == 1
    assert agg.active_candles[1].open == 25010.0
    
    # Verify completed candle is archived
    assert len(agg.completed_candles[1]) == 1
    assert agg.completed_candles[1][0] == completed[0]
    
    print("✅ Test 7 PASSED: New candle starts after rollover")


def test_8_independent_interval_calculation():
    """Verify 1m, 5m, 15m candles independently calculated."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1, 5, 15])
    base_time = datetime(2026, 8, 24, 10, 30, 0)
    
    # Process ticks within same minute
    for i in range(5):
        tick = PriceTick(
            symbol="NIFTY",
            price=25000.0 + i,
            timestamp=base_time + timedelta(seconds=i * 5)
        )
        agg.process_tick(tick)
    
    # All intervals should have active candles
    assert 1 in agg.active_candles
    assert 5 in agg.active_candles
    assert 15 in agg.active_candles
    
    # All should have same number of ticks (same time period)
    assert agg.active_candles[1].tick_count == 5
    assert agg.active_candles[5].tick_count == 5
    assert agg.active_candles[15].tick_count == 5
    
    # But different open/close times
    assert agg.active_candles[1].close_time.replace(tzinfo=None) == base_time + timedelta(minutes=1)
    assert agg.active_candles[5].close_time.replace(tzinfo=None) == base_time + timedelta(minutes=5)
    assert agg.active_candles[15].close_time.replace(tzinfo=None) == base_time + timedelta(minutes=15)
    
    print("✅ Test 8 PASSED: Independent interval calculation working")


def test_9_call_put_formula_isolation():
    """Verify Call + Put formula is isolated and configurable."""
    from src.models import ATMResult
    from src.price_calculator import get_calculator
    
    # Test mock calculator
    calc = get_calculator("mock")
    atm = ATMResult(
        strike=25000.0,
        call_ltp=200.0,
        put_ltp=180.0,
        straddle_premium=380.0,
        underlying_ltp=25000.0,
        distance_from_spot=0.0,
    )
    
    result = calc.calculate(atm)
    
    # Verify formula is Call + Put
    assert result["straddle_premium"] == 380.0  # 200 + 180
    assert result["call_put_ratio"] == 200.0 / 180.0
    assert result["synthetic_price"] == 200.0 - 180.0
    
    # Verify method is labeled
    assert result["calculation_method"] == "mock_simple_addition"
    
    # Verify calculator is configurable
    calc_bs = get_calculator("black_scholes")
    assert calc_bs is not None
    assert isinstance(calc_bs, type(calc)) == False  # Different type
    
    print("✅ Test 9 PASSED: Call + Put formula isolated and configurable")
    print("   Current formula: straddle_premium = call_ltp + put_ltp")
    print("   This is TEMPORARY - awaiting client confirmation")


def test_10_atm_method_not_delta_based():
    """Confirm current implementation does NOT use Delta ≈ 0.5."""
    from src.option_chain import find_atm_strike
    
    # Create scenario where Delta-based would differ from price-based
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,
        expiry="28-Aug-2026",
        timestamp=datetime.now(),
        strikes=[
            OptionLeg(strike=24900.0, call_ltp=300.0, put_ltp=100.0),  # Far ITM call (high delta)
            OptionLeg(strike=25000.0, call_ltp=200.0, put_ltp=200.0),  # ATM by price
            OptionLeg(strike=25100.0, call_ltp=100.0, put_ltp=300.0),  # Far ITM put (high delta)
        ],
    )
    
    atm = find_atm_strike(chain)
    
    # Current implementation uses price proximity
    assert atm.strike == 25000.0  # Exact price match
    
    # If Delta-based, might choose 24900 or 25100 due to high delta
    # Current implementation does NOT consider delta
    
    # Verify no delta calculation in code
    import inspect
    source = inspect.getsource(find_atm_strike)
    assert "delta" not in source.lower()
    assert "abs(leg.strike - spot)" in source  # Price-based method
    
    print("✅ Test 10 PASSED: Current ATM method is price-based, NOT Delta ≈ 0.5")
    print("   Current method: min(|strike - spot|)")
    print("   Delta-based method is NOT implemented - awaiting client confirmation")


def test_11_identify_missing_functionality():
    """Identify what is still missing from functional requirements."""
    missing_items = []
    
    # Check for Delta-based ATM
    try:
        from src.option_chain import find_atm_strike_delta
        delta_method_exists = True
    except ImportError:
        delta_method_exists = False
        missing_items.append("Delta ≈ 0.5 ATM selection method")
    
    # Check for confirmed business formula
    from src.price_calculator import get_calculator
    calc = get_calculator()
    if hasattr(calc, 'calculate'):
        result = calc.calculate(None)
        if result.get("calculation_method") == "mock_simple_addition":
            missing_items.append("Confirmed Call + Put business formula")
    
    # Check for editor/admin table
    try:
        from src.admin import AdminTable
        admin_exists = True
    except ImportError:
        admin_exists = False
        missing_items.append("Editor/admin table implementation")
    
    # Check for final data provider configuration
    # (This is configurable, so not strictly missing)
    
    print("✅ Test 11 COMPLETED: Missing functionality identified")
    for item in missing_items:
        print(f"   - {item}")
    
    if not missing_items:
        print("   All confirmed requirements implemented!")


def test_12_controlled_candle_ohlc_stream():
    """Controlled test to prove candle OHLC values and rollover are correct."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1, 5])
    base_time = datetime(2026, 8, 24, 10, 30, 0)
    
    # Simulate realistic price stream across minute boundary
    price_stream = [
        (25000.0, 0),    # 10:30:00 - Start of candle
        (25025.0, 10),   # 10:30:10 - Higher
        (24990.0, 20),   # 10:30:20 - Lower
        (25015.0, 30),   # 10:30:30 - Mid
        (25050.0, 40),   # 10:30:40 - New high
        (24985.0, 50),   # 10:30:50 - New low
        (25010.0, 60),   # 10:31:00 - Rollover to new minute
        (25020.0, 70),   # 10:31:10 - New candle
    ]
    
    completed_candles = []
    
    for price, offset in price_stream:
        tick = PriceTick(
            symbol="NIFTY",
            price=price,
            timestamp=base_time + timedelta(seconds=offset)
        )
        completed = agg.process_tick(tick)
        completed_candles.extend(completed)
    
    # Verify first candle (10:30-10:31)
    assert len(completed_candles) == 1
    first_candle = completed_candles[0]
    
    assert first_candle.open == 25000.0
    assert first_candle.high == 25050.0
    assert first_candle.low == 24985.0
    assert first_candle.close == 24985.0  # Last price before rollover
    assert first_candle.tick_count == 6
    assert first_candle.is_complete == True
    
    # Verify second candle (10:31-10:32) - building
    second_candle = agg.active_candles[1]
    assert second_candle.open == 25010.0
    assert second_candle.high == 25020.0
    assert second_candle.low == 25010.0
    assert second_candle.close == 25020.0
    assert second_candle.tick_count == 2
    assert second_candle.is_complete == False
    
    # Verify 5m candle still building (no rollover)
    five_m_candle = agg.active_candles[5]
    assert five_m_candle.tick_count == 8  # All ticks
    assert five_m_candle.is_complete == False
    
    print("✅ Test 12 PASSED: Controlled candle OHLC and rollover verified")
    print(f"   First candle: O={first_candle.open}, H={first_candle.high}, L={first_candle.low}, C={first_candle.close}")
    print(f"   Second candle: O={second_candle.open}, H={second_candle.high}, L={second_candle.low}, C={second_candle.close}")


if __name__ == "__main__":
    # Run all verification tests
    test_1_continuous_price_data()
    test_2_atm_calculation_correctness()
    test_3_atm_call_put_from_option_chain()
    test_4_ohlc_calculation_correctness()
    test_5_realtime_high_low_updates()
    test_6_candle_rollover_boundary()
    test_7_new_candle_after_rollover()
    test_8_independent_interval_calculation()
    test_9_call_put_formula_isolation()
    test_10_atm_method_not_delta_based()
    test_11_identify_missing_functionality()
    test_12_controlled_candle_ohlc_stream()
    
    print("\n" + "="*60)
    print("✅ ALL VERIFICATION TESTS PASSED")
    print("="*60)
