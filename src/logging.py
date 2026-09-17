"""Structured JSON logging for market data system."""

import json
import logging
import threading
from collections import deque
from datetime import datetime
from typing import Any

from src.models import Candle, PriceTick

# How many recent log entries the in-memory ring buffer keeps for the UI's
# System Logs panel (`GET /api/logs`). Purely additive to the existing
# stdout JSON logging below — nothing else depends on it.
RECENT_LOG_BUFFER_SIZE = 500


class StructuredLogger:
    """Logger that outputs structured JSON for prices and candles."""

    def __init__(self, log_level: str = "INFO"):
        self.logger = logging.getLogger("market_data")
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        # Console handler
        handler = logging.StreamHandler()
        handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # In-memory ring buffer so the web UI can read recent log entries
        # without tailing stdout. Thread-safe (the tick worker logs from a
        # background thread, the API reads from the request-handling loop).
        self._recent: deque[dict] = deque(maxlen=RECENT_LOG_BUFFER_SIZE)
        self._recent_lock = threading.Lock()

    def _remember(self, entry: dict, level: str) -> None:
        with self._recent_lock:
            self._recent.append({**entry, "level": level})

    def get_recent(self, limit: int = 200, level: str | None = None) -> list[dict]:
        """Most recent log entries, newest first. Optional `level` filter."""
        with self._recent_lock:
            entries = list(self._recent)
        if level:
            entries = [e for e in entries if e.get("level") == level.upper()]
        return list(reversed(entries))[:limit]

    def log_price_tick(self, tick: PriceTick, metadata: dict[str, Any] | None = None) -> None:
        """Log a price tick in structured JSON format."""
        log_entry = {
            "event_type": "price_tick",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "symbol": tick.symbol,
                "price": tick.price,
                "tick_timestamp": tick.timestamp.isoformat(),
                "volume": tick.volume,
            },
            "metadata": metadata or {},
        }
        self._remember(log_entry, "INFO")
        self.logger.info(json.dumps(log_entry))

    def log_candle_completed(self, candle: Candle, metadata: dict[str, Any] | None = None) -> None:
        """Log a completed candle in structured JSON format."""
        log_entry = {
            "event_type": "candle_completed",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "symbol": candle.symbol,
                "interval_minutes": candle.interval_minutes,
                "open_time": candle.open_time.isoformat(),
                "close_time": candle.close_time.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "tick_count": candle.tick_count,
                "is_complete": candle.is_complete,
            },
            "metadata": metadata or {},
        }
        self._remember(log_entry, "INFO")
        self.logger.info(json.dumps(log_entry))

    def log_atm_update(self, atm_data: dict, metadata: dict[str, Any] | None = None) -> None:
        """Log ATM strike update in structured JSON format."""
        log_entry = {
            "event_type": "atm_update",
            "timestamp": datetime.now().isoformat(),
            "data": atm_data,
            "metadata": metadata or {},
        }
        self._remember(log_entry, "INFO")
        self.logger.info(json.dumps(log_entry))

    def log_calculated_prices(
        self, calculated: dict, metadata: dict[str, Any] | None = None
    ) -> None:
        """Log calculated prices in structured JSON format."""
        log_entry = {
            "event_type": "calculated_prices",
            "timestamp": datetime.now().isoformat(),
            "data": calculated,
            "metadata": metadata or {},
        }
        self._remember(log_entry, "INFO")
        self.logger.info(json.dumps(log_entry))

    def log_error(self, error: Exception, metadata: dict[str, Any] | None = None) -> None:
        """Log an error in structured JSON format."""
        log_entry = {
            "event_type": "error",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
            "metadata": metadata or {},
        }
        self._remember(log_entry, "ERROR")
        self.logger.error(json.dumps(log_entry))

    def log_system_event(
        self, event: str, data: dict[str, Any] | None = None, metadata: dict[str, Any] | None = None
    ) -> None:
        """Log a system event in structured JSON format."""
        log_entry = {
            "event_type": "system_event",
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "data": data or {},
            "metadata": metadata or {},
        }
        self._remember(log_entry, "INFO")
        self.logger.info(json.dumps(log_entry))


# Global logger instance
_logger: StructuredLogger | None = None


def get_logger(log_level: str = "INFO") -> StructuredLogger:
    """Get or create the global structured logger instance."""
    global _logger
    if _logger is None:
        _logger = StructuredLogger(log_level)
    return _logger


def set_logger(logger: StructuredLogger) -> None:
    """Set a custom structured logger instance."""
    global _logger
    _logger = logger
