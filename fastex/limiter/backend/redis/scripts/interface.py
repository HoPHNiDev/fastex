from abc import ABC, abstractmethod
from typing import Any


class LuaScript(ABC):
    @abstractmethod
    def get_script(self) -> str:
        """Return the Lua script as a string."""
        raise NotImplementedError

    @abstractmethod
    def extra_params(self) -> list[Any]:
        """
        Return any extra parameters needed for the Lua script.

        Returns:
            list[Any]: A list of extra parameters.
        """
        raise NotImplementedError

    @abstractmethod
    def parse_result(self, result: list[Any]) -> tuple[int, int]:
        """
        Parse the result returned by the Lua script.

        Parameters:
            result (list[Any]): The raw result from the Lua script execution.
        Returns:
            tuple[int, int]: A tuple containing two integers, ttl and current stored requests count.
        """
        raise NotImplementedError
