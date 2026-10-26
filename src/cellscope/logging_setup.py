"""Configure local diagnostic logs without changing Python's root logger."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(directory: Path) -> RotatingFileHandler:
    """Attach and return CellScope's file handler in the supplied directory.

    Call on startup before launching workers. Repeated calls for the same path
    reuse the handler. Files rotate near 1 MiB with two backups. Directory or
    file access errors propagate as OSError so the GUI can report them.
    """
    path = directory.resolve() / "cellscope.log"
    logger = logging.getLogger("cellscope")
    for handler in logger.handlers:
        if handler.name == "cellscope.file" and isinstance(handler, RotatingFileHandler):
            if Path(handler.baseFilename) == path:
                return handler
            raise ValueError("CellScope logging is already configured for another path")

    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8"
    )
    handler.set_name("cellscope.file")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"
    ))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return handler
