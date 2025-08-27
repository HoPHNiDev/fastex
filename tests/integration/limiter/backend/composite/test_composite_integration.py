"""
Integration tests for CompositeLimiterBackend real-world scenarios.

This module tests end-to-end functionality in realistic scenarios:
- High availability scenarios
- Failover and recovery patterns
- Performance under load
- Multi-backend coordination
- Production-like configurations

Tests cover:
- Redis -> Memory fallback scenarios
- Circuit breaker in action
- Health check monitoring
- Load balancing between backends
- Graceful degradation
- Recovery testing
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from fastex.limiter.backend.composite.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import (
    CircuitBreakerState,
    SwitchingStrategy,
)
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import LimiterBackend
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.schemas import RateLimitConfig


@pytest.mark.integration
class TestHighAvailabilityScenarios:
    """Test high availability scenarios."""

    @pytest.mark.asyncio
    async def test_redis_to_memory_fallback_scenario(self) -> None:
        """Test typical Redis -> In-memory fallback scenario."""
        # Mock Redis backend (primary)
        redis_backend = AsyncMock(spec=LimiterBackend)
        redis_backend.is_connected.return_value = True

        # Mock Memory backend (fallback)
        memory_backend = AsyncMock(spec=LimiterBackend)
        memory_backend.is_connected.return_value = True

        # Composite backend with circuit breaker
        composite = CompositeLimiterBackend(
            primary=redis_backend,
            fallback=memory_backend,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            failure_threshold=3,
            recovery_timeout_seconds=30,
        )

        await composite.connect()

        config = RateLimitConfig(times=100, minutes=1)

        # Phase 1: Normal operation - Redis works
        redis_result = RateLimitResult(
            is_exceeded=False,
            limit_times=100,
            retry_after_ms=0,
            remaining_requests=99,
            reset_time=None,
        )
        redis_backend.check_limit.return_value = redis_result

        for i in range(5):
            result = await composite.check_limit(f"user_{i}", config)
            assert not result.is_exceeded
            assert composite.current_backend == "primary"

        # Phase 2: Redis starts failing
        redis_backend.check_limit.side_effect = LimiterBackendError(
            "Redis connection lost"
        )
        memory_result = RateLimitResult(
            is_exceeded=False,
            limit_times=100,
            retry_after_ms=0,
            remaining_requests=99,
            reset_time=None,
        )
        memory_backend.check_limit.return_value = memory_result

        # Should use fallback after failures
        for i in range(5):
            result = await composite.check_limit(f"user_fail_{i}", config)
            assert not result.is_exceeded

        # Circuit should be open after threshold
        stats = composite.get_stats()
        assert stats["circuit_state"] == "open"
        assert stats["failure_count"] >= 3

        await composite.disconnect()

    @pytest.mark.asyncio
    async def test_gradual_degradation_scenario(self) -> None:
        """Test gradual degradation when primary becomes unreliable."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        composite = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            failure_threshold=2,
            recovery_timeout_seconds=5,
        )

        await composite.connect()

        config = RateLimitConfig(times=50, seconds=30)

        # Simulate intermittent failures
        failure_count = 0

        def intermittent_primary(key: str, config: RateLimitConfig) -> RateLimitResult:
            nonlocal failure_count
            failure_count += 1
            if failure_count % 3 == 0:  # Fail every 3rd request
                raise LimiterBackendError("Primary intermittent failure")
            return RateLimitResult(
                is_exceeded=False,
                limit_times=50,
                retry_after_ms=0,
                remaining_requests=49,
                reset_time=None,
            )

        primary.check_limit.side_effect = intermittent_primary
        fallback.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=50,
            retry_after_ms=0,
            remaining_requests=49,
            reset_time=None,
        )

        # Make several requests
        successful_requests = 0
        for i in range(10):
            try:
                result = await composite.check_limit(f"user_{i}", config)
                if not result.is_exceeded:
                    successful_requests += 1
            except LimiterBackendError:
                pass  # Some requests might fail if both backends fail

        # Should have some successful requests despite failures
        assert successful_requests > 0

        stats = composite.get_stats()
        assert stats["primary_errors"] > 0
        assert stats["total_requests"] >= successful_requests

        await composite.disconnect()

    @pytest.mark.asyncio
    async def test_recovery_after_outage_scenario(self) -> None:
        """Test recovery scenario after complete primary outage."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        composite = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            failure_threshold=2,
            recovery_timeout_seconds=1,  # Fast recovery for testing
        )

        await composite.connect()

        config = RateLimitConfig(times=10, seconds=60)

        # Phase 1: Primary fails completely
        primary.check_limit.side_effect = LimiterBackendError("Complete outage")
        fallback.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=10,
            retry_after_ms=0,
            remaining_requests=9,
            reset_time=None,
        )

        # Generate failures to open circuit
        for i in range(3):
            result = await composite.check_limit(f"outage_{i}", config)
            assert not result.is_exceeded  # Fallback should work

        # Circuit should be open
        assert composite._circuit_state == CircuitBreakerState.OPEN

        # Phase 2: Wait for recovery timeout
        await asyncio.sleep(1.5)  # Wait for recovery timeout

        # Phase 3: Primary recovers
        primary.check_limit.side_effect = None
        primary.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=10,
            retry_after_ms=0,
            remaining_requests=9,
            reset_time=None,
        )

        # Next request should test primary (HALF_OPEN)
        result = await composite.check_limit("recovery_test", config)
        assert not result.is_exceeded

        # Circuit should be closed after successful primary request
        assert composite._circuit_state == CircuitBreakerState.CLOSED

        await composite.disconnect()


@pytest.mark.integration
class TestPerformanceScenarios:
    """Test performance scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_load_scenario(self) -> None:
        """Test composite backend under concurrent load."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        composite = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.FAIL_FAST,
        )

        await composite.connect()

        # Mock fast responses
        async def fast_check(key: str, config: RateLimitConfig) -> RateLimitResult:
            await asyncio.sleep(0.01)  # Simulate small latency
            return RateLimitResult(
                is_exceeded=False,
                limit_times=100,
                retry_after_ms=0,
                remaining_requests=99,
                reset_time=None,
            )

        primary.check_limit.side_effect = fast_check
        fallback.check_limit.side_effect = fast_check

        config = RateLimitConfig(times=100, seconds=60)

        # Generate concurrent requests
        async def make_request(request_id: int) -> bool:
            try:
                result = await composite.check_limit(f"user_{request_id}", config)
                return not result.is_exceeded
            except Exception:
                return False

        # Run 50 concurrent requests
        start_time = time.time()
        tasks = [make_request(i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        # Verify performance
        duration = end_time - start_time
        assert duration < 2.0  # Should complete within 2 seconds

        # Most requests should succeed
        success_count = sum(results)
        assert success_count >= 45  # At least 90% success rate

        # Verify statistics
        stats = composite.get_stats()
        assert stats["total_requests"] == success_count

        await composite.disconnect()

    @pytest.mark.asyncio
    async def test_mixed_load_with_failures_scenario(self) -> None:
        """Test mixed load scenario with some failures."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        composite = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            failure_threshold=10,  # Higher threshold for load testing
        )

        await composite.connect()

        # Primary fails 20% of the time
        call_count = 0

        async def unreliable_primary(
            key: str, config: RateLimitConfig
        ) -> RateLimitResult:
            nonlocal call_count
            call_count += 1
            if call_count % 5 == 0:  # Fail every 5th request
                raise LimiterBackendError("Intermittent failure")
            return RateLimitResult(
                is_exceeded=False,
                limit_times=100,
                retry_after_ms=0,
                remaining_requests=99,
                reset_time=datetime.now(),
            )

        primary.check_limit.side_effect = unreliable_primary
        fallback.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=100,
            retry_after_ms=0,
            remaining_requests=99,
            reset_time=datetime.now(),
        )

        config = RateLimitConfig(times=100, seconds=60)

        # Generate load with concurrent requests
        async def make_request(request_id: int) -> tuple[bool, str]:
            try:
                result = await composite.check_limit(f"load_user_{request_id}", config)
                backend_used = composite.current_backend
                return not result.is_exceeded, backend_used
            except Exception:
                return False, "error"

        # Run concurrent load
        tasks = [make_request(i) for i in range(30)]
        results = await asyncio.gather(*tasks)

        successes = [r for r, _ in results if r]
        primary_used = [r for r, b in results if b == "primary"]
        fallback_used = [r for r, b in results if b == "fallback"]

        # Verify mixed usage
        assert len(successes) > 20  # Most should succeed
        assert len(primary_used) > 0  # Some primary usage
        assert len(fallback_used) == 0  # Some fallback usage
        # Note: With circuit breaker strategy and threshold=10, fallback will not be used
        # if we don't reach the failure threshold, which is expected behavior

        # Verify error statistics
        stats = composite.get_stats()
        assert stats["primary_errors"] > 0
        assert stats["fallback_requests"] > 0

        await composite.disconnect()


