"""Tests for the simulation-only paper trading position engine (TP/SL, P&L, history)."""

import pytest
from datetime import datetime, timedelta

from src.models import OptionChainSnapshot, OptionLeg
from src.paper_trading import (
    EXIT_MANUAL,
    EXIT_STOP_LOSS,
    EXIT_TAKE_PROFIT,
    PaperTradeConfig,
    PaperTradingEngine,
)


def make_chain(strike: float, call_ltp: float, put_ltp: float) -> OptionChainSnapshot:
    return OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=strike,
        expiry="28-Aug-2026",
        timestamp=datetime(2026, 8, 23, 10, 0, 0),
        strikes=[OptionLeg(strike=strike, call_ltp=call_ltp, put_ltp=put_ltp)],
    )


def test_open_position_defaults_open_status():
    engine = PaperTradingEngine()
    pos = engine.open_position("CE", 25000, 50, 100.0, datetime(2026, 8, 23, 10, 0, 0))

    assert pos.status == "OPEN"
    assert pos.option_type == "CE"
    assert pos.strike == 25000
    assert pos.entry_price == 100.0
    assert pos.current_price == 100.0
    assert pos.pnl == 0.0
    assert pos.exit_reason is None
    assert engine.get_open_positions() == [pos]


def test_open_position_rejects_invalid_input():
    engine = PaperTradingEngine()
    with pytest.raises(ValueError):
        engine.open_position("XX", 25000, 50, 100.0, datetime.now())
    with pytest.raises(ValueError):
        engine.open_position("CE", 25000, 0, 100.0, datetime.now())
    with pytest.raises(ValueError):
        engine.open_position("CE", 25000, 50, 0, datetime.now())


def test_take_profit_auto_exit_at_default_10_percent():
    """Default TP=10%: a CE bought at 100 should auto-exit once premium >= 110."""
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("CE", 25000, 50, 100.0, t0)

    # Below TP threshold: stays open
    exits = engine.update(make_chain(25000, call_ltp=105.0, put_ltp=50.0), t0 + timedelta(seconds=1))
    assert exits == []
    assert pos.status == "OPEN"
    assert pos.pnl_percent == pytest.approx(5.0)

    # Crosses TP threshold (>= 10%): auto exits
    exits = engine.update(make_chain(25000, call_ltp=110.0, put_ltp=50.0), t0 + timedelta(seconds=2))
    assert len(exits) == 1
    exited = exits[0]
    assert exited.id == pos.id
    assert exited.status == "EXITED"
    assert exited.exit_reason == EXIT_TAKE_PROFIT
    assert exited.exit_price == 110.0
    assert exited.pnl == pytest.approx((110.0 - 100.0) * 50)
    assert exited.pnl_percent == pytest.approx(10.0)

    assert engine.get_open_positions() == []
    assert engine.get_history() == [exited]


def test_stop_loss_auto_exit_at_default_5_percent():
    """Default SL=5%: a PE bought at 100 should auto-exit once premium <= 95."""
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("PE", 25000, 50, 100.0, t0)

    exits = engine.update(make_chain(25000, call_ltp=50.0, put_ltp=97.0), t0 + timedelta(seconds=1))
    assert exits == []
    assert pos.status == "OPEN"

    exits = engine.update(make_chain(25000, call_ltp=50.0, put_ltp=95.0), t0 + timedelta(seconds=2))
    assert len(exits) == 1
    exited = exits[0]
    assert exited.exit_reason == EXIT_STOP_LOSS
    assert exited.exit_price == 95.0
    assert exited.pnl == pytest.approx((95.0 - 100.0) * 50)
    assert exited.pnl_percent == pytest.approx(-5.0)
    assert engine.get_open_positions() == []


def test_position_stays_open_between_thresholds():
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    engine.open_position("CE", 25000, 50, 100.0, t0)

    for premium in (98.0, 102.0, 96.0, 108.0):
        exits = engine.update(make_chain(25000, call_ltp=premium, put_ltp=50.0), t0)
        assert exits == []
    assert len(engine.get_open_positions()) == 1


def test_configurable_tp_sl_thresholds_are_respected():
    """TP/SL must be configurable, not hardcoded — verify a non-default config works."""
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=20.0, stop_loss_percent=2.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    engine.open_position("CE", 25000, 50, 100.0, t0)

    # Would have hit default 10% TP, but configured TP is 20% -> stays open
    exits = engine.update(make_chain(25000, call_ltp=115.0, put_ltp=50.0), t0)
    assert exits == []

    # Crosses the configured 20% TP
    exits = engine.update(make_chain(25000, call_ltp=120.0, put_ltp=50.0), t0)
    assert len(exits) == 1
    assert exits[0].exit_reason == EXIT_TAKE_PROFIT


def test_set_config_updates_thresholds_and_validates():
    engine = PaperTradingEngine()
    cfg = engine.set_config(take_profit_percent=15.0, stop_loss_percent=7.5)
    assert cfg.take_profit_percent == 15.0
    assert cfg.stop_loss_percent == 7.5
    assert engine.get_config().take_profit_percent == 15.0

    with pytest.raises(ValueError):
        engine.set_config(take_profit_percent=0)
    with pytest.raises(ValueError):
        engine.set_config(stop_loss_percent=-1)


