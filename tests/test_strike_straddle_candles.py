"""
Tests for StrikeStraddleCandleEngine (src/option_chain/strike_straddle_candles.py)
and its serializer — per-strike CE/PE/Straddle OHLC candles backing the ATM
Straddle Chart's candlestick view. Deterministic, hand-computed inputs,
following the repo's one-file-per-module convention.
"""

from datetime import datetime

from src.models import OptionChainSnapshot, OptionLeg
from src.option_chain.strike_straddle_candles import StrikeStraddleCandleEngine
from src.serializers import serialize_strike_candles


def make_chain(timestamp, legs):
    """legs: list of (strike, call_ltp, put_ltp)"""
    return OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=legs[0][0],
        expiry="28-Aug-2026",
        timestamp=timestamp,
        strikes=[OptionLeg(strike=s, call_ltp=c, put_ltp=p) for s, c, p in legs],
    )


def test_unseen_strike_returns_none():
    engine = StrikeStraddleCandleEngine(intervals_minutes=[1])
    assert engine.get_strike_builders(24500) is None
    assert engine.has_strike(24500) is False


def test_single_tick_seeds_ohlc_for_every_leg():
    engine = StrikeStraddleCandleEngine(intervals_minutes=[1])
    t0 = datetime(2026, 9, 3, 9, 15, 5)
    chain = make_chain(t0, [(24500, 100.0, 90.0)])

    engine.process(chain, t0)

    builders = engine.get_strike_builders(24500)
    assert builders is not None
    ce_bar = builders["ce"].active_candles[1]
    pe_bar = builders["pe"].active_candles[1]
    straddle_bar = builders["straddle"].active_candles[1]
    assert ce_bar.open == ce_bar.close == 100.0
    assert pe_bar.open == pe_bar.close == 90.0
    assert straddle_bar.open == straddle_bar.close == 190.0


def test_multiple_strikes_never_mix():
    """Core correctness guarantee: each strike's candles are built purely
    from that strike's own leg prices, independent of every other strike
    present in the same chain snapshot."""
    engine = StrikeStraddleCandleEngine(intervals_minutes=[1])
    t0 = datetime(2026, 9, 3, 9, 15, 0)
    chain = make_chain(t0, [(24500, 100.0, 90.0), (24600, 40.0, 150.0)])

    engine.process(chain, t0)

    low_strike = engine.get_strike_builders(24500)
    high_strike = engine.get_strike_builders(24600)
    assert low_strike["straddle"].active_candles[1].close == 190.0
    assert high_strike["straddle"].active_candles[1].close == 190.0  # coincidentally equal totals
    assert low_strike["ce"].active_candles[1].close == 100.0
    assert high_strike["ce"].active_candles[1].close == 40.0  # not contaminated by 24500's CE


def test_ohlc_accumulates_correctly_within_a_bucket():
    engine = StrikeStraddleCandleEngine(intervals_minutes=[1])
    t0 = datetime(2026, 9, 3, 9, 15, 5)

    engine.process(make_chain(t0, [(24500, 100.0, 90.0)]), t0)
    engine.process(make_chain(t0.replace(second=20), [(24500, 105.0, 85.0)]), t0.replace(second=20))
    engine.process(make_chain(t0.replace(second=40), [(24500, 98.0, 92.0)]), t0.replace(second=40))

    ce = engine.get_strike_builders(24500)["ce"].active_candles[1]
    assert ce.open == 100.0
    assert ce.high == 105.0
    assert ce.low == 98.0
    assert ce.close == 98.0
    assert ce.tick_count == 3


def test_time_rollover_finalizes_candle():
    engine = StrikeStraddleCandleEngine(intervals_minutes=[1])
    t0 = datetime(2026, 9, 3, 9, 15, 5)
    t1 = datetime(2026, 9, 3, 9, 16, 5)

    engine.process(make_chain(t0, [(24500, 100.0, 90.0)]), t0)
    engine.process(make_chain(t1, [(24500, 110.0, 80.0)]), t1)

    straddle_agg = engine.get_strike_builders(24500)["straddle"]
    assert len(straddle_agg.completed_candles[1]) == 1
    assert straddle_agg.completed_candles[1][0].close == 190.0
    assert straddle_agg.active_candles[1].open == 190.0  # 110 + 80


def test_strike_dropping_out_of_chain_freezes_but_is_still_queryable():
    engine = StrikeStraddleCandleEngine(intervals_minutes=[1])
    t0 = datetime(2026, 9, 3, 9, 15, 0)
    t1 = datetime(2026, 9, 3, 9, 15, 10)

    engine.process(make_chain(t0, [(24500, 100.0, 90.0), (24600, 40.0, 150.0)]), t0)
    # Next tick's chain window drifted — 24500 no longer present.
    engine.process(make_chain(t1, [(24600, 42.0, 148.0)]), t1)

    assert engine.has_strike(24500) is True
    frozen = engine.get_strike_builders(24500)["ce"].active_candles[1]
    assert frozen.close == 100.0  # unchanged since it stopped receiving ticks


def test_process_none_chain_is_a_noop():
    engine = StrikeStraddleCandleEngine(intervals_minutes=[1])
    engine.process(None, datetime(2026, 9, 3, 9, 15, 0))
    assert engine.known_strikes() == []


# -- serializer ---------------------------------------------------------------


def test_serialize_strike_candles_shape():
    engine = StrikeStraddleCandleEngine(intervals_minutes=[1, 5])
    t0 = datetime(2026, 9, 3, 9, 15, 0)
    engine.process(make_chain(t0, [(24500, 100.0, 90.0)]), t0)

    data = serialize_strike_candles(24500, engine.get_strike_builders(24500))

    assert data["strike"] == 24500
    assert set(data["by_interval"].keys()) == {"1", "5"}
    for interval_data in data["by_interval"].values():
        assert set(interval_data.keys()) == {"ce", "pe", "straddle"}
        assert len(interval_data["straddle"]) == 1
        bar = interval_data["straddle"][0]
        assert bar["open"] == bar["close"] == 190.0
        assert bar["is_complete"] is False  # still the active/forming bar
