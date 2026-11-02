"""Presentation layer for CellScope's navigation layout and dataset page."""

from functools import partial
from pathlib import Path
import logging

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cellscope.dataset import Dataset, load_counts_table
from cellscope.analysis import calculate_quality_metrics
from cellscope.tasks import BackgroundTask

_WELCOME_TEXT = "Welcome to CellScope\nSingle-cell RNA sequencing analysis"
_NO_DATASET_TEXT = (
    "No dataset loaded\n\n"
    "Open a .csv, .tsv, or .txt counts table whose first row lists genes\n"
    "and whose first column lists cells."
)
# BackgroundTask reports the exception type; a user does not need the class name.
_DATASET_ERROR_PREFIX = "DatasetError: "
_FILE_FILTER = "Counts tables (*.csv *.tsv *.txt);;All files (*)"


class DatasetPage(QWidget):
    """Show a dataset summary and offer a button that requests a file.

    A passive view: it holds no dataset, starts no work, and reads no files.
    MainWindow connects ``open_button`` and sets the text of ``summary``.
    """

    def __init__(self) -> None:
        """Create the page's label and button; takes no arguments."""
        super().__init__()
        layout = QVBoxLayout(self)

        self.summary = QLabel(_NO_DATASET_TEXT)
        self.summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary.setWordWrap(True)
        self.summary.setMargin(16)
        # Identifiers and counts are worth copying out of the window.
        self.summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self.open_button = QPushButton("Open counts table…")
        self.open_button.setToolTip("Read a delimited counts table from disk.")
        self.qc_button = QPushButton("Calculate quality metrics")
        self.qc_button.setEnabled(False)
        self.qc_summary = QLabel("")
        self.qc_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qc_summary.setWordWrap(True)
        self.qc_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # The label takes the spare vertical space so the button stays put.
        layout.addWidget(self.summary, 1)
        layout.addWidget(self.qc_summary)
        layout.addWidget(self.qc_button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignHCenter)


class MainWindow(QMainWindow):
    """Navigate pages and load one dataset at a time off the GUI thread."""

    def __init__(self) -> None:
        """Create an independent main window; takes no arguments and returns None."""
        super().__init__()
        self.setWindowTitle("CellScope")
        self.resize(900, 600)

        # The loaded dataset and the task reading it; both absent until a load.
        self.dataset: Dataset | None = None
        self._task: BackgroundTask | None = None

        content = QWidget()
        layout = QHBoxLayout(content)
        self.setCentralWidget(content)

        self.navigation = QListWidget()
        self.navigation.setAccessibleName("Workflow navigation")
        self.navigation.setMinimumWidth(140)
        self.navigation.setMaximumWidth(200)
        self.navigation.setToolTip("Choose a page with the mouse or arrow keys.")
        self.pages = QStackedWidget()

        welcome = QLabel(_WELCOME_TEXT)
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setWordWrap(True)
        welcome.setMargin(16)
        self.dataset_page = DatasetPage()

        # Build both widgets together so each navigation row matches its page.
        for title, page in (("Welcome", welcome), ("Dataset", self.dataset_page)):
            self.navigation.addItem(title)
            self.pages.addWidget(page)

        layout.addWidget(self.navigation)
        # The content area receives extra horizontal space as the window grows.
        layout.addWidget(self.pages, 1)

        # A Qt signal announces selection changes; the connected slot shows a page.
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        self.dataset_page.open_button.clicked.connect(self.choose_dataset)
        self.dataset_page.qc_button.clicked.connect(self.calculate_qc)

    @Slot()
    def choose_dataset(self) -> None:
        """Ask for a counts table and begin loading it; must run on the GUI thread.

        Does nothing if the user cancels the dialog or a load is already running.
        """
        if self._task is not None:
            return
        name, _ = QFileDialog.getOpenFileName(
            self, "CellScope — Open counts table", "", _FILE_FILTER
        )
        if name:
            self.load_dataset(Path(name))

    def load_dataset(self, path: Path) -> None:
        """Read a counts table on a worker thread, leaving the interface responsive.

        Replaces any previously loaded dataset only once the read succeeds, so a
        failed load leaves the current dataset in place. Returns before the read
        finishes; the outcome arrives through a queued signal.
        """
        logging.getLogger(__name__).info("Loading dataset from %s", path)
        self.dataset_page.open_button.setEnabled(False)
        self.dataset_page.qc_button.setEnabled(False)
        self.dataset_page.summary.setText(f"Loading {path.name}…")

        # partial binds the path because BackgroundTask runs a no-argument callable.
        task = BackgroundTask(partial(load_counts_table, path))
        self._task = task
        # Queued connections move each outcome onto the GUI thread before use.
        task.succeeded.connect(self._dataset_loaded, Qt.ConnectionType.QueuedConnection)
        task.failed.connect(self._load_failed, Qt.ConnectionType.QueuedConnection)
        task.finished.connect(self._load_finished, Qt.ConnectionType.QueuedConnection)
        task.start()

    @Slot(object)
    def _dataset_loaded(self, result: object) -> None:
        """Keep a successfully read dataset and display its summary."""
        if not isinstance(result, Dataset):
            self.report_error("The reader returned an unexpected result.")
            return
        self.dataset = result
        self.dataset_page.summary.setText(result.summary())
        self.dataset_page.qc_summary.clear()
        self.dataset_page.qc_button.setEnabled(True)

    @Slot(str)
    def _load_failed(self, message: str) -> None:
        """Report a failed read, restoring the page to its previous description."""
        self.dataset_page.summary.setText(
            self.dataset.summary() if self.dataset is not None else _NO_DATASET_TEXT
        )
        self.report_error(message.removeprefix(_DATASET_ERROR_PREFIX))

    @Slot()
    def _load_finished(self) -> None:
        """Release the finished task and allow another load to start."""
        if self._task is not None:
            self._task.deleteLater()
            self._task = None
        self.dataset_page.open_button.setEnabled(True)
        self.dataset_page.qc_button.setEnabled(self.dataset is not None)

    @Slot()
    def calculate_qc(self) -> None:
        """Calculate and display basic per-cell and per-gene QC metrics."""
        if self.dataset is None:
            return
        try:
            metrics = calculate_quality_metrics(self.dataset)
        except Exception as error:
            self.report_error(str(error))
            return
        self.dataset_page.qc_summary.setText(metrics.summary())

    def closeEvent(self, event) -> None:
        """Wait for a running read before closing, then accept the close event.

        Destroying a live QThread would terminate the process. A table read is
        finite, so this blocks briefly rather than offering a cancel that the
        worker could not honour.
        """
        if self._task is not None and self._task.isRunning():
            logging.getLogger(__name__).info("Waiting for a dataset read to finish")
            self._task.wait()
        super().closeEvent(event)

    @Slot(str)
    def report_error(self, message: str) -> None:
        """Log and display an error summary; must run on the GUI thread.

        Connected to dataset read failures through a queued connection. The
        dialog treats messages as plain text, including filenames with markup.
        """
        logging.getLogger(__name__).error("Operation failed: %s", message)
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("CellScope — Operation failed")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()
