"""
Unit tests for CompositeLimiterBackend connection and disconnection lifecycle.

This module tests the connection/disconnection functionality:
- Connection scenarios (success, partial failure, complete failure)
- Disconnection with cleanup
- Connection state management
- Health status tracking during connection
- Task lifecycle management

Tests cover:
- Successful connection to both backends
- Primary backend connection failure
- Fallback backend connection failure
- Both backends connection failure
- Connection with different configurations
- Disconnection cleanup
- Health check task management
- Safe disconnection with error handling
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from fastex.limiter.backend.composite.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import (
    CircuitBreakerState,
    SwitchingStrategy,
)
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackend


class TestCompositeLimiterBackendConnection:
    """Test CompositeLimiterBackend connection functionality."""

    @pytest.mark.asyncio
    async def test_connect_both_backends_successful(self) -> None:
        """Test successful connection to both backends."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Successful connection
        await backend.connect()

        # Verify both backends were connected
        primary.connect.assert_called_once()
        fallback.connect.assert_called_once()

        # Verify backend state
        assert backend._connected is True
        assert backend._primary_healthy is True
        assert backend._fallback_healthy is True
        assert backend._circuit_state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_connect_with_configs(self) -> None:
        """Test connection with configuration parameters."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        primary_config = MagicMock()
        fallback_config = MagicMock()

        # Connect with configs
        await backend.connect(primary_config, fallback_config)

        # Verify configs were passed
        primary.connect.assert_called_once_with(config=primary_config)
        fallback.connect.assert_called_once_with(config=fallback_config)

        assert backend._connected is True

    @pytest.mark.asyncio
    async def test_connect_without_configs(self) -> None:
        """Test connection without configuration parameters."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Connect without configs
        await backend.connect()

        # Verify None configs were passed
        primary.connect.assert_called_once_with(config=None)
        fallback.connect.assert_called_once_with(config=None)

        assert backend._connected is True

    @pytest.mark.asyncio
    async def test_connect_primary_fails(self) -> None:
        """Test connection when primary backend fails."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Make primary fail
        primary.connect.side_effect = LimiterBackendError("Primary connection failed")

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Should connect successfully with fallback only
        await backend.connect()

        # Verify connection attempts
        primary.connect.assert_called_once()
        fallback.connect.assert_called_once()

        # Verify state
        assert backend._connected is True
        assert backend._primary_healthy is False
        assert backend._fallback_healthy is True
        assert backend._circuit_state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_connect_fallback_fails(self) -> None:
        """Test connection when fallback backend fails."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Make fallback fail
        fallback.connect.side_effect = LimiterBackendError("Fallback connection failed")

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Should connect successfully with primary only
        await backend.connect()

        # Verify connection attempts
        primary.connect.assert_called_once()
        fallback.connect.assert_called_once()

        # Verify state
        assert backend._connected is True
        assert backend._primary_healthy is True
        assert backend._fallback_healthy is False
        assert backend._circuit_state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_connect_both_backends_fail(self) -> None:
        """Test connection when both backends fail."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Make both fail
        primary.connect.side_effect = LimiterBackendError("Primary connection failed")
        fallback.connect.side_effect = LimiterBackendError("Fallback connection failed")

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Should raise error
        with pytest.raises(
            LimiterBackendError,
            match="Failed to connect to both primary and fallback backends",
        ):
            await backend.connect()

        # Verify connection attempts were made
        primary.connect.assert_called_once()
        fallback.connect.assert_called_once()

        # Verify state
        assert backend._connected is False
        assert backend._primary_healthy is False
        assert backend._fallback_healthy is False

    @pytest.mark.asyncio
    async def test_connect_health_check_strategy_starts_task(self) -> None:
        """Test that health check strategy starts background task."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=1,
        )

        # Connect
        await backend.connect()

        # Verify health check task is started
        assert backend._health_check_task is not None
        assert not backend._health_check_task.done()

        # Cleanup
        await backend.disconnect()

    @pytest.mark.asyncio
    async def test_connect_non_health_check_strategy_no_task(self) -> None:
        """Test that non-health check strategies don't start background task."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        strategies = [SwitchingStrategy.FAIL_FAST, SwitchingStrategy.CIRCUIT_BREAKER]

        for strategy in strategies:
            backend = CompositeLimiterBackend(
                primary=primary,
                fallback=fallback,
                strategy=strategy,
            )

            # Connect
            await backend.connect()

            # Verify no health check task
            assert backend._health_check_task is None

            # Cleanup
            await backend.disconnect()


class TestCompositeLimiterBackendDisconnection:
    """Test CompositeLimiterBackend disconnection functionality."""

    @pytest.mark.asyncio
    async def test_disconnect_both_backends_successful(self) -> None:
        """Test successful disconnection from both backends."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Connect first
        await backend.connect()
        assert backend._connected is True

        # Disconnect
        await backend.disconnect()

        # Verify both backends were disconnected
        primary.disconnect.assert_called_once()
        fallback.disconnect.assert_called_once()

        # Verify state
        assert backend._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_with_health_check_task(self) -> None:
        """Test disconnection cancels health check task."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=1,
        )

        # Connect (starts health check task)
        await backend.connect()
        task = backend._health_check_task
        assert task is not None
        assert not task.done()

        # Disconnect
        await backend.disconnect()

        # Verify task was cancelled
        assert task.cancelled() or task.done()
        assert backend._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_primary_fails(self) -> None:
        """Test disconnection when primary backend fails."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Make primary disconnect fail
        primary.disconnect.side_effect = Exception("Primary disconnect failed")

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Connect first
        await backend.connect()

        # Disconnect should not raise error
        await backend.disconnect()

        # Verify both disconnect attempts were made
        primary.disconnect.assert_called_once()
        fallback.disconnect.assert_called_once()

        # Verify state
        assert backend._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_fallback_fails(self) -> None:
        """Test disconnection when fallback backend fails."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Make fallback disconnect fail
        fallback.disconnect.side_effect = Exception("Fallback disconnect failed")

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Connect first
        await backend.connect()

        # Disconnect should not raise error
        await backend.disconnect()

        # Verify both disconnect attempts were made
        primary.disconnect.assert_called_once()
        fallback.disconnect.assert_called_once()

        # Verify state
        assert backend._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_both_backends_fail(self) -> None:
        """Test disconnection when both backends fail."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Make both fail
        primary.disconnect.side_effect = Exception("Primary disconnect failed")
        fallback.disconnect.side_effect = Exception("Fallback disconnect failed")

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Connect first
        await backend.connect()

        # Disconnect should not raise error (graceful degradation)
        await backend.disconnect()

        # Verify both disconnect attempts were made
        primary.disconnect.assert_called_once()
        fallback.disconnect.assert_called_once()

        # Verify state
        assert backend._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        """Test disconnection when backend is not connected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Disconnect without connecting first
        await backend.disconnect()

        # Verify disconnect attempts were still made
        primary.disconnect.assert_called_once()
        fallback.disconnect.assert_called_once()

        # Verify state
        assert backend._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_cancelled_health_check_task(self) -> None:
        """Test disconnection with already cancelled health check task."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=1,
        )

        # Connect (starts health check task)
        await backend.connect()
        task = backend._health_check_task

        # Manually cancel task
        task.cancel()

        # Wait for task to be cancelled
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Disconnect should handle already cancelled task
        await backend.disconnect()

        assert backend._connected is False