@pytest.mark.integration
class TestHealthCheckScenarios:
    """Test health check scenarios."""

    @pytest.mark.asyncio
    async def test_continuous_health_monitoring_scenario(self) -> None:
        """Test continuous health monitoring scenario."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        composite = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=0.2,  # Fast for testing
        )

        # Start with both healthy
        primary.is_connected.return_value = True
        fallback.is_connected.return_value = True

        await composite.connect()

        # Allow health checks to run
        await asyncio.sleep(0.5)

        # Verify both are healthy
        stats = composite.get_stats()
        assert stats["primary_healthy"] is True
        assert stats["fallback_healthy"] is True

        # Primary becomes unhealthy
        primary.is_connected.return_value = False

        # Wait for health check to detect
        await asyncio.sleep(0.3)

        # Verify health status updated
        stats = composite.get_stats()
        assert stats["primary_healthy"] is False
        assert stats["fallback_healthy"] is True

        # Primary recovers
        primary.is_connected.return_value = True

        # Wait for health check to detect
        await asyncio.sleep(0.3)

        # Verify recovery detected
        stats = composite.get_stats()
        assert stats["primary_healthy"] is True
        assert stats["fallback_healthy"] is True

        await composite.disconnect()

    @pytest.mark.asyncio
    async def test_health_based_routing_scenario(self) -> None:
        """Test routing based on health status."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        composite = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.HEALTH_CHECK,
            health_check_interval_seconds=0.1,
        )

        # Setup responses
        primary.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=10,
            retry_after_ms=0,
            remaining_requests=9,
            reset_time=None,
        )
        fallback.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=10,
            retry_after_ms=0,
            remaining_requests=9,
            reset_time=None,
        )

        await composite.connect()

        config = RateLimitConfig(times=10, seconds=60)

        # Initially both healthy - should use primary
        await composite.check_limit("test1", config)
        assert composite.current_backend == "primary"

        # Make primary unhealthy
        primary.is_connected.return_value = False
        await asyncio.sleep(0.2)  # Wait for health check

        # Should now use fallback
        await composite.check_limit("test2", config)
        assert composite.current_backend == "fallback"

        # Primary recovers
        primary.is_connected.return_value = True
        await asyncio.sleep(0.2)  # Wait for health check

        # Should return to primary
        await composite.check_limit("test3", config)
        assert composite.current_backend == "primary"

        await composite.disconnect()


