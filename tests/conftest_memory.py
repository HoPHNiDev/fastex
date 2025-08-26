"""Pytest configuration and fixtures specifically for memory backend tests."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from fastex.limiter.backend.enums import FallbackMode
from fastex.limiter.backend.memory.memory import InMemoryLimiterBackend
from fastex.limiter.backend.memory.schemas import MemoryLimiterBackendConnectConfig


@pytest.fixture
def memory_backend() -> InMemoryLimiterBackend:
    """Create a memory backend instance for testing."""
    return InMemoryLimiterBackend()


@pytest.fixture
def memory_config() -> MemoryLimiterBackendConnectConfig:
    """Create a test configuration for memory backend."""
    return MemoryLimiterBackendConnectConfig(
        cleanup_interval_seconds=300, max_keys=10000, fallback_mode=FallbackMode.ALLOW
    )


@pytest.fixture
def memory_config_fast_cleanup() -> MemoryLimiterBackendConnectConfig:
    """Create a test configuration with fast cleanup for testing."""
    return MemoryLimiterBackendConnectConfig(
        cleanup_interval_seconds=1,  # Very fast for testing
        max_keys=100,
        fallback_mode=FallbackMode.ALLOW,
    )


@pytest.fixture
def memory_config_small_capacity() -> MemoryLimiterBackendConnectConfig:
    """Create a test configuration with small capacity for memory protection testing."""
    return MemoryLimiterBackendConnectConfig(
        cleanup_interval_seconds=300,
        max_keys=5,  # Small for testing memory protection
        fallback_mode=FallbackMode.DENY,
    )


@pytest_asyncio.fixture
async def connected_memory_backend(
    memory_backend: InMemoryLimiterBackend,
    memory_config: MemoryLimiterBackendConnectConfig,
) -> AsyncGenerator[InMemoryLimiterBackend, None]:
    """Create a connected memory backend for testing."""
    await memory_backend.connect(memory_config)
    yield memory_backend
    try:
        await memory_backend.disconnect()
    except Exception:
        pass  # Ignore cleanup errors


@pytest_asyncio.fixture
async def connected_memory_backend_fast_cleanup(
    memory_backend: InMemoryLimiterBackend,
    memory_config_fast_cleanup: MemoryLimiterBackendConnectConfig,
) -> AsyncGenerator[InMemoryLimiterBackend, None]:
    """Create a connected memory backend with fast cleanup for testing."""
    await memory_backend.connect(memory_config_fast_cleanup)
    yield memory_backend
    try:
        await memory_backend.disconnect()
    except Exception:
        pass  # Ignore cleanup errors


@pytest_asyncio.fixture
async def connected_memory_backend_small_capacity(
    memory_backend: InMemoryLimiterBackend,
    memory_config_small_capacity: MemoryLimiterBackendConnectConfig,
) -> AsyncGenerator[InMemoryLimiterBackend, None]:
    """Create a connected memory backend with small capacity for testing."""
    await memory_backend.connect(memory_config_small_capacity)
    yield memory_backend
    try:
        await memory_backend.disconnect()
    except Exception:
        pass  # Ignore cleanup errors
