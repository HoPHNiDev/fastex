"""Unit tests for Lua script implementations."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from fastex.limiter.backend.redis.scripts.interface import LuaScript
from fastex.limiter.backend.redis.scripts.scripts import (
    FIXED_WINDOW_SCRIPT,
    SLIDING_WINDOW_SCRIPT,
    FileBasedScript,
    FixedWindowScript,
    SlidingWindowScript,
)


class TestFixedWindowScript:
    """Test the FixedWindowScript implementation."""

    def test_inheritance(self) -> None:
        """Test that FixedWindowScript properly inherits from LuaScript."""
        script = FixedWindowScript()
        assert isinstance(script, LuaScript)

    def test_get_script_returns_correct_script(self) -> None:
        """Test that get_script returns the correct Lua script."""
        script = FixedWindowScript()
        result = script.get_script()

        assert result == FIXED_WINDOW_SCRIPT
        assert isinstance(result, str)
        assert len(result) > 0

    def test_extra_params_returns_empty_list(self) -> None:
        """Test that extra_params returns an empty list."""
        script = FixedWindowScript()
        result = script.extra_params()

        assert result == []
        assert isinstance(result, list)

    def test_parse_result_with_valid_input(self) -> None:
        """Test parse_result with valid input."""
        script = FixedWindowScript()

        # Test case: no limit exceeded
        result = script.parse_result([0, 5])
        assert result == (0, 5)
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

        # Test case: limit exceeded
        result = script.parse_result([1000, 10])
        assert result == (1000, 10)

    def test_parse_result_with_string_numbers(self) -> None:
        """Test parse_result with string representations of numbers."""
        script = FixedWindowScript()

        result = script.parse_result(["500", "15"])
        assert result == (500, 15)
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_parse_result_with_float_numbers(self) -> None:
        """Test parse_result with float numbers (should convert to int)."""
        script = FixedWindowScript()

        result = script.parse_result([100.5, 7.9])
        assert result == (100, 7)
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_parse_result_error_handling(self) -> None:
        """Test parse_result error handling with invalid input."""
        script = FixedWindowScript()

        # Test with non-numeric strings
        with pytest.raises(ValueError):
            script.parse_result(["invalid", "data"])

        # Test with insufficient data
        with pytest.raises(IndexError):
            script.parse_result([])

        with pytest.raises(IndexError):
            script.parse_result([100])

    def test_script_content_validation(self) -> None:
        """Test that the fixed window script contains expected Lua code."""
        script_content = FIXED_WINDOW_SCRIPT

        # Check for key Lua script elements
        assert "local key = KEYS[1]" in script_content
        assert "local limit = tonumber(ARGV[1])" in script_content
        assert "local window_ms = tonumber(ARGV[2])" in script_content
        assert "redis.call('GET', key)" in script_content
        assert "redis.call('SET', key" in script_content
        assert "redis.call('INCR', key)" in script_content
        assert "redis.call('PTTL', key)" in script_content


class TestSlidingWindowScript:
    """Test the SlidingWindowScript implementation."""

    def test_inheritance(self) -> None:
        """Test that SlidingWindowScript properly inherits from LuaScript."""
        script = SlidingWindowScript()
        assert isinstance(script, LuaScript)

    def test_get_script_returns_correct_script(self) -> None:
        """Test that get_script returns the correct Lua script."""
        script = SlidingWindowScript()
        result = script.get_script()

        assert result == SLIDING_WINDOW_SCRIPT
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("time.time")
    def test_extra_params_returns_current_timestamp(self, mock_time) -> None:
        """Test that extra_params returns current timestamp in milliseconds."""
        mock_time.return_value = 1640995200.123

        script = SlidingWindowScript()
        result = script.extra_params()

        expected_timestamp = int(1640995200.123 * 1000)
        assert result == [expected_timestamp]
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], int)

    def test_extra_params_returns_realistic_timestamp(self) -> None:
        """Test that extra_params returns a realistic current timestamp."""
        script = SlidingWindowScript()
        result = script.extra_params()

        assert len(result) == 1
        # Check that the timestamp is realistic (after 2020 and before 2030)
        timestamp = result[0]
        assert 1577836800000 < timestamp < 1893456000000  # 2020-2030 range

    def test_parse_result_with_valid_input(self) -> None:
        """Test parse_result with valid input."""
        script = SlidingWindowScript()

        # Test case: no limit exceeded
        result = script.parse_result([0, 3])
        assert result == (0, 3)
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

        # Test case: limit exceeded
        result = script.parse_result([2500, 10])
        assert result == (2500, 10)

    def test_parse_result_with_string_numbers(self) -> None:
        """Test parse_result with string representations of numbers."""
        script = SlidingWindowScript()

        result = script.parse_result(["1500", "8"])
        assert result == (1500, 8)
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_parse_result_error_handling(self) -> None:
        """Test parse_result error handling with invalid input."""
        script = SlidingWindowScript()

        # Test with non-numeric strings
        with pytest.raises(ValueError):
            script.parse_result(["invalid", "data"])

        # Test with insufficient data
        with pytest.raises(IndexError):
            script.parse_result([])

        with pytest.raises(IndexError):
            script.parse_result([100])

    def test_script_content_validation(self) -> None:
        """Test that the sliding window script contains expected Lua code."""
        script_content = SLIDING_WINDOW_SCRIPT

        # Check for key Lua script elements
        assert "local key = KEYS[1]" in script_content
        assert "local limit = tonumber(ARGV[1])" in script_content
        assert "local window_ms = tonumber(ARGV[2])" in script_content
        assert "local now = tonumber(ARGV[3])" in script_content
        assert "redis.call('ZREMRANGEBYSCORE'" in script_content
        assert "redis.call('ZCARD', key)" in script_content
        assert "redis.call('ZADD', key" in script_content
        assert "redis.call('EXPIRE', key" in script_content
        assert "redis.call('ZRANGE', key" in script_content


class TestFileBasedScript:
    """Test the FileBasedScript implementation."""

    def test_inheritance(self) -> None:
        """Test that FileBasedScript properly inherits from LuaScript."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write("return {0, 1}")
            temp_path = f.name

        try:
            script = FileBasedScript(temp_path)
            assert isinstance(script, LuaScript)
        finally:
            Path(temp_path).unlink()

    def test_init_with_string_path(self) -> None:
        """Test initialization with string path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write("test script content")
            temp_path = f.name

        try:
            script = FileBasedScript(temp_path)
            assert script.script_path == Path(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_init_with_path_object(self) -> None:
        """Test initialization with Path object."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write("test script content")
            temp_path = Path(f.name)

        try:
            script = FileBasedScript(temp_path)
            assert script.script_path == temp_path
        finally:
            temp_path.unlink()

    def test_get_script_reads_file_content(self) -> None:
        """Test that get_script reads and returns file content."""
        test_content = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        return {0, 1}
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            script = FileBasedScript(temp_path)
            result = script.get_script()
            assert result == test_content
        finally:
            Path(temp_path).unlink()

    def test_get_script_with_empty_file(self) -> None:
        """Test get_script with empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            script = FileBasedScript(temp_path)
            result = script.get_script()
            assert result == ""
        finally:
            Path(temp_path).unlink()

    def test_get_script_file_not_found_error(self) -> None:
        """Test get_script raises FileNotFoundError for non-existent file."""
        script = FileBasedScript("non_existent_file.lua")

        with pytest.raises(FileNotFoundError):
            script.get_script()

    def test_extra_params_returns_empty_list(self) -> None:
        """Test that extra_params returns an empty list."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write("return {0, 1}")
            temp_path = f.name

        try:
            script = FileBasedScript(temp_path)
            result = script.extra_params()
            assert result == []
            assert isinstance(result, list)
        finally:
            Path(temp_path).unlink()

    def test_parse_result_with_valid_input(self) -> None:
        """Test parse_result with valid input."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write("return {0, 1}")
            temp_path = f.name

        try:
            script = FileBasedScript(temp_path)

            # Test case: no limit exceeded
            result = script.parse_result([0, 4])
            assert result == (0, 4)
            assert isinstance(result[0], int)
            assert isinstance(result[1], int)

            # Test case: limit exceeded
            result = script.parse_result([3000, 12])
            assert result == (3000, 12)
        finally:
            Path(temp_path).unlink()

    def test_parse_result_error_handling(self) -> None:
        """Test parse_result error handling with invalid input."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write("return {0, 1}")
            temp_path = f.name

        try:
            script = FileBasedScript(temp_path)

            # Test with non-numeric strings
            with pytest.raises(ValueError):
                script.parse_result(["invalid", "data"])

            # Test with insufficient data
            with pytest.raises(IndexError):
                script.parse_result([])
        finally:
            Path(temp_path).unlink()


class TestScriptConstants:
    """Test the script constants themselves."""

    def test_fixed_window_script_is_string(self) -> None:
        """Test that FIXED_WINDOW_SCRIPT is a non-empty string."""
        assert isinstance(FIXED_WINDOW_SCRIPT, str)
        assert len(FIXED_WINDOW_SCRIPT) > 0

    def test_sliding_window_script_is_string(self) -> None:
        """Test that SLIDING_WINDOW_SCRIPT is a non-empty string."""
        assert isinstance(SLIDING_WINDOW_SCRIPT, str)
        assert len(SLIDING_WINDOW_SCRIPT) > 0

    def test_scripts_are_different(self) -> None:
        """Test that the two scripts are different."""
        assert FIXED_WINDOW_SCRIPT != SLIDING_WINDOW_SCRIPT

    def test_scripts_contain_lua_syntax(self) -> None:
        """Test that scripts contain basic Lua syntax."""
        for script in [FIXED_WINDOW_SCRIPT, SLIDING_WINDOW_SCRIPT]:
            assert "local" in script
            assert "redis.call" in script
            assert "return" in script
