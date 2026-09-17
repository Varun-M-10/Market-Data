from __future__ import annotations

from abc import ABC, abstractmethod


class DataSource(ABC):
    """Abstract market data source."""

    @abstractmethod
    def fetch_option_chain(self) -> dict:
        """Return raw option chain payload."""

    @abstractmethod
    def get_underlying_ltp(self) -> float:
        """Return latest underlying last traded price."""

    @abstractmethod
    def stream_ticks(self):
        """Yield PriceTick objects continuously."""


# Alias for interface compatibility
MarketDataProvider = DataSource

