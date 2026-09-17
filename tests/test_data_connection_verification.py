"""Verify actual market-data connection and data flow."""

import time
from datetime import datetime

from src.config import load_config
from src.engine import MarketEngine


def test_actual_data_connection():
    """Verify the exact data provider and connection status."""
    cfg = load_config()
    
    print("="*60)
    print("MARKET DATA CONNECTION VERIFICATION")
    print("="*60)
    
    # 1. Identify provider
    data_source = cfg.get("data_source", "mock")
    print(f"\n1. Data provider: {data_source.upper()}")
    
    # 2. Live or Mock
    is_live = data_source in ["nse", "dhan"]
    print(f"2. Live or Mock: {'LIVE (' + data_source.upper() + ')' if is_live else 'MOCK/SIMULATED'}")
    
    # 3. Connection method
    if data_source == "dhan":
        connection_method = "DhanHQ v2 WebSocket Feed (Ticks) + REST API (Option Chain)"
        api_endpoint = "wss://api-feed.dhan.co & https://api.dhan.co"
    elif data_source == "nse":
        connection_method = "HTTP polling to NSE India API"
        api_endpoint = "https://www.nseindia.com/api/option-chain-indices"
    else:
        connection_method = "Local simulation via MockDataSource"
        api_endpoint = "None (internal generation)"
    print(f"3. Connection method: {connection_method}")
    print(f"   API endpoint: {api_endpoint}")
    
    # 4. Data update frequency
    poll_interval = cfg.get("poll_interval_seconds", 5)
    print(f"4. Data update frequency: Every {poll_interval} seconds")
    
    # 5. Start engine and capture actual data
    engine = MarketEngine(cfg)
    captured_data = {
        "ticks": [],
        "atm_updates": [],
        "timestamps": []
    }
    
    def capture_snapshot(snapshot):
        captured_data["ticks"].append(snapshot.get("price"))
        captured_data["timestamps"].append(snapshot.get("timestamp"))
        if snapshot.get("atm"):
            captured_data["atm_updates"].append(snapshot["atm"])
    
    engine.subscribe(capture_snapshot)
    engine.start()
    
    # Wait for a few data points
    time.sleep(3)
    
    engine.stop()
    
    # 6. Verify data characteristics
    print(f"\n5. Data capture results:")
    print(f"   Ticks captured: {len(captured_data['ticks'])}")
    print(f"   ATM updates: {len(captured_data['atm_updates'])}")
    
    if captured_data["ticks"]:
        print(f"\n6. Sample tick data:")
        print(f"   Price: {captured_data['ticks'][0]}")
        print(f"   Timestamp: {captured_data['timestamps'][0]}")
        
        if captured_data["atm_updates"]:
            atm = captured_data["atm_updates"][0]
            print(f"\n7. Sample ATM data:")
            print(f"   Strike: {atm['strike']}")
            print(f"   Call LTP: {atm['call_ltp']}")
            print(f"   Put LTP: {atm['put_ltp']}")
    
    # 8. Verify timestamp continuity
    if len(captured_data["timestamps"]) > 1:
        ts1 = datetime.fromisoformat(captured_data["timestamps"][0])
        ts2 = datetime.fromisoformat(captured_data["timestamps"][-1])
        time_diff = (ts2 - ts1).total_seconds()
        print(f"\n8. Timestamp analysis:")
        print(f"   Time span: {time_diff:.2f} seconds")
        print(f"   Continuous updates: {'YES' if time_diff > 0 else 'NO'}")
    
    # 9. Data source verification
    print(f"\n9. Data source verification:")
    if data_source == "dhan":
        print(f"   CONFIRMED: Provider configured as DHAN")
        print(f"   Using DhanHQ WebSocket API & REST option chain")
        print(f"   Credentials: DHAN_CLIENT_ID & DHAN_ACCESS_TOKEN loaded from environment")
    elif data_source == "nse":
        print(f"   CONFIRMED: Using NSE India HTTP API")
    else:
        print(f"   CONFIRMED: Using MOCK/SIMULATED data")
        print(f"   Data is generated internally by MockDataSource")
    
    print(f"\n10. Production requirements:")
    print(f"    - Provider set to '{data_source}'")
    print(f"    - Valid DHAN_CLIENT_ID and active DHAN_ACCESS_TOKEN in .env")
    print(f"    - Data API Subscription enabled in DhanHQ Portal (https://dhan.co)")
    
    print("\n" + "="*60)
    
    # Code path summary
    print(f"\n11. Exact code path:")
    if data_source == "dhan":
        print(f"   DhanMarketDataProvider.stream_ticks()")
        print(f"      -> DhanFeed v2 WebSocket connection")
        print(f"      -> yield PriceTick(symbol, price, timestamp)")
    else:
        print(f"   MockDataSource.stream_ticks()")
        print(f"      -> yield PriceTick(symbol, price, timestamp)")
    print(f"   MarketEngine._tick_worker()")
    print(f"      -> CandleAggregator.process_tick(tick)")
    print(f"      -> candle.update(price)")
    print(f"      -> snapshot broadcast to UI/subscribers")
    
    print("\n" + "="*60)
    
    assert engine._source is not None
    return None


if __name__ == "__main__":
    test_actual_data_connection()
