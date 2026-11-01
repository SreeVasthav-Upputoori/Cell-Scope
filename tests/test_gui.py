"""Smoke-test the window, navigation, and dataset loading with Qt's offscreen platform."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

# Select a display-independent backend before creating QApplication.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from cellscope.gui import DatasetPage, MainWindow


class WelcomeWindowTest(unittest.TestCase):
    """Check that users can open and close the initial application window."""

    def test_error_dialog(self) -> None:
        """Display literal error text, then dismiss the dialog without closing the window."""
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.show()
        observed = []

        def dismiss() -> None:
            for dialog in window.findChildren(QMessageBox):
                observed.append((dialog.text(), dialog.textFormat(), dialog.icon()))
                dialog.accept()

        message = "Cannot read <example.h5ad>"
        try:
            QTimer.singleShot(0, dismiss)
            with self.assertLogs("cellscope.gui", level="ERROR"):
                window.report_error(message)
            self.assertEqual(observed, [(
                message, Qt.TextFormat.PlainText, QMessageBox.Icon.Critical
            )])
            self.assertTrue(window.isVisible())
        finally:
            window.close()

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
            self.assertIsInstance(window.pages.currentWidget(), DatasetPage)
            self.assertTrue(window.pages.currentWidget().isVisible())
            self.assertFalse(window.pages.widget(0).isVisible())
            self.assertIn("No dataset loaded", window.dataset_page.summary.text())
            self.assertTrue(window.dataset_page.open_button.isEnabled())

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


class DatasetLoadingTest(unittest.TestCase):
    """Check that a chosen table reaches the page without blocking the interface."""

    @classmethod
    def setUpClass(cls) -> None:
        """Keep one application alive for the Qt event loops in these tests."""
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        """Create a window and a temporary directory for table files."""
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.window = MainWindow()
        self.addCleanup(self.window.close)

    def write(self, name: str, text: str) -> Path:
        """Create a table file and return its path."""
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def settle(self) -> None:
        """Wait for the worker to exit, then deliver its queued signals."""
        task = self.window._task
        if task is not None:
            self.assertTrue(task.wait(5000), "the dataset read did not finish")
        self.app.processEvents()

    def test_button_click_loads_chosen_table(self) -> None:
        """A chosen file is read off the GUI thread and summarised on the page."""
        path = self.write("counts.csv", "cell,GeneA,GeneB\nc1,1,2\nc2,3,4\n")
        with patch(
            "cellscope.gui.QFileDialog.getOpenFileName", return_value=(str(path), "")
        ):
            QTest.mouseClick(self.window.dataset_page.open_button, Qt.MouseButton.LeftButton)
            # The read is queued, so the button is disabled before any result.
            self.assertFalse(self.window.dataset_page.open_button.isEnabled())
            self.settle()

        self.assertIsNotNone(self.window.dataset)
        self.assertEqual((self.window.dataset.n_cells, self.window.dataset.n_genes), (2, 2))
        self.assertIn("2 cells × 2 genes", self.window.dataset_page.summary.text())
        self.assertTrue(self.window.dataset_page.open_button.isEnabled())
        self.assertIsNone(self.window._task)

    def test_cancelled_dialog_loads_nothing(self) -> None:
        """Dismissing the file dialog leaves the page and dataset untouched."""
        with patch("cellscope.gui.QFileDialog.getOpenFileName", return_value=("", "")):
            self.window.choose_dataset()
        self.assertIsNone(self.window.dataset)
        self.assertIsNone(self.window._task)
        self.assertIn("No dataset loaded", self.window.dataset_page.summary.text())

    def test_malformed_table_reports_error_without_class_name(self) -> None:
        """A bad file raises a dialog whose text omits the exception class name."""
        path = self.write("counts.csv", "cell,GeneA\nc1,high\n")
        reported = []
        with patch.object(MainWindow, "report_error", lambda _self, text: reported.append(text)):
            # assertLogs captures the worker's traceback instead of printing it.
            with self.assertLogs("cellscope.tasks", level="ERROR"):
                self.window.load_dataset(path)
                self.settle()

        self.assertEqual(len(reported), 1)
        self.assertNotIn("DatasetError", reported[0])
        self.assertIn("non-numeric", reported[0])
        # A failed read must not discard the page's description or wedge the button.
        self.assertIsNone(self.window.dataset)
        self.assertIn("No dataset loaded", self.window.dataset_page.summary.text())
        self.assertTrue(self.window.dataset_page.open_button.isEnabled())

    def test_failed_reload_keeps_the_previous_dataset(self) -> None:
        """A later bad file leaves the already loaded dataset and its summary."""
        good = self.write("good.csv", "cell,GeneA\nc1,5\n")
        bad = self.write("bad.csv", "cell,GeneA\nc1,-1\n")
        self.window.load_dataset(good)
        self.settle()
        first = self.window.dataset

        with patch.object(MainWindow, "report_error", lambda _self, text: None):
            with self.assertLogs("cellscope.tasks", level="ERROR"):
                self.window.load_dataset(bad)
                self.settle()

        self.assertIs(self.window.dataset, first)
        self.assertIn("good.csv", self.window.dataset_page.summary.text())

    def test_second_load_is_refused_while_one_runs(self) -> None:
        """One read at a time, so a queued result cannot overwrite a newer one."""
        path = self.write("counts.csv", "cell,GeneA\nc1,1\n")
        self.window.load_dataset(path)
        running = self.window._task
        with patch("cellscope.gui.QFileDialog.getOpenFileName") as dialog:
            self.window.choose_dataset()
        dialog.assert_not_called()
        self.assertIs(self.window._task, running)
        self.settle()

    def test_close_waits_for_a_running_read(self) -> None:
        """Closing mid-read waits for the worker instead of destroying its thread."""
        path = self.write("counts.csv", "cell,GeneA\nc1,1\n")
        self.window.show()
        self.window.load_dataset(path)
        task = self.window._task
        self.window.close()
        self.assertFalse(task.isRunning())
        self.assertFalse(self.window.isVisible())


if __name__ == "__main__":
    unittest.main()
