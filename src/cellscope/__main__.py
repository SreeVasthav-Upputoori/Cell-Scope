"""Start CellScope with ``python -m cellscope``."""

import sys

from PySide6.QtWidgets import QApplication

from cellscope.gui import MainWindow


def main() -> int:
    """Launch the GUI and return Qt's exit status; no scientific data is loaded."""
    # Qt needs one application object before any widgets can be created.
    app = QApplication(sys.argv)
    app.setApplicationName("CellScope")
    window = MainWindow()
    window.show()
    # The event loop keeps the interface responsive until the window closes.
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