class TestCompositeLimiterBackendConnectionState:
    """Test CompositeLimiterBackend connection state management."""

    @pytest.mark.asyncio
    async def test_is_connected_when_connected(self) -> None:
        """Test is_connected returns True when connected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Mock backends as connected
        primary.is_connected.return_value = True
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Connect
        await backend.connect()

        # Should be connected
        assert backend.is_connected() is True

    @pytest.mark.asyncio
    async def test_is_connected_when_disconnected(self) -> None:
        """Test is_connected returns False when disconnected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Mock backends as disconnected
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = False

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Should be disconnected
        assert backend.is_connected() is False

    @pytest.mark.asyncio
    async def test_is_connected_primary_only(self) -> None:
        """Test is_connected when only primary is connected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Mock primary connected, fallback disconnected
        primary.is_connected.return_value = True
        fallback.is_connected.return_value = False

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Connect
        await backend.connect()

        # Should be connected (at least one backend)
        assert backend.is_connected() is True

    @pytest.mark.asyncio
    async def test_is_connected_fallback_only(self) -> None:
        """Test is_connected when only fallback is connected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Mock primary disconnected, fallback connected
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = True

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Connect
        await backend.connect()

        # Should be connected (at least one backend)
        assert backend.is_connected() is True

    @pytest.mark.asyncio
    async def test_is_connected_with_raise_exc_true(self) -> None:
        """Test is_connected with raise_exc=True when not connected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Mock both as disconnected
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = False

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Should raise exception
        with pytest.raises(LimiterBackendError, match="No backends are connected"):
            backend.is_connected(raise_exc=True)

    @pytest.mark.asyncio
    async def test_is_connected_with_raise_exc_false(self) -> None:
        """Test is_connected with raise_exc=False when not connected."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        # Mock both as disconnected
        primary.is_connected.return_value = False
        fallback.is_connected.return_value = False

        backend = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
        )

        # Should return False without raising
        assert backend.is_connected(raise_exc=False) is False
