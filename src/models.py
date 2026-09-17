from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PriceTick:
    """Single price observation from the market."""

    symbol: str
    price: float
    timestamp: datetime
    volume: Optional[float] = None


@dataclass
class OptionLeg:
    strike: float
    call_ltp: float
    put_ltp: float
    call_oi: Optional[int] = None
    put_oi: Optional[int] = None
    call_volume: Optional[int] = None
    put_volume: Optional[int] = None
    call_delta: Optional[float] = None  # Optional: CE Delta for future Delta-based ATM
    put_delta: Optional[float] = None  # Optional: PE Delta for future Delta-based ATM


@dataclass
class OptionChainSnapshot:
    underlying: str
    underlying_ltp: float
    expiry: str
    timestamp: datetime
    strikes: list[OptionLeg] = field(default_factory=list)
    # Configurable expiry field for flexibility
    expiry_type: Optional[str] = None  # e.g., "weekly", "monthly"


@dataclass
class ATMResult:
    """At-The-Money strike and derived values."""

    strike: float
    call_ltp: float
    put_ltp: float
    straddle_premium: float  # Call + Put at ATM
    underlying_ltp: float
    distance_from_spot: float  # |strike - spot|
    method: str = "price"  # "price" (nearest to spot) or "delta" (Greeks-based)
    call_delta: Optional[float] = None
    put_delta: Optional[float] = None
    delta_threshold: Optional[float] = None  # target |delta|, e.g. 0.50
    price_based_strike: Optional[float] = None  # nearest-to-spot strike, for comparison


@dataclass
class Candle:
    """OHLC candlestick for a given interval."""

    symbol: str
    interval_minutes: int
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_count: int = 0
    is_complete: bool = False

    def update(self, price: float) -> None:
        if self.tick_count == 0:
            self.open = price
            self.high = price
            self.low = price
        else:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
        self.close = price
        self.tick_count += 1
