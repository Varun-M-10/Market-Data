"""
Deterministic tests for the ₹ (absolute P&L) Profit Target / Loss Limit
auto-exit, the BUY/SELL P&L formulas, turnover, and the total P&L summary.

Percent-based TP/SL is disabled in these tests (set far out of reach) so the
₹ trigger is the only thing that can fire — isolating exactly what this
feature adds. Existing percent-based behavior is covered separately in
tests/test_paper_trading.py and is untouched by this file.
"""

from datetime import datetime, timedelta

import pytest

from src.models import OptionChainSnapshot, OptionLeg
from src.paper_trading import (
    EXIT_STOP_LOSS,
    EXIT_TAKE_PROFIT,
    PaperTradeConfig,
    PaperTradingEngine,
)

T0 = datetime(2026, 9, 5, 10, 0, 0)


def make_chain(strike: float, call_ltp: float, put_ltp: float) -> OptionChainSnapshot:
    return OptionChainSnapshot(
        underlying="NIFTY",
        underlying_ltp=strike,
        expiry="10-Sep-2026",
        timestamp=T0,
        strikes=[OptionLeg(strike=strike, call_ltp=call_ltp, put_ltp=put_ltp)],
    )


def far_out_percent_config(**kwargs) -> PaperTradeConfig:
    """Percent thresholds so wide they can never fire in these tests."""
    return PaperTradeConfig(take_profit_percent=10_000.0, stop_loss_percent=10_000.0, **kwargs)


# --------------------------------------------------------------------------
# BUY profit: entry ₹10, qty 1, Profit Target ₹10 -> exit once price hits ₹20.
# --------------------------------------------------------------------------


def test_buy_profit_target_amount_exits_at_exact_target():
    engine = PaperTradingEngine(far_out_percent_config(take_profit_amount=10.0, stop_loss_amount=5.0))
    pos = engine.open_position("CE", 25000, 1, 10.0, T0, side="BUY")

    # Below target (+₹9): stays open.
    exits = engine.update(make_chain(25000, call_ltp=19.0, put_ltp=1.0), T0 + timedelta(seconds=1))
    assert exits == []
    assert pos.status == "OPEN"
    assert pos.pnl == pytest.approx(9.0)

    # Hits ₹20 -> P&L = (20-10)*1 = +₹10 = target -> auto-exit.
    exits = engine.update(make_chain(25000, call_ltp=20.0, put_ltp=1.0), T0 + timedelta(seconds=2))
    assert len(exits) == 1
    exited = exits[0]
    assert exited.status == "EXITED"
    assert exited.exit_reason == EXIT_TAKE_PROFIT
    assert exited.exit_price == 20.0
    assert exited.exit_time == T0 + timedelta(seconds=2)
    assert exited.pnl == pytest.approx(10.0)
    assert engine.get_open_positions() == []
    assert engine.get_history() == [exited]


def test_buy_profit_pnl_formula_is_current_minus_entry_times_quantity():
    engine = PaperTradingEngine(far_out_percent_config())
    pos = engine.open_position("CE", 25000, 3, 10.0, T0, side="BUY")
    engine.update(make_chain(25000, call_ltp=14.0, put_ltp=1.0), T0)
    assert pos.pnl == pytest.approx((14.0 - 10.0) * 3)


# --------------------------------------------------------------------------
# BUY loss: entry ₹10, qty 1, Loss Limit ₹5 -> exit once price falls to ₹5.
# --------------------------------------------------------------------------


def test_buy_loss_limit_amount_exits_at_exact_limit():
    engine = PaperTradingEngine(far_out_percent_config(take_profit_amount=10.0, stop_loss_amount=5.0))
    pos = engine.open_position("CE", 25000, 1, 10.0, T0, side="BUY")

    # -₹4: stays open.
    exits = engine.update(make_chain(25000, call_ltp=6.0, put_ltp=1.0), T0 + timedelta(seconds=1))
    assert exits == []
    assert pos.status == "OPEN"

    # Falls to ₹5 -> P&L = (5-10)*1 = -₹5 = -limit -> auto-exit.
    exits = engine.update(make_chain(25000, call_ltp=5.0, put_ltp=1.0), T0 + timedelta(seconds=2))
    assert len(exits) == 1
    exited = exits[0]
    assert exited.exit_reason == EXIT_STOP_LOSS
    assert exited.exit_price == 5.0
    assert exited.pnl == pytest.approx(-5.0)
    assert engine.get_open_positions() == []


