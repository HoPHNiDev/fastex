"""Unit tests for Lua script interface."""

from typing import Any

import pytest

from fastex.limiter.backend.redis.scripts.interface import LuaScript


class TestLuaScriptInterface:
    """Test the LuaScript abstract base class."""

    def test_lua_script_is_abstract(self) -> None:
        """Test that LuaScript is an abstract base class."""
        from abc import ABC

        assert LuaScript.__bases__ == (ABC,)
        assert hasattr(LuaScript, "__abstractmethods__")

    def test_lua_script_abstract_methods(self) -> None:
        """Test that LuaScript has the required abstract methods."""
        abstract_methods = LuaScript.__abstractmethods__
        expected_methods = {"get_script", "extra_params", "parse_result"}
        assert abstract_methods == expected_methods

    def test_cannot_instantiate_lua_script_directly(self) -> None:
        """Test that LuaScript cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            LuaScript()  # type: ignore

    def test_get_script_method_signature(self) -> None:
        """Test that get_script method has correct signature."""
        method = LuaScript.get_script
        assert hasattr(method, "__annotations__")
        assert method.__annotations__.get("return") is str

    def test_extra_params_method_signature(self) -> None:
        """Test that extra_params method has correct signature."""
        method = LuaScript.extra_params
        assert hasattr(method, "__annotations__")
        assert method.__annotations__.get("return") == list[Any]

    def test_parse_result_method_signature(self) -> None:
        """Test that parse_result method has correct signature."""
        method = LuaScript.parse_result
        assert hasattr(method, "__annotations__")
        assert method.__annotations__.get("return") == tuple[int, int]
        assert method.__annotations__.get("result") == list[Any]


class ConcreteTestScript(LuaScript):
    """Concrete implementation for testing purposes."""

    def get_script(self) -> str:
        return "return {0, 1}"

    def extra_params(self) -> list[Any]:
        return []

    def parse_result(self, result: list[Any]) -> tuple[int, int]:
        return int(result[0]), int(result[1])


class TestConcreteImplementation:
    """Test that concrete implementations work correctly."""

    def test_concrete_script_can_be_instantiated(self) -> None:
        """Test that a concrete implementation can be instantiated."""
        script = ConcreteTestScript()
        assert isinstance(script, LuaScript)

    def test_concrete_script_methods_work(self) -> None:
        """Test that concrete implementation methods work as expected."""
        script = ConcreteTestScript()

        # Test get_script
        assert script.get_script() == "return {0, 1}"

        # Test extra_params
        assert script.extra_params() == []

        # Test parse_result
        result = script.parse_result([10, 5])
        assert result == (10, 5)
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)

    def test_concrete_script_inheritance(self) -> None:
        """Test that concrete script properly inherits from LuaScript."""
        script = ConcreteTestScript()
        assert isinstance(script, LuaScript)
        assert hasattr(script, "get_script")
        assert hasattr(script, "extra_params")
        assert hasattr(script, "parse_result")
