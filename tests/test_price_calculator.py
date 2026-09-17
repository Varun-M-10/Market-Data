"""Tests for PriceCalculator component."""

import pytest

from src.models import ATMResult
from src.price_calculator import (
    BlackScholesCalculator,
    DeltaNeutralCalculator,
    MockPriceCalculator,
    get_calculator,
)


def test_mock_calculator_basic():
    """Test basic mock calculator functionality."""
    calc = MockPriceCalculator()
    atm = ATMResult(
        strike=25000.0,
        call_ltp=200.0,
        put_ltp=180.0,
        straddle_premium=380.0,
        underlying_ltp=25000.0,
        distance_from_spot=0.0,
    )

    result = calc.calculate(atm)
    assert result is not None
    assert "straddle_premium" in result
    assert "call_put_ratio" in result
    assert "synthetic_price" in result
    assert "calculation_method" in result


def test_mock_calculator_straddle():
    """Test that mock calculator correctly calculates straddle premium."""
    calc = MockPriceCalculator()
    atm = ATMResult(
        strike=25000.0,
        call_ltp=150.5,
        put_ltp=175.25,
        straddle_premium=325.75,
        underlying_ltp=25000.0,
        distance_from_spot=0.0,
    )

    result = calc.calculate(atm)
    assert result["straddle_premium"] == 325.75


def test_mock_calculator_call_put_ratio():
    """Test that mock calculator correctly calculates call/put ratio."""
    calc = MockPriceCalculator()
    atm = ATMResult(
        strike=25000.0,
        call_ltp=200.0,
        put_ltp=100.0,
        straddle_premium=300.0,
        underlying_ltp=25000.0,
        distance_from_spot=0.0,
    )

    result = calc.calculate(atm)
    assert result["call_put_ratio"] == 2.0


def test_mock_calculator_zero_put():
    """Test mock calculator handles zero put price."""
    calc = MockPriceCalculator()
    atm = ATMResult(
        strike=25000.0,
        call_ltp=200.0,
        put_ltp=0.0,
        straddle_premium=200.0,
        underlying_ltp=25000.0,
        distance_from_spot=0.0,
    )

    result = calc.calculate(atm)
    assert result["call_put_ratio"] == 0.0


def test_mock_calculator_synthetic():
    """Test that mock calculator correctly calculates synthetic price (Call - Put)."""
    calc = MockPriceCalculator()
    atm = ATMResult(
        strike=25000.0,
        call_ltp=200.0,
        put_ltp=180.0,
        straddle_premium=380.0,
        underlying_ltp=25000.0,
        distance_from_spot=0.0,
    )

    result = calc.calculate(atm)
    assert result["synthetic_price"] == 20.0  # 200 - 180


def test_mock_calculator_none_atm():
    """Test mock calculator handles None ATM result."""
    calc = MockPriceCalculator()
    result = calc.calculate(None)

    assert result is not None
    assert result["straddle_premium"] == 0.0
    assert result["call_put_ratio"] == 0.0
    assert result["synthetic_price"] == 0.0


def test_black_scholes_not_implemented():
    """Test that BlackScholesCalculator raises NotImplementedError."""
    calc = BlackScholesCalculator()
    atm = ATMResult(
        strike=25000.0,
        call_ltp=200.0,
        put_ltp=180.0,
        straddle_premium=380.0,
        underlying_ltp=25000.0,
        distance_from_spot=0.0,
    )

    with pytest.raises(NotImplementedError):
        calc.calculate(atm)


def test_delta_neutral_not_implemented():
    """Test that DeltaNeutralCalculator raises NotImplementedError."""
    calc = DeltaNeutralCalculator()
    atm = ATMResult(
        strike=25000.0,
        call_ltp=200.0,
        put_ltp=180.0,
        straddle_premium=380.0,
        underlying_ltp=25000.0,
        distance_from_spot=0.0,
    )

    with pytest.raises(NotImplementedError):
        calc.calculate(atm)


def test_get_calculator_mock():
    """Test get_calculator factory for mock method."""
    calc = get_calculator("mock")
    assert isinstance(calc, MockPriceCalculator)


def test_get_calculator_case_insensitive():
    """Test get_calculator is case-insensitive."""
    calc_lower = get_calculator("mock")
    calc_upper = get_calculator("MOCK")
    calc_mixed = get_calculator("Mock")

    assert isinstance(calc_lower, MockPriceCalculator)
    assert isinstance(calc_upper, MockPriceCalculator)
    assert isinstance(calc_mixed, MockPriceCalculator)


def test_get_calculator_black_scholes():
    """Test get_calculator factory for black_scholes method."""
    calc = get_calculator("black_scholes")
    assert isinstance(calc, BlackScholesCalculator)


def test_get_calculator_delta_neutral():
    """Test get_calculator factory for delta_neutral method."""
    calc = get_calculator("delta_neutral")
    assert isinstance(calc, DeltaNeutralCalculator)


def test_get_calculator_invalid_method():
    """Test get_calculator raises ValueError for invalid method."""
    with pytest.raises(ValueError, match="Unknown calculator method"):
        get_calculator("invalid_method")


def test_get_calculator_default():
    """Test get_calculator defaults to mock if no method specified."""
    calc = get_calculator()
    assert isinstance(calc, MockPriceCalculator)


def test_mock_calculator_method_label():
    """Test that mock calculator labels its method correctly."""
    calc = MockPriceCalculator()
    atm = ATMResult(
        strike=25000.0,
        call_ltp=200.0,
        put_ltp=180.0,
        straddle_premium=380.0,
        underlying_ltp=25000.0,
        distance_from_spot=0.0,
    )

    result = calc.calculate(atm)
    assert result["calculation_method"] == "mock_simple_addition"
