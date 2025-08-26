from typing import Any

from loguru import logger


class FastexLogger:
    def __init__(self, name: str = "fastex") -> None:
        self.name = name
        self.logger = logger.opt(colors=True, lazy=True)

    def _parse_msg(self, message: str) -> str:
        return f"<m>[{self.name}]</m> {message}"

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.logger.debug(self._parse_msg(message), *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.logger.info(self._parse_msg(message), *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.logger.warning(self._parse_msg(message), *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.logger.error(self._parse_msg(message), *args, **kwargs)

    def success(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.logger.success(self._parse_msg(message), *args, **kwargs)

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.logger.critical(self._parse_msg(message), *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.logger.exception(self._parse_msg(message), *args, **kwargs)
