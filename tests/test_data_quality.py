"""Tests for stale-data detection and the data_quality block in the snapshot."""

from datetime import datetime, timedelta

from src.data_quality import compute_staleness, default_stale_threshold_seconds


def test_no_tick_yet_is_stale():
    age, is_stale = compute_staleness(None, threshold_seconds=10)
    assert age is None
    assert is_stale is True


def test_fresh_tick_is_not_stale():
    now = datetime(2026, 8, 23, 10, 30, 5)
    last_tick = datetime(2026, 8, 23, 10, 30, 0)
    age, is_stale = compute_staleness(last_tick, now=now, threshold_seconds=10)
    assert age == 5.0
    assert is_stale is False


def test_tick_exactly_at_threshold_is_not_stale():
    now = datetime(2026, 8, 23, 10, 30, 10)
    last_tick = datetime(2026, 8, 23, 10, 30, 0)
    age, is_stale = compute_staleness(last_tick, now=now, threshold_seconds=10)
    assert age == 10.0
    assert is_stale is False  # strictly greater-than triggers staleness


def test_tick_past_threshold_is_stale():
    now = datetime(2026, 8, 23, 10, 30, 11)
    last_tick = datetime(2026, 8, 23, 10, 30, 0)
    age, is_stale = compute_staleness(last_tick, now=now, threshold_seconds=10)
    assert age == 11.0
    assert is_stale is True


def test_default_threshold_uses_poll_interval_when_larger():
    assert default_stale_threshold_seconds(1) == 10.0  # 3*1=3 < floor of 10
    assert default_stale_threshold_seconds(5) == 15.0  # 3*5=15 > 10


def test_default_threshold_floor_is_10_seconds():
    assert default_stale_threshold_seconds(0.1) == 10.0


def test_snapshot_reports_data_quality_fields_end_to_end():
    """MarketEngine snapshots expose a data_quality block once ticks are flowing."""
    import time
    from src.engine import MarketEngine

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
        assert snapshots, "Expected at least one snapshot"
        dq = snapshots[-1]["data_quality"]
        assert dq["source"] == "mock"
        assert dq["tick_count"] > 0
        assert dq["last_tick_time"] is not None
        assert dq["last_tick_age_seconds"] is not None
        # Ticks are flowing every 0.1s and we just received one, so this should not be stale.
        assert dq["is_stale"] is False
        assert dq["stale_threshold_seconds"] is not None
        assert dq["persistence_enabled"] is False  # not enabled in this test cfg
    finally:
        engine.stop()


def test_snapshot_before_any_tick_reports_stale():
    """Before the worker thread has produced a tick, the snapshot must not claim freshness."""
    from src.engine import MarketEngine

    cfg = {
        "underlying": "NIFTY",
        "data_source": "mock",
        "poll_interval_seconds": 5,
        "candle_intervals": [1],
        "price_calculator": "mock",
    }
    engine = MarketEngine(cfg)
    snapshot = engine.get_snapshot()
    assert snapshot["data_quality"]["last_tick_time"] is None
    assert snapshot["data_quality"]["is_stale"] is True
