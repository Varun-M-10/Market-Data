"""
Tests for the trading-terminal dashboard upgrade: paper-trading stats/TP-SL
distance, per-row option chain CE+PE, candle price basis, and deterministic
Replay/Test Mode. Existing pipeline behavior (candles, Delta ATM, CE+PE,
TP/SL) is already covered by test_deterministic_requirements.py and friends —
these tests only exercise what's new.
"""

from datetime import datetime, timedelta

from src.candles.aggregator import CandleAggregator
from src.data_sources.replay import REPLAY_SEQUENCES, ReplayDataSource
from src.models import OptionChainSnapshot, OptionLeg, PriceTick
from src.paper_trading import PaperTradeConfig, PaperTradingEngine
from src.serializers import serialize_chain


def make_chain(strike: float, call_ltp: float, put_ltp: float) -> OptionChainSnapshot:
    return OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=strike,
        expiry="28-Aug-2026",
        timestamp=datetime(2026, 8, 23, 10, 0, 0),
        strikes=[OptionLeg(strike=strike, call_ltp=call_ltp, put_ltp=put_ltp)],
    )


# -- Paper trading: stats -----------------------------------------------------


def test_stats_empty_book():
    engine = PaperTradingEngine()
    stats = engine.to_state_dict()["stats"]
    assert stats == {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_percent": 0.0,
        "total_pnl": 0.0,
        "average_win": 0.0,
        "average_loss": 0.0,
        "max_drawdown": 0.0,
    }


def test_stats_win_rate_and_averages():
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)

    # Winning trade: CE 100 -> 120 (+20%, hits TP)
    pos1 = engine.open_position("CE", 25000, 50, 100.0, t0)
    engine.update(make_chain(25000, 120.0, 50.0), t0 + timedelta(seconds=1))

    # Losing trade: PE 100 -> 90 (-10%, hits SL)
    pos2 = engine.open_position("PE", 25000, 50, 100.0, t0)
    engine.update(make_chain(25000, 50.0, 90.0), t0 + timedelta(seconds=2))

    stats = engine.to_state_dict()["stats"]
    assert stats["total_trades"] == 2
    assert stats["wins"] == 1
    assert stats["losses"] == 1
    assert stats["win_rate_percent"] == 50.0
    # pos1: (120-100)*50 = 1000; pos2: (90-100)*50 = -500
    assert stats["total_pnl"] == 500.0
    assert stats["average_win"] == 1000.0
    assert stats["average_loss"] == -500.0
    # Equity curve: +1000 (peak), then -500 -> cumulative 500 -> drawdown 500 off the peak.
    assert stats["max_drawdown"] == 500.0


def test_stats_max_drawdown_tracks_peak_to_trough():
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=50.0, stop_loss_percent=50.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)

    # Close trades manually (never crossing TP/SL) in a specific order to
    # produce a known equity curve: +1000, -1500, +200
    p1 = engine.open_position("CE", 25000, 50, 100.0, t0)
    engine.close_position(p1.id, 120.0, t0, reason="MANUAL")  # +1000

    p2 = engine.open_position("CE", 25000, 50, 100.0, t0)
    engine.close_position(p2.id, 70.0, t0, reason="MANUAL")  # -1500

    p3 = engine.open_position("CE", 25000, 50, 100.0, t0)
    engine.close_position(p3.id, 104.0, t0, reason="MANUAL")  # +200

    stats = engine.to_state_dict()["stats"]
    # Equity curve: 1000, -500, -300. Peak=1000, trough=-500 -> drawdown 1500.
    assert stats["max_drawdown"] == 1500.0
    assert stats["total_pnl"] == -300.0


# -- Paper trading: TP/SL distance & price levels -----------------------------


def test_position_exposes_tp_sl_price_and_distance():
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("CE", 25000, 50, 100.0, t0)
    engine.update(make_chain(25000, 104.0, 50.0), t0 + timedelta(seconds=1))  # +4%

    d = engine.get_open_positions()[0].to_dict()
    assert d["take_profit_price"] == 110.0
    assert d["stop_loss_price"] == 95.0
    assert d["distance_to_tp_percent"] == 6.0  # 10 - 4
    assert d["distance_to_sl_percent"] == 9.0  # 4 + 5


def test_exited_position_has_no_distance_fields():
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("CE", 25000, 50, 100.0, t0)
    engine.close_position(pos.id, 105.0, t0, reason="MANUAL")
    closed = engine.get_history()[0].to_dict()
    assert closed["distance_to_tp_percent"] is None
    assert closed["distance_to_sl_percent"] is None


# -- Option chain: CE+PE per row ----------------------------------------------


def test_serialize_chain_includes_combined_value_per_row():
    chain = make_chain(25000, 150.0, 160.0)
    serialized = serialize_chain(chain, atm_strike=25000)
    assert serialized["strikes"][0]["combined_value"] == 310.0


# -- Candle price basis (aggregator reuse, no new formula) -------------------


def test_candle_aggregator_accepts_combined_value_as_price_basis():
    """
    The engine feeds the aggregator either the underlying spot or the ATM
    Combined Value depending on `candle_price_basis` — the aggregator itself
    is untouched; this just confirms a synthetic tick with a different price
    still builds a correct OHLC candle.
    """
    from zoneinfo import ZoneInfo

    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1], timezone="Asia/Kolkata")
    tz = ZoneInfo("Asia/Kolkata")
    base = datetime(2026, 8, 23, 9, 15, 10, tzinfo=tz)

    combined_values = [300.0, 320.0, 290.0, 310.0]
    for i, val in enumerate(combined_values):
        tick = PriceTick(symbol="NIFTY", price=val, timestamp=base + timedelta(seconds=i * 10))
        agg.process_tick(tick)

    active = agg.snapshot_active()[1]
    assert active.open == 300.0
    assert active.high == 320.0
    assert active.low == 290.0
    assert active.close == 310.0


# -- Deterministic Replay/Test Mode -------------------------------------------


def test_replay_sequence_is_deterministic_across_instances():
    src1 = ReplayDataSource(sequence="trend_up", speed=100.0, seed=7)
    src2 = ReplayDataSource(sequence="trend_up", speed=100.0, seed=7)

    spots1 = [src1._advance() for _ in range(10)]
    spots2 = [src2._advance() for _ in range(10)]
    assert spots1 == spots2

    chain1 = src1.fetch_option_chain()
    chain2 = src2.fetch_option_chain()
    assert chain1 == chain2  # same seeded RNG -> identical OI/volume/greeks too


def test_replay_sequence_loops():
    src = ReplayDataSource(sequence="choppy_range", speed=100.0, seed=1)
    n = len(REPLAY_SEQUENCES["choppy_range"])
    first_pass = [src._advance() for _ in range(n)]
    second_pass = [src._advance() for _ in range(n)]
    assert first_pass == second_pass


def test_replay_unknown_sequence_falls_back_to_default():
    src = ReplayDataSource(sequence="does_not_exist")
    assert src.sequence_name == "trend_up"


def test_replay_speed_is_clamped():
    fast = ReplayDataSource(poll_interval=1.0, speed=1000.0)
    slow = ReplayDataSource(poll_interval=1.0, speed=0.001)
    assert fast.speed == 20.0
    assert slow.speed == 0.1
