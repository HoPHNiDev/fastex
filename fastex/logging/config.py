import sys
from os import PathLike

from loguru import logger

log = logger.opt(colors=True, lazy=True)
BASE_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function: <10}</cyan>:<cyan>{line: <3}</cyan> - "
    "<level>{message}</level>"
)


def configure_fastex_logging(
    level: str = "DEBUG",
    sink: str | PathLike[str] | None = None,
    log_format: str | None = None,
) -> None:
    """
    Configure loguru for the fastex library.

    Args:
        level (str): Log level ("DEBUG", "INFO", "WARNING", ...).
        sink (str | PathLike | None): Log output destination (file path or None for stdout).
        log_format (str|None): Custom log format.
    """
    logger.remove()

    logger.add(
        sink or sys.stdout,
        level=level,
        format=log_format or BASE_LOG_FORMAT,
        colorize=True,
    )


def enable_fastex_logging() -> None:
    logger.enable("fastex")


def disable_fastex_logging() -> None:
    logger.disable("fastex")


configure_fastex_logging()
