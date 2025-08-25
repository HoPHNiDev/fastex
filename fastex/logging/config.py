import sys
from os import PathLike
from typing import Any

from loguru import logger

log = logger.bind(module="fastex")
BASE_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def configure_fastex_logging(
    enable: bool = True,
    level: str = "INFO",
    sink: str | PathLike[str] | None = None,
    log_format: str | None = None,
) -> None:
    """
    Configure loguru for the fastex library.

    Args:
        enable (bool): Enable or disable logging.
        level (str): Log level ("DEBUG", "INFO", "WARNING", ...).
        sink (str | PathLike | None): Log output destination (file path or None for stdout).
        log_format (str|None): Custom log format.
    """
    logger.remove()

    if not enable:
        return

    logger_params: dict[str, Any] = {
        "level": level,
        "format": log_format or BASE_LOG_FORMAT,
    }

    if sink is not None:
        logger_params["sink"] = sink
    else:
        logger_params["sink"] = sys.stdout

    logger.add(**logger_params)
    log.debug(f"Fastex logging configured - level: {level}, sink: {sink or 'stdout'}")