# --------------------------------------------------------------------------
# SELL profit: short at ₹10, qty 1, Profit Target ₹10 -> exit once price
# falls to ₹0... use a Profit Target ₹5 -> exit once price falls to ₹5, since
# a SELL profits as price falls (mirror of BUY).
# --------------------------------------------------------------------------


def test_sell_profit_target_amount_exits_when_price_falls():
    engine = PaperTradingEngine(far_out_percent_config(take_profit_amount=5.0, stop_loss_amount=5.0))
    pos = engine.open_position("PE", 25000, 1, 10.0, T0, side="SELL")

    # Price falls to ₹6: P&L = (10-6)*1 = +₹4, below the ₹5 target -> stays open.
    exits = engine.update(make_chain(25000, call_ltp=1.0, put_ltp=6.0), T0 + timedelta(seconds=1))
    assert exits == []
    assert pos.pnl == pytest.approx(4.0)

    # Price falls to ₹5: P&L = (10-5)*1 = +₹5 = target -> auto-exit.
    exits = engine.update(make_chain(25000, call_ltp=1.0, put_ltp=5.0), T0 + timedelta(seconds=2))
    assert len(exits) == 1
    exited = exits[0]
    assert exited.exit_reason == EXIT_TAKE_PROFIT
    assert exited.exit_price == 5.0
    assert exited.pnl == pytest.approx(5.0)


# --------------------------------------------------------------------------
# SELL loss: short at ₹10, qty 1, Loss Limit ₹5 -> exit once price rises to ₹15.
# --------------------------------------------------------------------------


def test_sell_loss_limit_amount_exits_when_price_rises():
    engine = PaperTradingEngine(far_out_percent_config(take_profit_amount=100.0, stop_loss_amount=5.0))
    pos = engine.open_position("PE", 25000, 1, 10.0, T0, side="SELL")

    # Price rises to ₹14: P&L = (10-14)*1 = -₹4, above the -₹5 limit -> stays open.
    exits = engine.update(make_chain(25000, call_ltp=1.0, put_ltp=14.0), T0 + timedelta(seconds=1))
    assert exits == []
    assert pos.pnl == pytest.approx(-4.0)

    # Price rises to ₹15: P&L = (10-15)*1 = -₹5 = -limit -> auto-exit.
    exits = engine.update(make_chain(25000, call_ltp=1.0, put_ltp=15.0), T0 + timedelta(seconds=2))
    assert len(exits) == 1
    exited = exits[0]
    assert exited.exit_reason == EXIT_STOP_LOSS
    assert exited.exit_price == 15.0
    assert exited.pnl == pytest.approx(-5.0)


def test_sell_pnl_formula_is_entry_minus_current_times_quantity():
    engine = PaperTradingEngine(far_out_percent_config())
    pos = engine.open_position("PE", 25000, 4, 10.0, T0, side="SELL")
    engine.update(make_chain(25000, call_ltp=1.0, put_ltp=7.0), T0)
    assert pos.pnl == pytest.approx((10.0 - 7.0) * 4)


# --------------------------------------------------------------------------
# ₹ target is opt-in and doesn't affect positions where it's unset.
# --------------------------------------------------------------------------


def test_amount_targets_unset_by_default_do_not_trigger():
    """Backward compatibility: no take_profit_amount/stop_loss_amount
    configured -> only the (far-out) percent thresholds are checked."""
    engine = PaperTradingEngine(far_out_percent_config())  # amounts default to None
    pos = engine.open_position("CE", 25000, 1, 10.0, T0, side="BUY")
    exits = engine.update(make_chain(25000, call_ltp=1000.0, put_ltp=1.0), T0)
    assert exits == []
    assert pos.pnl == pytest.approx(990.0)


def test_config_requires_positive_amounts():
    engine = PaperTradingEngine()
    with pytest.raises(ValueError):
        engine.set_config(take_profit_amount=0)
    with pytest.raises(ValueError):
        engine.set_config(stop_loss_amount=-1)


def test_set_config_amount_targets_are_read_back():
    engine = PaperTradingEngine()
    cfg = engine.set_config(take_profit_amount=500.0, stop_loss_amount=200.0)
    assert cfg.take_profit_amount == 500.0
    assert cfg.stop_loss_amount == 200.0
    assert engine.get_config().take_profit_amount == 500.0


