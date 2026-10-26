"""Presentation layer for CellScope's initial navigation layout."""

import logging

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)


class MainWindow(QMainWindow):
    """Display navigable information pages without performing analysis."""

    def __init__(self) -> None:
        """Create an independent main window; takes no arguments and returns None."""
        super().__init__()
        self.setWindowTitle("CellScope")
        self.resize(900, 600)

        content = QWidget()
        layout = QHBoxLayout(content)
        self.setCentralWidget(content)

        self.navigation = QListWidget()
        self.navigation.setAccessibleName("Workflow navigation")
        self.navigation.setMinimumWidth(140)
        self.navigation.setMaximumWidth(200)
        self.navigation.setToolTip("Choose a page with the mouse or arrow keys.")
        self.pages = QStackedWidget()

        # Build both widgets together so each navigation row matches its page.
        for title, text in (
            ("Welcome", "Welcome to CellScope\nSingle-cell RNA sequencing analysis"),
            (
                "Dataset",
                "No dataset loaded\n\n"
                "Dataset import is not implemented yet.\n"
                "This page will provide dataset loading and a summary of cells and genes.",
            ),
        ):
            page = QLabel(text)
            page.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page.setWordWrap(True)
            page.setMargin(16)
            self.navigation.addItem(title)
            self.pages.addWidget(page)

        layout.addWidget(self.navigation)
        # The content area receives extra horizontal space as the window grows.
        layout.addWidget(self.pages, 1)

        # A Qt signal announces selection changes; the connected slot shows a page.
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

    @Slot(str)
    def report_error(self, message: str) -> None:
        """Log and display an error summary; must run on the GUI thread.

        Connect future worker failures using a queued connection. The dialog
        treats messages as plain text, including filenames containing markup.
        """
        logging.getLogger(__name__).error("Operation failed: %s", message)
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("CellScope — Operation failed")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()
