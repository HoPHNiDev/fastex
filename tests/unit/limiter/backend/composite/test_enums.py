"""
Unit tests for composite backend enums.

This module tests the enum classes used by the composite backend:
- SwitchingStrategy: Strategy for switching between primary and fallback backends
- CircuitBreakerState: Circuit breaker states for resilience pattern

Tests cover:
- Enum structure and values
- String representations
- Membership testing
- Type validation
"""

import pytest

from fastex.limiter.backend.composite.enums import (
    CircuitBreakerState,
    SwitchingStrategy,
)


class TestSwitchingStrategy:
    """Test SwitchingStrategy enum functionality."""

    def test_enum_values(self) -> None:
        """Test that all expected enum values exist."""
        expected_values = {
            "FAIL_FAST": "fail_fast",
            "CIRCUIT_BREAKER": "circuit_breaker",
            "HEALTH_CHECK": "health_check",
        }

        for name, value in expected_values.items():
            assert hasattr(SwitchingStrategy, name)
            assert getattr(SwitchingStrategy, name).value == value

    def test_enum_membership(self) -> None:
        """Test enum membership checks."""
        valid_strategies = [
            SwitchingStrategy.FAIL_FAST,
            SwitchingStrategy.CIRCUIT_BREAKER,
            SwitchingStrategy.HEALTH_CHECK,
        ]

        for strategy in valid_strategies:
            assert strategy in SwitchingStrategy

    def test_enum_string_representation(self) -> None:
        """Test string representation of enum values."""
        assert str(SwitchingStrategy.FAIL_FAST) == "SwitchingStrategy.FAIL_FAST"
        assert (
            str(SwitchingStrategy.CIRCUIT_BREAKER)
            == "SwitchingStrategy.CIRCUIT_BREAKER"
        )
        assert str(SwitchingStrategy.HEALTH_CHECK) == "SwitchingStrategy.HEALTH_CHECK"

    def test_enum_value_access(self) -> None:
        """Test accessing enum values."""
        assert SwitchingStrategy.FAIL_FAST.value == "fail_fast"
        assert SwitchingStrategy.CIRCUIT_BREAKER.value == "circuit_breaker"
        assert SwitchingStrategy.HEALTH_CHECK.value == "health_check"

    def test_enum_comparison(self) -> None:
        """Test enum comparison operations."""
        assert SwitchingStrategy.FAIL_FAST == SwitchingStrategy.FAIL_FAST

    def test_enum_count(self) -> None:
        """Test that enum has expected number of members."""
        assert len(SwitchingStrategy) == 3

    @pytest.mark.parametrize(
        "strategy",
        [
            SwitchingStrategy.FAIL_FAST,
            SwitchingStrategy.CIRCUIT_BREAKER,
            SwitchingStrategy.HEALTH_CHECK,
        ],
    )
    def test_enum_iteration(self, strategy: SwitchingStrategy) -> None:
        """Test that all strategies can be iterated."""
        assert strategy in list(SwitchingStrategy)


class TestCircuitBreakerState:
    """Test CircuitBreakerState enum functionality."""

    def test_enum_values(self) -> None:
        """Test that all expected enum values exist."""
        expected_values = {
            "CLOSED": "closed",
            "OPEN": "open",
            "HALF_OPEN": "half_open",
        }

        for name, value in expected_values.items():
            assert hasattr(CircuitBreakerState, name)
            assert getattr(CircuitBreakerState, name).value == value

    def test_enum_membership(self) -> None:
        """Test enum membership checks."""
        valid_states = [
            CircuitBreakerState.CLOSED,
            CircuitBreakerState.OPEN,
            CircuitBreakerState.HALF_OPEN,
        ]

        for state in valid_states:
            assert state in CircuitBreakerState

    def test_enum_string_representation(self) -> None:
        """Test string representation of enum values."""
        assert str(CircuitBreakerState.CLOSED) == "CircuitBreakerState.CLOSED"
        assert str(CircuitBreakerState.OPEN) == "CircuitBreakerState.OPEN"
        assert str(CircuitBreakerState.HALF_OPEN) == "CircuitBreakerState.HALF_OPEN"

    def test_enum_value_access(self) -> None:
        """Test accessing enum values."""
        assert CircuitBreakerState.CLOSED.value == "closed"
        assert CircuitBreakerState.OPEN.value == "open"
        assert CircuitBreakerState.HALF_OPEN.value == "half_open"

    def test_enum_count(self) -> None:
        """Test that enum has expected number of members."""
        assert len(CircuitBreakerState) == 3

    @pytest.mark.parametrize(
        "state",
        [
            CircuitBreakerState.CLOSED,
            CircuitBreakerState.OPEN,
            CircuitBreakerState.HALF_OPEN,
        ],
    )
    def test_enum_iteration(self, state: CircuitBreakerState) -> None:
        """Test that all states can be iterated."""
        assert state in list(CircuitBreakerState)

    def test_circuit_breaker_state_transitions(self) -> None:
        """Test logical state transitions (conceptual)."""
        # These are conceptual tests for state transition logic
        # In real circuit breaker, these transitions would be:
        # CLOSED -> OPEN (on failures)
        # OPEN -> HALF_OPEN (after timeout)
        # HALF_OPEN -> CLOSED (on success) or HALF_OPEN -> OPEN (on failure)

        # Test that we have all necessary states for circuit breaker pattern
        states = {state.value for state in CircuitBreakerState}
        expected_states = {"closed", "open", "half_open"}
        assert states == expected_states


class TestEnumInteroperability:
    """Test interaction between different enums."""

    def test_enum_values_in_dicts(self) -> None:
        """Test using enum values as dictionary keys."""
        strategy_dict = {
            SwitchingStrategy.FAIL_FAST: "fast",
            SwitchingStrategy.CIRCUIT_BREAKER: "breaker",
            SwitchingStrategy.HEALTH_CHECK: "health",
        }

        state_dict = {
            CircuitBreakerState.CLOSED: "normal",
            CircuitBreakerState.OPEN: "failed",
            CircuitBreakerState.HALF_OPEN: "testing",
        }

        assert len(strategy_dict) == 3
        assert len(state_dict) == 3
        assert strategy_dict[SwitchingStrategy.FAIL_FAST] == "fast"
        assert state_dict[CircuitBreakerState.CLOSED] == "normal"

    def test_enum_serialization_values(self) -> None:
        """Test enum values for serialization compatibility."""
        # Test that enum values are JSON-serializable strings
        strategy_values = [strategy.value for strategy in SwitchingStrategy]
        state_values = [state.value for state in CircuitBreakerState]

        for value in strategy_values + state_values:
            assert isinstance(value, str)
            assert len(value) > 0
            assert "_" in value or value.isalpha()  # Valid identifier format
