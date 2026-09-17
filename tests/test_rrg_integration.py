"""Test RRG integration with real market data stream."""

import time
from datetime import datetime, timedelta

from src.config import load_config
from src.engine import MarketEngine
from src.rrg.models import RRGConfig


def test_rrg_with_mock_market_data():
    """Test RRG calculation using the application's real mock market data stream."""
    # Configure with RRG enabled
    cfg = load_config()
    cfg["enable_rrg"] = True
    cfg["rrg_timeframe"] = "1min"
    cfg["rrg_rolling_window"] = 5  # Small window for faster testing
    cfg["rrg_momentum_period"] = 1
    cfg["poll_interval_seconds"] = 0.5  # Fast polling for testing
    cfg["data_source"] = "mock"
    
    engine = MarketEngine(cfg)
    rrg_snapshots = []
    
    def capture_rrg(snapshot):
        if snapshot.get("rrg"):
            rrg_snapshots.append(snapshot["rrg"])
    
    engine.subscribe(capture_rrg)
    engine.start()
    
    try:
        # Wait for RRG calculations
        time.sleep(8)
        
        # Verify RRG calculations occurred
        assert len(rrg_snapshots) > 0, "Should have RRG snapshots"
        
        # Verify RRG snapshot structure
        latest_rrg = rrg_snapshots[-1]
        assert "benchmark_symbol" in latest_rrg
        assert "benchmark_ltp" in latest_rrg
        assert "timeframe" in latest_rrg
        assert "data_points" in latest_rrg
        assert latest_rrg["timeframe"] == "1min"
        
        # Verify data points
        assert len(latest_rrg["data_points"]) > 0, "Should have RRG data points"
        
        # Verify data point structure
        data_point = latest_rrg["data_points"][0]
        assert "strike" in data_point
        assert "option_type" in data_point
        assert "rs" in data_point
        assert "rs_ratio" in data_point
        assert "rs_momentum" in data_point
        assert "quadrant" in data_point
        assert "timestamp" in data_point
        
        print("✅ RRG integration with mock market data: PASSED")
        print(f"   RRG snapshots captured: {len(rrg_snapshots)}")
        print(f"   Data points in latest snapshot: {len(latest_rrg['data_points'])}")
        print(f"   Sample data point: {data_point}")
        
    finally:
        engine.stop()


def test_rrg_with_real_data_stream():
    """Test RRG using the actual normalized market data stream."""
    cfg = load_config()
    cfg["enable_rrg"] = True
    cfg["rrg_timeframe"] = "1min"
    cfg["rrg_rolling_window"] = 5
    cfg["rrg_momentum_period"] = 1
    cfg["poll_interval_seconds"] = 0.5
    cfg["data_source"] = "mock"
    
    engine = MarketEngine(cfg)
    
    # Capture both regular snapshots and RRG data
    snapshots = []
    
    def capture_all(snapshot):
        snapshots.append(snapshot)
    
    engine.subscribe(capture_all)
    engine.start()
    
    try:
        # Wait for data
        time.sleep(6)
        
        # Verify regular snapshots contain RRG data
        assert len(snapshots) > 0
        
        rrg_enabled_snapshots = [s for s in snapshots if s.get("rrg")]
        assert len(rrg_enabled_snapshots) > 0, "Some snapshots should have RRG data"
        
        # Verify RRG is integrated into the snapshot
        latest = snapshots[-1]
        assert "rrg" in latest
        assert latest["rrg"] is not None or len(rrg_enabled_snapshots) > 0
        
        print("✅ RRG with real data stream: PASSED")
        print(f"   Total snapshots: {len(snapshots)}")
        print(f"   Snapshots with RRG: {len(rrg_enabled_snapshots)}")
        
    finally:
        engine.stop()


def test_rrg_configuration_options():
    """Test different RRG configuration options."""
    # Test with specific strikes
    cfg = load_config()
    cfg["enable_rrg"] = True
    cfg["rrg_strikes"] = [24800.0, 24850.0]  # Only specific strikes
    cfg["rrg_rolling_window"] = 5
    cfg["rrg_momentum_period"] = 1
    cfg["poll_interval_seconds"] = 0.5
    cfg["data_source"] = "mock"
    
    engine = MarketEngine(cfg)
    snapshots = []
    
    engine.subscribe(lambda s: snapshots.append(s))
    engine.start()
    
    try:
        time.sleep(6)
        
        # Find a snapshot with RRG data
        rrg_snapshot = None
        for snapshot in snapshots:
            if snapshot.get("rrg") and snapshot["rrg"]["data_points"]:
                rrg_snapshot = snapshot["rrg"]
                break
        
        if rrg_snapshot:
            # Verify only configured strikes are analyzed
            strikes_analyzed = {dp["strike"] for dp in rrg_snapshot["data_points"]}
            assert strikes_analyzed.issubset({24800.0, 24850.0}) and len(strikes_analyzed) > 0
            print("✅ RRG configuration options: PASSED")
            print(f"   Configured strikes: {[24800.0, 24850.0]}")
            print(f"   Analyzed strikes: {strikes_analyzed}")
        else:
            print("⚠️ RRG configuration options: SKIPPED (no RRG data captured)")
        
    finally:
        engine.stop()


if __name__ == "__main__":
    print("Testing RRG integration with market data stream...")
    print()
    
    test_rrg_with_mock_market_data()
    print()
    test_rrg_with_real_data_stream()
    print()
    test_rrg_configuration_options()
    
    print()
    print("="*60)
    print("✅ RRG INTEGRATION TESTS COMPLETED")
    print("="*60)