def test_manual_close_sets_manual_reason_and_moves_to_history():
    engine = PaperTradingEngine()
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("CE", 25000, 50, 100.0, t0)

    engine.update(make_chain(25000, call_ltp=103.0, put_ltp=50.0), t0)
    closed = engine.close_position(pos.id, 103.0, t0 + timedelta(minutes=1), reason=EXIT_MANUAL)

    assert closed is not None
    assert closed.status == "EXITED"
    assert closed.exit_reason == EXIT_MANUAL
    assert engine.get_open_positions() == []
    assert engine.get_history() == [closed]


def test_close_unknown_position_returns_none():
    engine = PaperTradingEngine()
    assert engine.close_position("does-not-exist", 100.0, datetime.now()) is None


def test_update_ignores_strike_missing_from_chain():
    """A position whose strike has rolled out of the visible chain window holds its last price."""
    engine = PaperTradingEngine()
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("CE", 25000, 50, 100.0, t0)

    exits = engine.update(make_chain(25200, call_ltp=999.0, put_ltp=1.0), t0)
    assert exits == []
    assert pos.current_price == 100.0  # unchanged


def test_sell_side_defaults_to_buy_when_omitted():
    """Backward compatibility: omitting `side` must keep behaving as BUY."""
    engine = PaperTradingEngine()
    pos = engine.open_position("CE", 25000, 50, 100.0, datetime(2026, 8, 23, 10, 0, 0))
    assert pos.side == "BUY"


def test_sell_side_rejects_invalid_value():
    engine = PaperTradingEngine()
    with pytest.raises(ValueError):
        engine.open_position("CE", 25000, 50, 100.0, datetime.now(), side="SHORT")


def test_sell_side_pnl_is_mirrored_from_buy():
    """SELL (short/write) profits as premium falls — the mirror image of BUY."""
    # Wide TP/SL so this pnl-sign check isn't cut short by an auto-exit —
    # threshold behavior itself is covered by the dedicated tests below.
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=50.0, stop_loss_percent=50.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("PE", 25000, 50, 100.0, t0, side="SELL")

    # Premium falls to 90 (-10%): a BUY would show pnl_percent -10%, a SELL +10%.
    engine.update(make_chain(25000, call_ltp=50.0, put_ltp=90.0), t0 + timedelta(seconds=1))
    assert pos.pnl_percent == pytest.approx(10.0)
    assert pos.pnl == pytest.approx((100.0 - 90.0) * 50)

    # Premium rises to 105 (+5% for the underlying move): SELL shows -5%.
    engine.update(make_chain(25000, call_ltp=50.0, put_ltp=105.0), t0 + timedelta(seconds=2))
    assert pos.pnl_percent == pytest.approx(-5.0)
    assert pos.pnl == pytest.approx((100.0 - 105.0) * 50)


def test_sell_side_take_profit_triggers_on_price_falling():
    """SELL TP is hit when the premium falls (mirror of BUY's rising-price TP)."""
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("CE", 25000, 50, 100.0, t0, side="SELL")

    exits = engine.update(make_chain(25000, call_ltp=91.0, put_ltp=50.0), t0 + timedelta(seconds=1))
    assert exits == []  # +9%, below the 10% TP threshold

    exits = engine.update(make_chain(25000, call_ltp=90.0, put_ltp=50.0), t0 + timedelta(seconds=2))
    assert len(exits) == 1
    assert exits[0].exit_reason == EXIT_TAKE_PROFIT
    assert exits[0].pnl_percent == pytest.approx(10.0)


def test_sell_side_stop_loss_triggers_on_price_rising():
    """SELL SL is hit when the premium rises against the short (mirror of BUY's falling-price SL)."""
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    pos = engine.open_position("PE", 25000, 50, 100.0, t0, side="SELL")

    exits = engine.update(make_chain(25000, call_ltp=50.0, put_ltp=104.0), t0 + timedelta(seconds=1))
    assert exits == []  # -4%, above the -5% SL threshold

    exits = engine.update(make_chain(25000, call_ltp=50.0, put_ltp=105.0), t0 + timedelta(seconds=2))
    assert len(exits) == 1
    assert exits[0].exit_reason == EXIT_STOP_LOSS
    assert exits[0].pnl_percent == pytest.approx(-5.0)


def test_sell_side_take_profit_and_stop_loss_prices_are_mirrored_in_to_dict():
    engine = PaperTradingEngine(PaperTradeConfig(take_profit_percent=10.0, stop_loss_percent=5.0))
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    buy_pos = engine.open_position("CE", 25000, 50, 100.0, t0, side="BUY")
    sell_pos = engine.open_position("PE", 25000, 50, 100.0, t0, side="SELL")

    buy_dict = buy_pos.to_dict()
    sell_dict = sell_pos.to_dict()

    assert buy_dict["side"] == "BUY"
    assert buy_dict["take_profit_price"] == pytest.approx(110.0)
    assert buy_dict["stop_loss_price"] == pytest.approx(95.0)

    assert sell_dict["side"] == "SELL"
    assert sell_dict["take_profit_price"] == pytest.approx(90.0)  # falls to profit
    assert sell_dict["stop_loss_price"] == pytest.approx(105.0)  # rises to loss


def test_to_state_dict_marks_everything_simulated():
    engine = PaperTradingEngine()
    t0 = datetime(2026, 8, 23, 10, 0, 0)
    engine.open_position("CE", 25000, 50, 100.0, t0)
    state = engine.to_state_dict()

    assert state["simulated"] is True
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["simulated"] is True
    assert state["config"]["take_profit_percent"] == 10.0
    assert state["config"]["stop_loss_percent"] == 5.0
