"""Smoke-test the welcome screen with Qt's offscreen platform."""

import os
import unittest

# Select a display-independent backend before creating QApplication.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
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
            self.assertIsInstance(window.pages.currentWidget(), QLabel)
            self.assertIn("Welcome to CellScope", window.pages.currentWidget().text())

            # Exercise actual mouse and keyboard input, not just the page setter.
            dataset_item = window.navigation.item(1)
            QTest.mouseClick(
                window.navigation.viewport(),
                Qt.MouseButton.LeftButton,
                pos=window.navigation.visualItemRect(dataset_item).center(),
            )
            self.assertEqual(window.pages.currentIndex(), 1)
            self.assertTrue(window.pages.currentWidget().isVisible())
            self.assertFalse(window.pages.widget(0).isVisible())
            self.assertIn("No dataset loaded", window.pages.currentWidget().text())
            self.assertIn("not implemented yet", window.pages.currentWidget().text())

            QTest.keyClick(window.navigation, Qt.Key.Key_Up)
            self.assertEqual(window.pages.currentIndex(), 0)
            self.assertTrue(window.pages.currentWidget().isVisible())
            self.assertFalse(window.pages.widget(1).isVisible())
            # Simulate closing the window after the event loop has started.
            QTimer.singleShot(0, window.close)
            self.assertEqual(app.exec(), 0)
            self.assertFalse(window.isVisible())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