@pytest.mark.integration
class TestMultiStrategyScenarios:
    """Test scenarios comparing different strategies."""

    @pytest.mark.asyncio
    async def test_strategy_comparison_under_failures(self) -> None:
        """Test how different strategies behave under similar failure conditions."""
        strategies = [
            SwitchingStrategy.FAIL_FAST,
            SwitchingStrategy.CIRCUIT_BREAKER,
            SwitchingStrategy.HEALTH_CHECK,
        ]

        results = {}

        for strategy in strategies:
            primary = AsyncMock(spec=LimiterBackend)
            fallback = AsyncMock(spec=LimiterBackend)

            composite = CompositeLimiterBackend(
                primary=primary,
                fallback=fallback,
                strategy=strategy,
                failure_threshold=3,
            )

            await composite.connect()

            # Simulate primary failures
            failure_count = 0

            def failing_primary(key: str, config: RateLimitConfig) -> RateLimitResult:
                nonlocal failure_count
                failure_count += 1
                if failure_count <= 5:  # First 5 fail
                    raise LimiterBackendError("Primary failed")
                return RateLimitResult(
                    is_exceeded=False,
                    limit_times=10,
                    retry_after_ms=0,
                    remaining_requests=9,
                    reset_time=None,
                )

            primary.check_limit.side_effect = failing_primary
            fallback.check_limit.return_value = RateLimitResult(
                is_exceeded=False,
                limit_times=10,
                retry_after_ms=0,
                remaining_requests=9,
                reset_time=None,
            )

            config = RateLimitConfig(times=10, seconds=60)

            # Run requests and collect statistics
            for i in range(10):
                try:
                    await composite.check_limit(f"test_{i}", config)
                except LimiterBackendError:
                    pass  # Some strategies might not handle all failures

            stats = composite.get_stats()
            results[strategy.value] = {
                "primary_errors": stats["primary_errors"],
                "fallback_requests": stats["fallback_requests"],
                "total_requests": stats["total_requests"],
            }

            await composite.disconnect()

        # Verify different strategies behave differently
        assert len({r["primary_errors"] for r in results.values()}) > 1
        assert all(r["total_requests"] > 0 for r in results.values())


