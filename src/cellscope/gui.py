"""Presentation layer for CellScope's initial navigation layout."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
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
