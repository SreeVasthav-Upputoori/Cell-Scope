"""Presentation layer for the initial CellScope welcome window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    """Display the welcome screen without performing scientific analysis."""

    def __init__(self) -> None:
        """Create an independent main window; takes no arguments and returns None."""
        super().__init__()
        self.setWindowTitle("CellScope")
        self.resize(900, 600)

        welcome = QLabel("Welcome to CellScope\nSingle-cell RNA sequencing analysis")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # A central widget fills the main window's content area as it resizes.
        self.setCentralWidget(welcome)
