import asyncio
import time
from typing import Any, overload

from fastex.limiter.backend.composite.enums import (
    CircuitBreakerState,
    SwitchingStrategy,
)
from fastex.limiter.backend.exceptions import LimiterBackendError
from fastex.limiter.backend.interfaces import (
    LimiterBackend,
    LimiterBackendConnectConfig,
)
from fastex.limiter.backend.schemas import RateLimitResult
from fastex.limiter.schemas import RateLimitConfig
from fastex.logging.logger import FastexLogger


class CompositeLimiterBackend(LimiterBackend):
    """
    Composite backend that provides high availability through primary/fallback pattern.

    Features:
    - Primary/fallback backend switching
    - Circuit breaker pattern for resilience
    - Health checking capabilities
    - Automatic recovery attempts
    - Detailed error handling and logging
    - Configurable switching strategies

    Use cases:
    - High availability rate limiting
    - Graceful degradation (Redis -> In-memory)
    - Multi-region deployments
    - Development/production environment switching
    """

    logger = FastexLogger("CompositeLimiterBackend")

    def __init__(
        self,
        primary: LimiterBackend,
        fallback: LimiterBackend,
        strategy: SwitchingStrategy = SwitchingStrategy.CIRCUIT_BREAKER,
        failure_threshold: int = 5,
        recovery_timeout_seconds: int = 60,
        health_check_interval_seconds: float = 30,
    ) -> None:
        """
        Initialize composite backend.

        Args:
            primary: Primary backend (e.g., Redis)
            fallback: Fallback backend (e.g., In-memory)
            strategy: Strategy for switching between backends
            failure_threshold: Number of failures before switching (circuit breaker)
            recovery_timeout_seconds: Time to wait before trying primary again
            health_check_interval_seconds: Interval for health checks
        """
        if isinstance(primary, CompositeLimiterBackend) or isinstance(
            fallback, CompositeLimiterBackend
        ):
            raise LimiterBackendError(
                "Nested CompositeLimiterBackend instances are not allowed"
            )

        self._primary = primary
        self._fallback = fallback
        self._strategy = strategy
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_seconds
        self._health_check_interval = health_check_interval_seconds

        # Circuit breaker state
        self._circuit_state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._last_success_time: float | None = None

        # Health checking
        self._health_check_task: asyncio.Task[Any] | None = None
        self._primary_healthy = True
        self._fallback_healthy = True

        # Statistics
        self._primary_requests = 0
        self._fallback_requests = 0
        self._primary_errors = 0
        self._fallback_errors = 0

        self._connected = False

    @overload
    async def connect(
        self,
        primary_config: LimiterBackendConnectConfig,
        fallback_config: LimiterBackendConnectConfig,
    ) -> None: ...

    @overload
    async def connect(self) -> None: ...

    async def connect(
        self,
        primary_config: LimiterBackendConnectConfig | None = None,
        fallback_config: LimiterBackendConnectConfig | None = None,
    ) -> None:
        """
        Connect both primary and fallback backends.

        Args:
            *args, **kwargs: Arguments passed to both backends
        """
        primary_connected = False
        fallback_connected = False

        # Try to connect primary backend
        try:
            await self._primary.connect(config=primary_config)
            primary_connected = True
            self._primary_healthy = True
            self.logger.debug("Primary backend connected successfully")
        except Exception as e:
            self.logger.warning(f"Failed to connect primary backend: {e}")
            self._primary_healthy = False
            self._circuit_state = CircuitBreakerState.OPEN

        # Try to connect fallback backend
        try:
            await self._fallback.connect(config=fallback_config)
            fallback_connected = True
            self._fallback_healthy = True
            self.logger.debug("Fallback backend connected successfully")
        except Exception as e:
            self.logger.warning(f"Failed to connect fallback backend: {e}")
            self._fallback_healthy = False

        # At least one backend must be connected
        if not primary_connected and not fallback_connected:
            raise LimiterBackendError(
                "Failed to connect to both primary and fallback backends"
            )

        self._connected = True

        # Start health checking if enabled
        if self._strategy == SwitchingStrategy.HEALTH_CHECK:
            self._health_check_task = asyncio.create_task(self._health_check_loop())

        self.logger.info(
            f"CompositeLimiterBackend connected - "
            f"primary: {'✓' if primary_connected else '✗'}, "
            f"fallback: {'✓' if fallback_connected else '✗'}, "
            f"strategy: {self._strategy.value}"
        )

    async def disconnect(self) -> None:
        """Disconnect both backends and cleanup resources."""
        self._connected = False

        # Stop health checking
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Disconnect backends
        disconnect_tasks = []
        if self._primary:
            disconnect_tasks.append(self._safe_disconnect(self._primary, "primary"))
        if self._fallback:
            disconnect_tasks.append(self._safe_disconnect(self._fallback, "fallback"))

        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)

        self.logger.debug("CompositeLimiterBackend disconnected")

    async def _safe_disconnect(self, backend: LimiterBackend, name: str) -> None:
        """Safely disconnect a backend with error handling."""
        try:
            await backend.disconnect()
            self.logger.debug(f"{name} backend disconnected")
        except Exception as e:
            self.logger.warning(f"Error disconnecting {name} backend: {e}")

    async def check_limit(self, key: str, config: RateLimitConfig) -> RateLimitResult:
        """
        Check rate limit using appropriate backend based on strategy.

        Args:
            key: Unique identifier for rate limiting
            config: Rate limit configuration

        Returns:
            RateLimitResult from the active backend

        Raises:
            LimiterBackendError: If both backends fail
        """
        if not self._connected:
            raise LimiterBackendError("Composite backend is not connected")

        backend = self._select_backend()
        backend_name = "primary" if backend == self._primary else "fallback"

        try:
            result = await backend.check_limit(key, config)
            await self._record_success(backend)

            # Update statistics
            if backend == self._primary:
                self._primary_requests += 1
            else:
                self._fallback_requests += 1

            self.logger.debug(
                f"Rate limit check successful using {backend_name} backend"
            )
            return result

        except Exception as e:
            await self._record_failure(backend, e)

            # Update error statistics
            if backend == self._primary:
                self._primary_errors += 1
            else:
                self._fallback_errors += 1

            self.logger.warning(f"{backend_name} backend failed: {e}")

            # Try the other backend if available
            other_backend = (
                self._fallback if backend == self._primary else self._primary
            )
            other_name = "fallback" if backend == self._primary else "primary"

            if self._is_backend_available(other_backend):
                try:
                    result = await other_backend.check_limit(key, config)
                    self.logger.info(
                        f"Successfully used {other_name} backend after {backend_name} failure"
                    )

                    # Update statistics for successful fallback
                    if other_backend == self._primary:
                        self._primary_requests += 1
                    else:
                        self._fallback_requests += 1

                    return result
                except Exception as fallback_error:
                    self.logger.error(
                        f"Both backends failed: {backend_name}={e}, {other_name}={fallback_error}"
                    )
                    raise LimiterBackendError(
                        f"Both backends failed: primary={e}, fallback={fallback_error}"
                    )
            else:
                self.logger.error(
                    f"No healthy backend available after {backend_name} failure"
                )
                raise LimiterBackendError(
                    f"{backend_name} backend failed and no healthy alternative: {e}"
                )

    def _select_backend(self) -> LimiterBackend:
        """Select appropriate backend based on current strategy and state."""
        match self._strategy:
            case SwitchingStrategy.FAIL_FAST:
                return self._select_fail_fast()
            case SwitchingStrategy.CIRCUIT_BREAKER:
                return self._select_circuit_breaker()
            case SwitchingStrategy.HEALTH_CHECK:
                return self._select_health_check()
            case _:
                raise LimiterBackendError(
                    f"Unknown switching strategy: {self._strategy}"
                )

    def _select_fail_fast(self) -> LimiterBackend:
        """Select backend for fail-fast strategy."""
        if self._is_backend_available(self._primary):
            return self._primary
        elif self._is_backend_available(self._fallback):
            return self._fallback
        else:
            # Return primary and let error handling deal with it
            return self._primary

    def _select_circuit_breaker(self) -> LimiterBackend:
        """Select backend for circuit breaker strategy."""
        match self._circuit_state:
            case CircuitBreakerState.CLOSED:
                return self._primary
            case CircuitBreakerState.OPEN:
                # Check if we should try primary again
                if (
                    self._last_failure_time
                    and time.time() - self._last_failure_time >= self._recovery_timeout
                ):
                    self._circuit_state = CircuitBreakerState.HALF_OPEN
                    self.logger.info("Circuit breaker moving to HALF_OPEN state")
                    return self._primary
                return self._fallback
            case CircuitBreakerState.HALF_OPEN:
                return self._primary
            case _:
                raise LimiterBackendError(
                    f"Unknown circuit state: {self._circuit_state}"
                )

    def _select_health_check(self) -> LimiterBackend:
        """Select backend for health check strategy."""
        if self._primary_healthy and self._is_backend_available(self._primary):
            return self._primary
        elif self._fallback_healthy and self._is_backend_available(self._fallback):
            return self._fallback
        else:
            # Prefer primary if both are unhealthy
            return self._primary

    @staticmethod
    def _is_backend_available(backend: LimiterBackend | None) -> bool:
        """Check if backend is available for use."""
        if backend is None:
            return False
        return backend.is_connected()

    async def _record_success(self, backend: LimiterBackend) -> None:
        """Record successful operation for circuit breaker logic."""
        self._last_success_time = time.time()

        if backend == self._primary:
            if self._circuit_state == CircuitBreakerState.HALF_OPEN:
                # Primary is working again, close the circuit
                self._circuit_state = CircuitBreakerState.CLOSED
                self._failure_count = 0
                self.logger.info("Circuit breaker CLOSED - primary backend recovered")
            elif self._circuit_state == CircuitBreakerState.CLOSED:
                # Reset failure count on successful primary operation
                self._failure_count = 0

    async def _record_failure(self, backend: LimiterBackend, error: Exception) -> None:
        """Record failed operation for circuit breaker logic."""
        self._last_failure_time = time.time()

        if (
            backend == self._primary
            and self._strategy == SwitchingStrategy.CIRCUIT_BREAKER
        ):
            self._failure_count += 1

            if (
                self._circuit_state == CircuitBreakerState.CLOSED
                and self._failure_count >= self._failure_threshold
            ):
                # Open the circuit
                self._circuit_state = CircuitBreakerState.OPEN
                self.logger.warning(
                    f"Circuit breaker OPENED after {self._failure_count} failures. "
                    f"Will retry primary backend in {self._recovery_timeout} seconds"
                )
            elif self._circuit_state == CircuitBreakerState.HALF_OPEN:
                # Failed during testing, go back to open
                self._circuit_state = CircuitBreakerState.OPEN
                self.logger.warning(
                    "Circuit breaker back to OPEN state after failed test"
                )

    async def _health_check_loop(self) -> None:
        """Background health checking loop."""
        while self._connected:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._perform_health_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check loop: {e}")

    async def _perform_health_checks(self) -> None:
        """Perform health checks on both backends."""
        # Check primary backend
        try:
            self._primary_healthy = self._primary.is_connected()
            if not self._primary_healthy:
                self.logger.debug("Primary backend health check failed - not connected")
        except Exception as e:
            self._primary_healthy = False
            self.logger.debug(f"Primary backend health check failed: {e}")

        # Check fallback backend
        try:
            self._fallback_healthy = self._fallback.is_connected()
            if not self._fallback_healthy:
                self.logger.debug(
                    "Fallback backend health check failed - not connected"
                )
        except Exception as e:
            self._fallback_healthy = False
            self.logger.debug(f"Fallback backend health check failed: {e}")

        self.logger.debug(
            f"Health check completed - primary: {'✓' if self._primary_healthy else '✗'}, "
            f"fallback: {'✓' if self._fallback_healthy else '✗'}"
        )

    def is_connected(self, raise_exc: bool = False) -> bool:
        """
        Check if at least one backend is connected.

        Args:
            raise_exc: Whether to raise exception if not connected

        Returns:
            True if at least one backend is connected

        Raises:
            LimiterBackendError: If no backends are connected and raise_exc=True
        """
        primary_connected = self._is_backend_available(self._primary)
        fallback_connected = self._is_backend_available(self._fallback)

        connected = self._connected and (primary_connected or fallback_connected)

        if not connected and raise_exc:
            raise LimiterBackendError("No backends are connected")

        return connected

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive statistics for monitoring."""
        return {
            "strategy": self._strategy.value,
            "circuit_state": self._circuit_state.value,
            "primary_healthy": self._primary_healthy,
            "fallback_healthy": self._fallback_healthy,
            "primary_connected": self._is_backend_available(self._primary),
            "fallback_connected": self._is_backend_available(self._fallback),
            "failure_count": self._failure_count,
            "last_failure_seconds_ago": (
                int(time.time() - self._last_failure_time)
                if self._last_failure_time
                else None
            ),
            "last_success_seconds_ago": (
                int(time.time() - self._last_success_time)
                if self._last_success_time
                else None
            ),
            "primary_requests": self._primary_requests,
            "fallback_requests": self._fallback_requests,
            "primary_errors": self._primary_errors,
            "fallback_errors": self._fallback_errors,
            "total_requests": self._primary_requests + self._fallback_requests,
            "total_errors": self._primary_errors + self._fallback_errors,
        }

    async def force_switch_to_primary(self) -> None:
        """Force switch back to primary backend (for manual recovery)."""
        if self._strategy == SwitchingStrategy.CIRCUIT_BREAKER:
            self._circuit_state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self.logger.info("Manually forced switch to primary backend")

    async def force_switch_to_fallback(self) -> None:
        """Force switch to fallback backend (for maintenance)."""
        if self._strategy == SwitchingStrategy.CIRCUIT_BREAKER:
            self._circuit_state = CircuitBreakerState.OPEN
            self.logger.info("Manually forced switch to fallback backend")

    @property
    def current_backend(self) -> str:
        """Get name of currently selected backend."""
        try:
            backend = self._select_backend()
            return "primary" if backend == self._primary else "fallback"
        except Exception as e:
            self.logger.error(f"Error determining current backend: {e}")
            return "unknown"

    @property
    def primary_backend(self) -> LimiterBackend:
        """Get primary backend instance."""
        return self._primary

    @property
    def fallback_backend(self) -> LimiterBackend:
        """Get fallback backend instance."""
        return self._fallback