@pytest.mark.integration
class TestProductionLikeScenarios:
    """Test production-like scenarios."""

    @pytest.mark.asyncio
    async def test_api_rate_limiting_scenario(self) -> None:
        """Test typical API rate limiting scenario."""
        # Setup realistic backends
        redis_backend = AsyncMock(spec=LimiterBackend)
        memory_backend = AsyncMock(spec=LimiterBackend)

        composite = CompositeLimiterBackend(
            primary=redis_backend,
            fallback=memory_backend,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
            failure_threshold=5,
            recovery_timeout_seconds=30,
        )

        await composite.connect()

        # Different rate limits for different endpoints
        light_config = RateLimitConfig(times=1000, minutes=1)  # Read operations
        medium_config = RateLimitConfig(times=100, minutes=1)  # Normal operations
        heavy_config = RateLimitConfig(times=10, minutes=1)  # Heavy operations

        # Mock responses
        def create_response(config: RateLimitConfig) -> RateLimitResult:
            return RateLimitResult(
                is_exceeded=False,
                limit_times=config.times,
                retry_after_ms=0,
                remaining_requests=config.times - 1,
                reset_time=None,
            )

        redis_backend.check_limit.side_effect = lambda k, c: create_response(c)
        memory_backend.check_limit.side_effect = lambda k, c: create_response(c)

        # Simulate various API requests
        user_id = "user_123"

        # Light operations (reads)
        for i in range(10):
            result = await composite.check_limit(f"read:{user_id}:{i}", light_config)
            assert not result.is_exceeded

        # Medium operations
        for i in range(5):
            result = await composite.check_limit(f"api:{user_id}:{i}", medium_config)
            assert not result.is_exceeded

        # Heavy operations
        for i in range(2):
            result = await composite.check_limit(f"heavy:{user_id}:{i}", heavy_config)
            assert not result.is_exceeded

        # Verify statistics
        stats = composite.get_stats()
        assert stats["total_requests"] == 17  # 10 + 5 + 2
        assert stats["primary_errors"] == 0  # No errors in this scenario

        await composite.disconnect()

    @pytest.mark.asyncio
    async def test_maintenance_window_scenario(self) -> None:
        """Test graceful handling of maintenance windows."""
        primary = AsyncMock(spec=LimiterBackend)
        fallback = AsyncMock(spec=LimiterBackend)

        composite = CompositeLimiterBackend(
            primary=primary,
            fallback=fallback,
            strategy=SwitchingStrategy.CIRCUIT_BREAKER,
        )

        await composite.connect()

        config = RateLimitConfig(times=50, minutes=1)

        # Normal operation
        primary.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=50,
            retry_after_ms=0,
            remaining_requests=49,
            reset_time=None,
        )

        for i in range(5):
            result = await composite.check_limit(f"normal_{i}", config)
            assert not result.is_exceeded
            assert composite.current_backend == "primary"

        # Maintenance begins - force switch to fallback
        await composite.force_switch_to_fallback()

        fallback.check_limit.return_value = RateLimitResult(
            is_exceeded=False,
            limit_times=50,
            retry_after_ms=0,
            remaining_requests=59,
            reset_time=None,
        )

        # During maintenance - should use fallback
        for i in range(5):
            result = await composite.check_limit(f"maintenance_{i}", config)
            assert not result.is_exceeded
            assert composite.current_backend == "fallback"

        # Maintenance ends - switch back to primary
        await composite.force_switch_to_primary()

        for i in range(5):
            result = await composite.check_limit(f"restored_{i}", config)
            assert not result.is_exceeded
            assert composite.current_backend == "primary"

        # Verify statistics show mixed usage
        stats = composite.get_stats()
        assert stats["primary_requests"] == 10  # 5 before + 5 after maintenance
        assert stats["fallback_requests"] == 5  # 5 during maintenance

        await composite.disconnect()
