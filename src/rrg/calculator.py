"""RRG calculator for option strikes."""

from collections import deque
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Optional

import numpy as np
import pandas as pd

from src.models import OptionChainSnapshot, PriceTick
from src.rrg.models import RRGConfig, RRGDataPoint, RRGQuadrant, RRGSnapshot
from src.timeutil import now_ist


class RRGCalculator:
    """
    Calculates Relative Rotation Graph (RRG) metrics for option strikes.
    
    Custom RRG implementation based on prototype formulas:
    - RS = (Option Premium / Benchmark Spot) × 100
    - RS-Ratio = 100 + z-score(RS) × multiplier
    - RS-Momentum = 100 + z-score(ROC(RS-Ratio)) × multiplier
    """

    def __init__(self, config: RRGConfig):
        self.config = config
        
        # Data storage for time series calculations
        self._benchmark_history: Deque[tuple[datetime, float]] = deque(maxlen=config.rolling_window + 10)
        self._option_history: Dict[str, Deque[tuple[datetime, float]]] = {}
        
        # Cache for latest values
        self._latest_benchmark_ltp: Optional[float] = None
        self._latest_option_chain: Optional[OptionChainSnapshot] = None
        self._latest_timestamp: Optional[datetime] = None

    def update(self, tick: PriceTick, option_chain: OptionChainSnapshot) -> None:
        """
        Update RRG calculator with new market data.
        
        Args:
            tick: Latest price tick for benchmark
            option_chain: Latest option chain data
        """
        self._latest_timestamp = tick.timestamp
        self._latest_benchmark_ltp = tick.price
        self._latest_option_chain = option_chain
        
        # Update benchmark history
        self._benchmark_history.append((tick.timestamp, tick.price))
        
        # Update option history for relevant strikes
        strikes_to_track = self._get_strikes_to_track(option_chain)
        
        for strike_data in strikes_to_track:
            key = self._make_option_key(strike_data['strike'], strike_data['type'])
            
            if key not in self._option_history:
                self._option_history[key] = deque(maxlen=self.config.rolling_window + 10)
            
            self._option_history[key].append((tick.timestamp, strike_data['ltp']))

    def calculate_rrg(self) -> RRGSnapshot:
        """
        Calculate current RRG values for all tracked strikes.
        
        Returns:
            RRGSnapshot with current RRG metrics
        """
        if self._latest_benchmark_ltp is None or self._latest_option_chain is None:
            raise ValueError("Insufficient data for RRG calculation")
        
        data_points = []
        
        # Get strikes to analyze
        strikes_to_analyze = self._get_strikes_to_track(self._latest_option_chain)
        
        for strike_data in strikes_to_analyze:
            try:
                rrg_point = self._calculate_strike_rrg(strike_data)
                if rrg_point:
                    data_points.append(rrg_point)
            except Exception as e:
                # Skip strikes that can't be calculated
                continue
        
        return RRGSnapshot(
            benchmark_symbol=self.config.benchmark_symbol,
            benchmark_ltp=self._latest_benchmark_ltp,
            timeframe=self.config.timeframe,
            timestamp=self._latest_timestamp or now_ist(),
            data_points=data_points,
        )

    def _calculate_strike_rrg(self, strike_data: dict) -> Optional[RRGDataPoint]:
        """Calculate RRG metrics for a single strike."""
        strike = strike_data['strike']
        option_type = strike_data['type']
        option_ltp = strike_data['ltp']
        benchmark_ltp = self._latest_benchmark_ltp
        
        key = self._make_option_key(strike, option_type)
        
        # Check if we have enough history
        if key not in self._option_history or len(self._option_history[key]) < 2:
            return None
        
        # Extract time series
        option_history = list(self._option_history[key])
        benchmark_history = list(self._benchmark_history)
        
        # Create aligned time series
        option_series = self._create_aligned_series(option_history, benchmark_history)
        benchmark_series = self._create_aligned_series(benchmark_history, benchmark_history)
        
        if len(option_series) < 2:
            return None
        
        try:
            # Calculate RS = (Option Premium / Benchmark Spot) × 100
            rs_series = (option_series / benchmark_series) * 100
            
            # Calculate RS-Ratio
            rs_ratio = self._calculate_rs_ratio(rs_series)
            
            # Calculate RS-Momentum
            rs_momentum = self._calculate_rs_momentum(rs_ratio, rs_series)
            
            # Determine quadrant
            quadrant = self._determine_quadrant(rs_ratio, rs_momentum)
            
            return RRGDataPoint(
                strike=strike,
                option_type=option_type,
                rs=rs_series.iloc[-1] if hasattr(rs_series, 'iloc') else rs_series[-1],
                rs_ratio=rs_ratio,
                rs_momentum=rs_momentum,
                quadrant=quadrant,
                timestamp=self._latest_timestamp or now_ist(),
                option_ltp=option_ltp,
                benchmark_ltp=benchmark_ltp,
            )
        except Exception as e:
            # Log error but don't fail the entire calculation
            import logging
            logging.getLogger(__name__).warning(f"Failed to calculate RRG for {key}: {e}")
            return None

    def _calculate_rs_ratio(self, rs_series: pd.Series) -> float:
        """
        Calculate RS-Ratio from RS series.
        
        Formula: RS-Ratio = 100 + z-score(RS) × multiplier
        """
        window = min(self.config.rolling_window, len(rs_series))
        
        if window < 2:
            return 100.0  # Default to neutral
        
        # Calculate rolling statistics
        rolling_mean = rs_series.rolling(window=window).mean().iloc[-1]
        rolling_std = rs_series.rolling(window=window).std().iloc[-1]
        
        # Calculate z-score
        if rolling_std == 0 or pd.isna(rolling_std):
            z_score = 0.0
        else:
            current_rs = rs_series.iloc[-1]
            z_score = (current_rs - rolling_mean) / rolling_std
        
        # Calculate RS-Ratio
        rs_ratio = 100 + z_score * self.config.rs_ratio_multiplier
        
        return rs_ratio

    def _calculate_rs_momentum(self, current_rs_ratio: float, rs_series: pd.Series) -> float:
        """
        Calculate RS-Momentum from RS-Ratio.
        
        Formula: RS-Momentum = 100 + z-score(ROC(RS-Ratio)) × multiplier
        """
        window = min(self.config.rolling_window, len(rs_series))
        
        if window < 2:
            return 100.0  # Default to neutral
        
        # Calculate RS-Ratio series for momentum calculation
        rs_ratio_series = []
        for i in range(window, len(rs_series) + 1):
            window_rs = rs_series.iloc[i-window:i] if i >= window else rs_series.iloc[:i]
            
            if len(window_rs) < 2:
                rs_ratio_series.append(100.0)
                continue
            
            rolling_mean = window_rs.mean()
            rolling_std = window_rs.std()
            
            if rolling_std == 0 or pd.isna(rolling_std):
                z_score = 0.0
            else:
                current_rs = window_rs.iloc[-1]
                z_score = (current_rs - rolling_mean) / rolling_std
            
            rs_ratio_series.append(100 + z_score * self.config.rs_ratio_multiplier)
        
        rs_ratio_series = pd.Series(rs_ratio_series)
        
        # Calculate rate of change (momentum period)
        if len(rs_ratio_series) < self.config.momentum_period + 1:
            return 100.0
        
        roc_period = min(self.config.momentum_period, len(rs_ratio_series) - 1)
        roc = rs_ratio_series.pct_change(periods=roc_period).iloc[-1]
        
        if pd.isna(roc):
            return 100.0
        
        # Calculate z-score of ROC
        roc_series = rs_ratio_series.pct_change(periods=roc_period).dropna()
        
        if len(roc_series) < 2:
            return 100.0
        
        roc_mean = roc_series.mean()
        roc_std = roc_series.std()
        
        if roc_std == 0 or pd.isna(roc_std):
            z_score = 0.0
        else:
            z_score = (roc - roc_mean) / roc_std
        
        # Calculate RS-Momentum
        rs_momentum = 100 + z_score * self.config.rs_momentum_multiplier
        
        return rs_momentum

    def _determine_quadrant(self, rs_ratio: float, rs_momentum: float) -> RRGQuadrant:
        """Determine quadrant based on RS-Ratio and RS-Momentum."""
        if rs_ratio > 100 and rs_momentum > 100:
            return RRGQuadrant.LEADING
        elif rs_ratio < 100 and rs_momentum > 100:
            return RRGQuadrant.IMPROVING
        elif rs_ratio < 100 and rs_momentum < 100:
            return RRGQuadrant.LAGGING
        else:  # rs_ratio > 100 and rs_momentum < 100
            return RRGQuadrant.WEAKENING

    def _get_strikes_to_track(self, option_chain: OptionChainSnapshot) -> List[dict]:
        """Get list of strikes to track based on configuration."""
        strikes = []
        
        for leg in option_chain.strikes:
            # Filter by configured strikes if specified
            if self.config.option_strikes and leg.strike not in self.config.option_strikes:
                continue
            
            # Filter by expiry if specified
            if self.config.expiry and option_chain.expiry != self.config.expiry:
                continue
            
            # Add both CE and PE
            strikes.append({
                'strike': leg.strike,
                'type': 'CE',
                'ltp': leg.call_ltp,
            })
            strikes.append({
                'strike': leg.strike,
                'type': 'PE',
                'ltp': leg.put_ltp,
            })
        
        return strikes if strikes else []

    def _make_option_key(self, strike: float, option_type: str) -> str:
        """Create a unique key for an option."""
        return f"{strike}_{option_type}"

    def _create_aligned_series(self, history: List[tuple], reference: List[tuple]) -> pd.Series:
        """Create aligned time series from history."""
        if not history:
            return pd.Series([])
        
        # Extract timestamps and values
        timestamps, values = zip(*history)
        
        # Create pandas series with datetime index
        series = pd.Series(list(values), index=pd.to_datetime(timestamps))
        
        # Sort by timestamp
        series = series.sort_index()
        
        return series

    def get_history_summary(self) -> dict:
        """Get summary of current data history."""
        return {
            "benchmark_points": len(self._benchmark_history),
            "tracked_options": len(self._option_history),
            "config": {
                "rolling_window": self.config.rolling_window,
                "momentum_period": self.config.momentum_period,
                "timeframe": self.config.timeframe,
            }
        }
