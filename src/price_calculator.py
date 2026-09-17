from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.models import ATMResult


class PriceCalculator(ABC):
    """Abstract base class for price calculation strategies."""

    @abstractmethod
    def calculate(self, atm: ATMResult) -> dict:
        """
        Calculate derived prices from ATM data.
        
        Args:
            atm: ATM result containing strike, call_ltp, put_ltp, etc.
            
        Returns:
            Dictionary with calculated values. Structure is implementation-dependent.
        """
        pass


class MockPriceCalculator(PriceCalculator):
    """
    Temporary mock calculator for testing the pipeline.
    Uses simple addition: Call + Put = Straddle Premium (= "Combined Value").

    This is a placeholder until the client provides the final business formula.
    The formula lives in exactly one place (`_combined_value` below) so it can
    be swapped without touching callers or the ATM/serialization layers.
    """

    def _combined_value(self, atm: ATMResult) -> float:
        """Combined Value = ATM Call LTP + ATM Put LTP. Isolated for easy replacement."""
        return atm.call_ltp + atm.put_ltp

    def calculate(self, atm: ATMResult) -> dict:
        if atm is None:
            return {
                "straddle_premium": 0.0,
                "combined_value": 0.0,
                "call_put_ratio": 0.0,
                "synthetic_price": 0.0,
                "calculation_method": "mock_simple_addition",
            }

        combined = self._combined_value(atm)
        ratio = atm.call_ltp / atm.put_ltp if atm.put_ltp > 0 else 0.0
        synthetic = atm.call_ltp - atm.put_ltp

        return {
            # "straddle_premium" kept for backward compatibility; "combined_value"
            # is the client-facing name requested for ATM CE + PE.
            "straddle_premium": combined,
            "combined_value": combined,
            "call_put_ratio": ratio,
            "synthetic_price": synthetic,
            "calculation_method": "mock_simple_addition",
        }


class BlackScholesCalculator(PriceCalculator):
    """
    Placeholder for Black-Scholes implementation.
    Not implemented until client confirms formula requirements.
    """

    def calculate(self, atm: ATMResult) -> dict:
        raise NotImplementedError(
            "Black-Scholes calculator not implemented. "
            "Client needs to confirm formula requirements."
        )


class DeltaNeutralCalculator(PriceCalculator):
    """
    Placeholder for Delta-neutral strategy implementation.
    Not implemented until client confirms formula requirements.
    """

    def calculate(self, atm: ATMResult) -> dict:
        raise NotImplementedError(
            "Delta-neutral calculator not implemented. "
            "Client needs to confirm formula requirements."
        )


def get_calculator(method: str = "mock") -> PriceCalculator:
    """
    Factory function to get the appropriate price calculator.
    
    Args:
        method: Calculation method ('mock', 'black_scholes', 'delta_neutral')
        
    Returns:
        PriceCalculator instance
        
    Raises:
        ValueError: If method is not supported
    """
    calculators = {
        "mock": MockPriceCalculator,
        "black_scholes": BlackScholesCalculator,
        "delta_neutral": DeltaNeutralCalculator,
    }
    
    calculator_class = calculators.get(method.lower())
    if calculator_class is None:
        raise ValueError(
            f"Unknown calculator method: {method}. "
            f"Supported methods: {list(calculators.keys())}"
        )
    
    return calculator_class()
