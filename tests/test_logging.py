"""Validate diagnostic files and startup fallback using temporary storage."""

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cellscope.logging_setup import configure_logging


class LoggingTest(unittest.TestCase):
    """Keep log configuration isolated from other tests and the user's logs."""

    def setUp(self) -> None:
        """Preserve the application logger and allocate temporary storage."""
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.logger = logging.getLogger("cellscope")
        self.original_level = self.logger.level
        self.original_handlers = self.logger.handlers[:]
        self.logger.handlers = []
        self.addCleanup(self.restore_logging)

    def restore_logging(self) -> None:
        """Close test handlers before removing their files on Windows."""
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
            handler.close()
        self.logger.handlers = self.original_handlers
        self.logger.setLevel(self.original_level)

    def test_traceback_and_repeated_setup(self) -> None:
        """Store Unicode and traceback details once despite repeated setup."""
        directory = Path(self.directory.name) / "logs"
        handler = configure_logging(directory)
        self.assertIs(configure_logging(directory), handler)
        try:
            raise ValueError("Example gene α")
        except ValueError:
            logging.getLogger("cellscope.tasks").exception("Test failure")
        contents = (directory / "cellscope.log").read_text(encoding="utf-8")
        self.assertEqual(contents.count("Test failure"), 1)
        self.assertIn("Traceback", contents)
        self.assertIn("ValueError: Example gene α", contents)

    def test_rotation(self) -> None:
        """Verify backups are bounded without generating megabytes of test logs."""
        directory = Path(self.directory.name)
        handler = configure_logging(directory)
        self.assertEqual(handler.maxBytes, 1024 * 1024)
        handler.maxBytes = 150
        for index in range(20):
            self.logger.info("Diagnostic entry %s %s", index, "x" * 60)
        self.assertEqual(
            {path.name for path in directory.iterdir()},
            {"cellscope.log", "cellscope.log.1", "cellscope.log.2"},
        )

    def test_invalid_directory(self) -> None:
        """A file used as a directory reports an error without attaching a handler."""
        path = Path(self.directory.name) / "file"
        path.write_text("occupied", encoding="utf-8")
        with self.assertRaises(OSError):
            configure_logging(path)
        self.assertEqual(self.logger.handlers, [])

    def test_startup_continues_without_log_file(self) -> None:
        """If log setup fails, warn the user and still enter the GUI event loop."""
        from cellscope.__main__ import main

        with (
            patch("cellscope.__main__.QApplication") as application,
            patch("cellscope.__main__.MainWindow") as window,
            patch("cellscope.__main__.configure_logging", side_effect=PermissionError),
            patch("cellscope.__main__.QMessageBox.warning") as warning,
        ):
            application.return_value.exec.return_value = 0
            self.assertEqual(main(), 0)
            warning.assert_called_once()
            window.return_value.show.assert_called_once()
            application.return_value.exec.assert_called_once()


if __name__ == "__main__":
    unittest.main()
