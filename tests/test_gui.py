"""Smoke-test the welcome screen with Qt's offscreen platform."""

import os
import unittest

# Select a display-independent backend before creating QApplication.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel

from cellscope.gui import MainWindow


class WelcomeWindowTest(unittest.TestCase):
    """Check that users can open and close the initial application window."""

    def test_welcome_window_lifecycle(self) -> None:
        """Verify welcome content and a successful exit through Qt's event loop."""
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        try:
            window.show()
            self.assertTrue(window.isVisible())
            self.assertEqual(window.windowTitle(), "CellScope")
            self.assertIsInstance(window.centralWidget(), QLabel)
            self.assertIn("Welcome to CellScope", window.centralWidget().text())
            # Simulate closing the window after the event loop has started.
            QTimer.singleShot(0, window.close)
            self.assertEqual(app.exec(), 0)
            self.assertFalse(window.isVisible())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
