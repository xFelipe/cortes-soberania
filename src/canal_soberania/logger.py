"""Setup loguru com rotação em data/logs/."""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
        colorize=True,
    )
    logger.add(
        log_dir / "pipeline_{time:YYYY-MM-DD}.log",
        level=level,
        rotation="00:00",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
    )


__all__ = ["logger", "setup_logger"]