def test_amount_targets_captured_per_position_survive_later_config_change():
    """Changing config after a position is open must not retroactively move
    that position's own thresholds (it keeps what it opened with)."""
    engine = PaperTradingEngine(far_out_percent_config(take_profit_amount=10.0))
    pos = engine.open_position("CE", 25000, 1, 10.0, T0, side="BUY")

    engine.set_config(take_profit_amount=1000.0)  # would never fire in this test

    # Still exits at the ORIGINAL ₹10 target captured when this position opened.
    exits = engine.update(make_chain(25000, call_ltp=20.0, put_ltp=1.0), T0 + timedelta(seconds=1))
    assert len(exits) == 1
    assert exits[0].id == pos.id
    assert exits[0].exit_reason == EXIT_TAKE_PROFIT


# --------------------------------------------------------------------------
# Turnover, position value, and the total P&L summary (to_state_dict).
# --------------------------------------------------------------------------


def test_turnover_is_separate_from_and_never_equal_to_profit():
    engine = PaperTradingEngine(far_out_percent_config())
    engine.open_position("CE", 25000, 2, 10.0, T0, side="BUY")   # buy value 20
    engine.open_position("PE", 25000, 3, 10.0, T0, side="SELL")  # sell value 30
    engine.update(make_chain(25000, call_ltp=12.0, put_ltp=8.0), T0)

    summary = engine.to_state_dict()["pnl_summary"]
    assert summary["buy_turnover"] == pytest.approx(20.0)
    assert summary["sell_turnover"] == pytest.approx(30.0)
    assert summary["total_turnover"] == pytest.approx(50.0)
    # Unrealized P&L: BUY (12-10)*2=+4, SELL (10-8)*3=+6 -> total +10, not 50.
    assert summary["unrealized_pnl"] == pytest.approx(10.0)
    assert summary["total_pnl"] == pytest.approx(10.0)
    assert summary["total_turnover"] != summary["total_pnl"]


def test_pnl_summary_splits_realized_and_unrealized_and_totals_them():
    engine = PaperTradingEngine(far_out_percent_config(take_profit_amount=10.0))
    # Position 1 will auto-exit at +₹10 (realized).
    engine.open_position("CE", 25000, 1, 10.0, T0, side="BUY")
    engine.update(make_chain(25000, call_ltp=20.0, put_ltp=1.0), T0 + timedelta(seconds=1))
    # Position 2 stays open at +₹3 (unrealized).
    engine.open_position("PE", 25100, 1, 10.0, T0, side="BUY")
    engine.update(make_chain(25100, call_ltp=1.0, put_ltp=13.0), T0 + timedelta(seconds=2))

    summary = engine.to_state_dict()["pnl_summary"]
    assert summary["realized_pnl"] == pytest.approx(10.0)
    assert summary["unrealized_pnl"] == pytest.approx(3.0)
    assert summary["total_pnl"] == pytest.approx(13.0)
    assert summary["open_position_count"] == 1


def test_position_value_and_buy_sell_value_fields_in_to_dict():
    engine = PaperTradingEngine(far_out_percent_config())
    pos = engine.open_position("CE", 25000, 5, 10.0, T0, side="BUY")
    engine.update(make_chain(25000, call_ltp=12.0, put_ltp=1.0), T0)

    d = pos.to_dict()
    assert d["position_value"] == pytest.approx(60.0)  # 5 * 12
    assert d["buy_value"] == pytest.approx(50.0)  # 5 * entry 10
    assert d["sell_value"] == pytest.approx(0.0)
    assert d["unrealized_pnl"] == pytest.approx(10.0)
    assert d["realized_pnl"] is None


def test_realized_pnl_populated_and_unrealized_cleared_once_closed():
    engine = PaperTradingEngine(far_out_percent_config(take_profit_amount=10.0))
    engine.open_position("CE", 25000, 1, 10.0, T0, side="BUY")
    engine.update(make_chain(25000, call_ltp=20.0, put_ltp=1.0), T0)

    closed = engine.get_history()[0].to_dict()
    assert closed["status"] == "EXITED"
    assert closed["realized_pnl"] == pytest.approx(10.0)
    assert closed["unrealized_pnl"] is None
    assert closed["exit_reason"] == "TAKE_PROFIT"
