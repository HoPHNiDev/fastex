"""Test coverage verification for Redis backend module."""

from pathlib import Path

import pytest


def test_import_all_redis_modules():
    """Test that all Redis backend modules can be imported successfully."""
    try:
        # Core module imports
        # Verify __all__ exports
        import fastex.limiter.backend.redis as redis_module
        from fastex.limiter.backend.redis.redis import RedisLimiterBackend
        from fastex.limiter.backend.redis.schemas import (
            RedisLimiterBackendConnectConfig,
        )

        # Script imports
        from fastex.limiter.backend.redis.scripts.interface import LuaScript
        from fastex.limiter.backend.redis.scripts.scripts import (
            FIXED_WINDOW_SCRIPT,
            SLIDING_WINDOW_SCRIPT,
            FileBasedScript,
            FixedWindowScript,
            SlidingWindowScript,
        )

        assert redis_module is not None
        assert RedisLimiterBackend is not None
        assert RedisLimiterBackendConnectConfig is not None
        assert LuaScript is not None
        assert FIXED_WINDOW_SCRIPT is not None
        assert SLIDING_WINDOW_SCRIPT is not None
        assert FileBasedScript is not None
        assert FixedWindowScript is not None
        assert SlidingWindowScript is not None

        expected_exports = [
            "RedisLimiterBackend",
            "LuaScript",
            "SlidingWindowScript",
            "FixedWindowScript",
            "FileBasedScript",
        ]

        for export in expected_exports:
            assert hasattr(redis_module, export), f"Missing export: {export}"

    except ImportError as e:
        pytest.fail(f"Failed to import Redis backend modules: {e}")


def test_coverage_requirements():
    """Verify that comprehensive test coverage is in place."""
    test_dir = Path(__file__).parent.parent

    required_test_files = [
        "unit/limiter/backend/redis/test_redis_backend.py",
        "unit/limiter/backend/redis/test_schemas.py",
        "unit/limiter/backend/redis/scripts/test_interface.py",
        "unit/limiter/backend/redis/scripts/test_scripts.py",
        "integration/limiter/backend/redis/test_redis_integration.py",
    ]

    missing_files = []
    for test_file in required_test_files:
        full_path = test_dir / test_file
        if not full_path.exists():
            missing_files.append(test_file)

    if missing_files:
        pytest.fail(f"Missing required test files: {missing_files}")
