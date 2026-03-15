"""Loguru-based logger setup for LocalRAG."""
import sys
from loguru import logger


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """Configure loguru logger with console and optional file sink."""
    logger.remove()

    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    if log_file:
        logger.add(
            log_file,
            level=log_level,
            rotation="10 MB",
            retention="7 days",
            compression="gz",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} — {message}",
        )


__all__ = ["logger", "setup_logging"]
