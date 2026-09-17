from __future__ import annotations

from datetime import datetime

from src.candles import CandleAggregator
from src.models import ATMResult, Candle, OptionChainSnapshot, PriceTick


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _ts(value: datetime) -> int:
    return int(value.timestamp())


def serialize_candle(candle: Candle, complete: bool | None = None) -> dict:
    return {
        "symbol": candle.symbol,
        "interval_minutes": candle.interval_minutes,
        "open_time": _dt(candle.open_time),
        "close_time": _dt(candle.close_time),
        "time": _ts(candle.open_time),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "tick_count": candle.tick_count,
        "is_complete": complete if complete is not None else candle.is_complete,
    }


def serialize_atm(atm: ATMResult | None) -> dict | None:
    if atm is None:
        return None
    return {
        "strike": atm.strike,
        "call_ltp": atm.call_ltp,
        "put_ltp": atm.put_ltp,
        "straddle_premium": atm.straddle_premium,
        "combined_value": atm.straddle_premium,  # ATM CE + PE, alias for on-screen label
        "underlying_ltp": atm.underlying_ltp,
        "distance_from_spot": atm.distance_from_spot,
        "method": atm.method,
        "call_delta": atm.call_delta,
        "put_delta": atm.put_delta,
        "delta_threshold": atm.delta_threshold,
        "price_based_strike": atm.price_based_strike,
    }


def serialize_strike_candles(strike: float, builders: dict[str, CandleAggregator]) -> dict:
    """CE/PE/Straddle OHLC candles for one fixed strike, at every interval —
    backs the ATM Straddle Chart's candlestick view (GET /api/straddle-candles).
    Reuses the exact same serialize_candle() the main candlestick chart uses;
    each leg's CandleAggregator was fed that strike's own price only, so
    there is nothing here to guard against mixing strikes."""
    by_interval: dict[str, dict] = {}
    for interval in builders["straddle"].intervals:
        by_interval[str(interval)] = {}
        for leg in ("ce", "pe", "straddle"):
            agg = builders[leg]
            completed = agg.completed_candles.get(interval, [])
            active = agg.active_candles.get(interval)
            series = [serialize_candle(c) for c in completed[-150:]]
            if active is not None:
                series.append(serialize_candle(active, complete=False))
            by_interval[str(interval)][leg] = series
    return {"strike": strike, "by_interval": by_interval}


def serialize_chain(chain: OptionChainSnapshot | None, atm_strike: float | None) -> dict | None:
    if chain is None:
        return None

    strikes = []
    for leg in chain.strikes:
        strikes.append(
            {
                "strike": leg.strike,
                "call_ltp": leg.call_ltp,
                "put_ltp": leg.put_ltp,
                "call_oi": leg.call_oi,
                "put_oi": leg.put_oi,
                "call_volume": leg.call_volume,
                "put_volume": leg.put_volume,
                "call_delta": leg.call_delta,  # Optional: CE Delta for future Delta-based ATM
                "put_delta": leg.put_delta,  # Optional: PE Delta for future Delta-based ATM
                # Same isolated CE+PE formula used everywhere else (MockPriceCalculator._combined_value)
                "combined_value": leg.call_ltp + leg.put_ltp,
                "is_atm": leg.strike == atm_strike if atm_strike is not None else False,
            }
        )

    return {
        "underlying": chain.underlying,
        "underlying_ltp": chain.underlying_ltp,
        "expiry": chain.expiry,
        "expiry_type": chain.expiry_type,  # Configurable expiry type
        "timestamp": _dt(chain.timestamp),
        "strikes": strikes,
    }


def serialize_snapshot(
    *,
    underlying: str,
    tick: PriceTick | None,
    atm: ATMResult | None,
    chain: OptionChainSnapshot | None,
    calculated_prices: dict | None = None,
    rrg_snapshot = None,
    active_candles: dict[int, Candle],
    completed_candles: dict[int, list[Candle]],
    newly_completed: list[Candle],
    tick_count: int,
    intervals: list[int],
    data_source: str,
    status: str = "LIVE",
    paper_trading: dict | None = None,
    last_tick_age_seconds: float | None = None,
    is_stale: bool = False,
    stale_threshold_seconds: float | None = None,
    persistence_enabled: bool = False,
    duplicate_tick_count: int = 0,
    rejected_tick_count: int = 0,
    market_session: str | None = None,
    settings: dict | None = None,
) -> dict:
    atm_strike = atm.strike if atm else None
    candles_by_interval: dict[str, dict] = {}

    for interval in intervals:
        completed = completed_candles.get(interval, [])
        active = active_candles.get(interval)
        series = [serialize_candle(c) for c in completed[-100:]]
        if active is not None:
            series.append(serialize_candle(active, complete=False))
        candles_by_interval[str(interval)] = {
            "active": serialize_candle(active, complete=False) if active else None,
            "completed": [serialize_candle(c) for c in completed[-20:]],
            "series": series,
        }

    # Serialize RRG snapshot if available
    rrg_data = None
    if rrg_snapshot:
        rrg_data = rrg_snapshot.to_dict()

    return {
        "underlying": underlying,
        "data_source": data_source,
        "status": status,
        "tick_count": tick_count,
        "price": tick.price if tick else None,
        "timestamp": _dt(tick.timestamp) if tick else None,
        "data_quality": {
            "source": data_source,
            "connection_status": status,
            "tick_count": tick_count,
            "last_tick_time": _dt(tick.timestamp) if tick else None,
            "last_tick_age_seconds": (
                round(last_tick_age_seconds, 2) if last_tick_age_seconds is not None else None
            ),
            "is_stale": is_stale,
            "stale_threshold_seconds": stale_threshold_seconds,
            "persistence_enabled": persistence_enabled,
            "duplicate_tick_count": duplicate_tick_count,
            "rejected_tick_count": rejected_tick_count,
            "market_session": market_session,
        },
        "atm": serialize_atm(atm),
        "option_chain": serialize_chain(chain, atm_strike),
        "calculated_prices": calculated_prices,
        "rrg": rrg_data,
        "intervals": intervals,
        "candles": candles_by_interval,
        "newly_completed": [serialize_candle(c) for c in newly_completed],
        "paper_trading": paper_trading
        or {
            "simulated": True,
            "config": {"take_profit_percent": 10.0, "stop_loss_percent": 5.0},
            "open_positions": [],
            "history": [],
            "stats": {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate_percent": 0.0,
                "total_pnl": 0.0,
                "average_win": 0.0,
                "average_loss": 0.0,
                "max_drawdown": 0.0,
            },
        },
        "settings": settings or {},
    }
