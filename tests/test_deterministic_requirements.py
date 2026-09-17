"""
Deterministic acceptance tests, one per requested requirement:
  1. Delta-based ATM
  2. CE+PE (Combined Value) calculation
  3. 1m/5m/15m OHLC
  4. TP exit
  5. SL exit
  6. Candle rollover

Each test is self-contained and uses fixed, hand-computed inputs (no randomness,
no live data) so results are reproducible run-to-run. Deeper edge-case coverage
for each area lives in its dedicated test file (test_atm_delta_selection.py,
test_price_calculator.py, test_candle_calculation.py, test_paper_trading.py);
this file is the direct, at-a-glance checklist.
"""

from datetime import datetime, timedelta

from src.candles.aggregator import CandleAggregator
from src.models import OptionChainSnapshot, OptionLeg, PriceTick
from src.option_chain import find_atm_strike_delta
from src.paper_trading import EXIT_STOP_LOSS, EXIT_TAKE_PROFIT, PaperTradeConfig, PaperTradingEngine
from src.price_calculator import get_calculator


def test_requirement_1_delta_based_atm():
    """ATM must be selected by Call/Put Delta closest to the configured threshold, not price."""
    chain = OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=25000.0,  # price-based ATM would be exactly this strike
        expiry="28-Aug-2026",
        timestamp=datetime(2026, 8, 23, 10, 0, 0),
        strikes=[
            OptionLeg(strike=25000.0, call_ltp=180.0, put_ltp=130.0, call_delta=0.63, put_delta=-0.37),
            OptionLeg(strike=25050.0, call_ltp=150.0, put_ltp=160.0, call_delta=0.50, put_delta=-0.50),
        ],
    )

    atm = find_atm_strike_delta(chain, delta_threshold=0.5)

    assert atm.strike == 25050.0  # NOT 25000 (the price-based strike)
    assert atm.method == "delta"
    assert atm.call_delta == 0.50
    assert atm.delta_threshold == 0.5
    assert atm.price_based_strike == 25000.0  # comparison value preserved


def test_requirement_2_ce_plus_pe_combined_value():
    """Combined Value = ATM Call LTP + ATM Put LTP, isolated behind the calculator."""
    from src.models import ATMResult

    atm = ATMResult(
        strike=25050.0,
        call_ltp=150.0,
        put_ltp=160.0,
        straddle_premium=310.0,
        underlying_ltp=25000.0,
        distance_from_spot=50.0,
    )
    calc = get_calculator("mock")
    result = calc.calculate(atm)

    assert result["combined_value"] == 310.0  # 150 + 160
    assert result["straddle_premium"] == 310.0
    assert result["calculation_method"] == "mock_simple_addition"


def test_requirement_3_ohlc_1m_5m_15m():
    """Open=first tick, High=max, Low=min, Close=latest tick — for all three intervals."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1, 5, 15])
    base = datetime(2026, 8, 23, 10, 30, 0)
    prices = [25000.0, 25080.0, 24950.0, 25010.0, 24990.0]

    for i, price in enumerate(prices):
        agg.process_tick(PriceTick(symbol="NIFTY", price=price, timestamp=base + timedelta(seconds=i * 5)))

    for interval in (1, 5, 15):
        candle = agg.active_candles[interval]
        assert candle.open == 25000.0
        assert candle.high == 25080.0
        assert candle.low == 24950.0
        assert candle.close == 24990.0
        assert candle.tick_count == 5


def test_requirement_4_take_profit_exit():
    """A CE bought at 100 with TP=10% auto-exits the instant premium >= 110."""
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("CE", 25000.0, 50, 100.0, t0)

    chain = lambda premium: OptionChainSnapshot(
        underlying="NIFTY", underlying_ltp=25000.0, expiry="28-Aug-2026",
        timestamp=t0, strikes=[OptionLeg(strike=25000.0, call_ltp=premium, put_ltp=50.0)],
    )

    assert engine.update(chain(109.9), t0) == []  # below threshold: stays open
    exits = engine.update(chain(110.0), t0)  # at threshold: exits

    assert len(exits) == 1
    assert exits[0].id == pos.id
    assert exits[0].exit_reason == EXIT_TAKE_PROFIT
    assert exits[0].status == "EXITED"
    assert exits[0].pnl == (110.0 - 100.0) * 50


def test_requirement_5_stop_loss_exit():
    """A PE bought at 100 with SL=5% auto-exits the instant premium <= 95."""
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("PE", 25000.0, 50, 100.0, t0)

    chain = lambda premium: OptionChainSnapshot(
        underlying="NIFTY", underlying_ltp=25000.0, expiry="28-Aug-2026",
        timestamp=t0, strikes=[OptionLeg(strike=25000.0, call_ltp=50.0, put_ltp=premium)],
    )

    assert engine.update(chain(95.1), t0) == []  # above -5%: stays open
    exits = engine.update(chain(95.0), t0)  # at -5%: exits

    assert len(exits) == 1
    assert exits[0].id == pos.id
    assert exits[0].exit_reason == EXIT_STOP_LOSS
    assert exits[0].status == "EXITED"
    assert exits[0].pnl == (95.0 - 100.0) * 50


def test_requirement_6_candle_rollover():
    """Crossing an interval boundary finalizes the current candle and opens a fresh one."""
    agg = CandleAggregator(symbol="NIFTY", intervals_minutes=[1])
    base = datetime(2026, 8, 23, 10, 30, 0)

    agg.process_tick(PriceTick(symbol="NIFTY", price=25000.0, timestamp=base))
    agg.process_tick(PriceTick(symbol="NIFTY", price=25040.0, timestamp=base + timedelta(seconds=30)))
    completed = agg.process_tick(
        PriceTick(symbol="NIFTY", price=25010.0, timestamp=base + timedelta(minutes=1))
    )

    assert len(completed) == 1
    closed = completed[0]
    assert closed.is_complete is True
    assert closed.open == 25000.0
    assert closed.high == 25040.0
    assert closed.close == 25040.0  # last tick before rollover

    new_candle = agg.active_candles[1]
    assert new_candle.open == 25010.0  # first tick of the new bucket
    assert new_candle.tick_count == 1
    assert new_candle.is_complete is False
    assert agg.completed_candles[1] == [closed]
