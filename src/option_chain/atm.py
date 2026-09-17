from __future__ import annotations

from datetime import datetime

from src.models import ATMResult, OptionChainSnapshot, OptionLeg
from src.timeutil import now_ist


def parse_option_chain(raw: dict, underlying: str) -> OptionChainSnapshot:
    """Parse NSE-style option chain JSON into structured snapshot."""
    records = raw.get("records", {})
    spot = float(records.get("underlyingValue", 0))
    expiry_dates = records.get("expiryDates", [])
    expiry = expiry_dates[0] if expiry_dates else ""

    strikes: list[OptionLeg] = []
    for row in records.get("data", []):
        strike = float(row.get("strikePrice", 0))
        ce = row.get("CE") or {}
        pe = row.get("PE") or {}
        strikes.append(
            OptionLeg(
                strike=strike,
                call_ltp=float(ce.get("lastPrice") or 0),
                put_ltp=float(pe.get("lastPrice") or 0),
                call_oi=ce.get("openInterest"),
                put_oi=pe.get("openInterest"),
                call_volume=ce.get("totalTradedVolume"),
                put_volume=pe.get("totalTradedVolume"),
                call_delta=ce.get("delta"),
                put_delta=pe.get("delta"),
            )
        )

    timestamp_str = records.get("timestamp", "")
    try:
        ts = datetime.strptime(timestamp_str, "%d-%b-%Y %H:%M:%S")
    except ValueError:
        ts = now_ist()

    return OptionChainSnapshot(
        underlying=underlying,
        underlying_ltp=spot,
        expiry=expiry,
        timestamp=ts,
        strikes=strikes,
    )


def find_atm_strike(snapshot: OptionChainSnapshot) -> ATMResult | None:
    """Identify ATM strike as the one closest to underlying LTP."""
    if snapshot is None or not snapshot.strikes:
        return None

    spot = snapshot.underlying_ltp
    atm_leg = min(snapshot.strikes, key=lambda leg: abs(leg.strike - spot))

    return ATMResult(
        strike=atm_leg.strike,
        call_ltp=atm_leg.call_ltp,
        put_ltp=atm_leg.put_ltp,
        straddle_premium=atm_leg.call_ltp + atm_leg.put_ltp,
        underlying_ltp=spot,
        distance_from_spot=abs(atm_leg.strike - spot),
        method="price",
    )


def find_atm_strike_delta(
    snapshot: OptionChainSnapshot, delta_threshold: float = 0.5
) -> ATMResult | None:
    """
    Identify ATM strike using option Greeks: the strike whose Call Delta
    and/or Put Delta is closest to `delta_threshold` (default 0.50).

    Put Delta is compared by magnitude (|put_delta|) since the convention
    used here stores it signed (roughly -1..0). A leg is only a candidate if
    it has at least one of call_delta / put_delta populated.

    Returns None if the chain is empty/missing, or if no leg carries any
    Greeks at all (e.g. a provider that doesn't supply delta) — callers
    should fall back to `find_atm_strike` (price-based) in that case.
    """
    if snapshot is None or not snapshot.strikes:
        return None

    candidates = [
        leg for leg in snapshot.strikes if leg.call_delta is not None or leg.put_delta is not None
    ]
    if not candidates:
        return None

    def _score(leg: OptionLeg) -> float:
        deltas = []
        if leg.call_delta is not None:
            deltas.append(abs(leg.call_delta - delta_threshold))
        if leg.put_delta is not None:
            deltas.append(abs(abs(leg.put_delta) - delta_threshold))
        return min(deltas)

    atm_leg = min(candidates, key=_score)
    spot = snapshot.underlying_ltp
    price_based = find_atm_strike(snapshot)

    return ATMResult(
        strike=atm_leg.strike,
        call_ltp=atm_leg.call_ltp,
        put_ltp=atm_leg.put_ltp,
        straddle_premium=atm_leg.call_ltp + atm_leg.put_ltp,
        underlying_ltp=spot,
        distance_from_spot=abs(atm_leg.strike - spot),
        method="delta",
        call_delta=atm_leg.call_delta,
        put_delta=atm_leg.put_delta,
        delta_threshold=delta_threshold,
        price_based_strike=price_based.strike if price_based else None,
    )
