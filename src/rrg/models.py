"""Data models for RRG analytics."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class RRGQuadrant(Enum):
    """RRG quadrants based on RS-Ratio and RS-Momentum."""
    LEADING = "leading"      # RS-Ratio > 100, RS-Momentum > 100
    IMPROVING = "improving"  # RS-Ratio < 100, RS-Momentum > 100
    LAGGING = "lagging"      # RS-Ratio < 100, RS-Momentum < 100
    WEAKENING = "weakening"  # RS-Ratio > 100, RS-Momentum < 100


@dataclass
class RRGConfig:
    """Configuration for RRG calculations."""
    
    # Data configuration
    benchmark_symbol: str = "NIFTY"  # Nifty 50 Spot
    option_strikes: list = None  # List of strikes to analyze (None = all available)
    expiry: Optional[str] = None  # Specific expiry (None = nearest)
    
    # Timeframe configuration
    timeframe: str = "1min"  # 1min, 5min, 15min, daily
    rolling_window: int = 14  # Number of periods for rolling calculations
    momentum_period: int = 1  # Period for rate of change calculation
    
    # Update configuration
    update_frequency: int = 60  # Seconds between RRG updates
    
    # Calculation parameters
    rs_ratio_multiplier: float = 10.0  # Multiplier for z-score in RS-Ratio
    rs_momentum_multiplier: float = 10.0  # Multiplier for z-score in RS-Momentum
    
    def __post_init__(self):
        if self.option_strikes is None:
            self.option_strikes = []


@dataclass
class RRGDataPoint:
    """Single RRG data point for an option strike."""
    
    strike: float
    option_type: str  # "CE" or "PE"
    rs: float  # Relative Strength
    rs_ratio: float  # RS-Ratio (Trend Strength)
    rs_momentum: float  # RS-Momentum (Rate of Change)
    quadrant: RRGQuadrant
    timestamp: datetime
    
    # Additional context
    option_ltp: float  # Current option premium
    benchmark_ltp: float  # Current benchmark price
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "strike": self.strike,
            "option_type": self.option_type,
            "rs": self.rs,
            "rs_ratio": self.rs_ratio,
            "rs_momentum": self.rs_momentum,
            "quadrant": self.quadrant.value,
            "timestamp": self.timestamp.isoformat(),
            "option_ltp": self.option_ltp,
            "benchmark_ltp": self.benchmark_ltp,
        }


@dataclass
class RRGSnapshot:
    """Complete RRG snapshot for all analyzed strikes."""
    
    benchmark_symbol: str
    benchmark_ltp: float
    timeframe: str
    timestamp: datetime
    data_points: list[RRGDataPoint]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "benchmark_symbol": self.benchmark_symbol,
            "benchmark_ltp": self.benchmark_ltp,
            "timeframe": self.timeframe,
            "timestamp": self.timestamp.isoformat(),
            "data_points": [dp.to_dict() for dp in self.data_points],
        }
