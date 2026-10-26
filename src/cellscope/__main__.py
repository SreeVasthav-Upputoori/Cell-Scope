"""Start CellScope with ``python -m cellscope``."""

import sys
import logging
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox

from cellscope.gui import MainWindow
from cellscope.logging_setup import configure_logging


def main() -> int:
    """Launch the GUI and return Qt's exit status; no scientific data is loaded."""
    # Qt needs one application object before any widgets can be created.
    app = QApplication(sys.argv)
    app.setApplicationName("CellScope")
    window = MainWindow()
    logger = logging.getLogger("cellscope")
    handler = None
    try:
        directory = Path(QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppLocalDataLocation
        )) / "logs"
        handler = configure_logging(directory)
    except OSError:
        # A logging setup problem must not prevent the application from opening.
        QMessageBox.warning(
            window, "CellScope — Logging unavailable",
            "The diagnostic log could not be opened. CellScope can continue, "
            "but errors will not be saved to a log file this session.",
        )
    window.show()
    try:
        logger.info("CellScope started")
        # The event loop keeps the interface responsive until the window closes.
        return app.exec()
    finally:
        logger.info("CellScope stopped")
        if handler is not None:
            logger.removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
