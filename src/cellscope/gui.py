"""Presentation layer for CellScope's navigation layout and dataset page."""

from functools import partial
from pathlib import Path
import logging

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cellscope.analysis import QualityMetrics, calculate_quality_metrics, filter_cells
from cellscope.dataset import Dataset, load_counts_table
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


class _SortableTableItem(QTableWidgetItem):
    """Sort numeric cells numerically while retaining display formatting."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        value = self.data(Qt.ItemDataRole.UserRole)
        other_value = other.data(Qt.ItemDataRole.UserRole)
        if value is not None and other_value is not None:
            return value < other_value
        return super().__lt__(other)


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
        self.cell_table = QTableWidget(0, 3)
        self.cell_table.setHorizontalHeaderLabels(
            ("Cell ID", "Total counts", "Detected genes")
        )
        self.cell_table.setSortingEnabled(True)
        self.cell_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cell_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cell_table.setAccessibleName("Per-cell quality metrics")
        self.cell_table.hide()
        self.filter_controls = QWidget()
        filter_layout = QFormLayout(self.filter_controls)
        self.min_counts = QDoubleSpinBox()
        self.min_counts.setDecimals(2)
        self.min_counts.setRange(0, 1_000_000_000_000)
        self.min_counts.setAccessibleName("Minimum total counts per cell")
        self.min_genes = QSpinBox()
        self.min_genes.setRange(0, 1_000_000_000)
        self.min_genes.setAccessibleName("Minimum detected genes per cell")
        self.filter_preview = QLabel("")
        self.apply_filter_button = QPushButton("Apply cell filters")
        filter_layout.addRow("Minimum total counts", self.min_counts)
        filter_layout.addRow("Minimum detected genes", self.min_genes)
        filter_layout.addRow(self.filter_preview)
        filter_layout.addRow(self.apply_filter_button)
        self.filter_controls.hide()

        # The label takes the spare vertical space so the button stays put.
        layout.addWidget(self.summary, 1)
        layout.addWidget(self.qc_summary)
        layout.addWidget(self.cell_table, 2)
        layout.addWidget(self.filter_controls)
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
        self._qc_metrics: QualityMetrics | None = None

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
        self.dataset_page.min_counts.valueChanged.connect(self.preview_filter)
        self.dataset_page.min_genes.valueChanged.connect(self.preview_filter)
        self.dataset_page.apply_filter_button.clicked.connect(self.apply_cell_filter)

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
        self._qc_metrics = None
        self.dataset_page.summary.setText(result.summary())
        self.dataset_page.qc_summary.clear()
        self.dataset_page.cell_table.clearContents()
        self.dataset_page.cell_table.setRowCount(0)
        self.dataset_page.cell_table.hide()
        self.dataset_page.filter_controls.hide()
        self.dataset_page.min_counts.setValue(0)
        self.dataset_page.min_genes.setValue(0)
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
        self._qc_metrics = metrics
        self.dataset_page.qc_summary.setText(metrics.summary())
        controls = self.dataset_page
        controls.min_counts.setMaximum(
            max(1_000_000_000_000.0, float(metrics.cell_total_counts.max()))
        )
        controls.min_genes.setMaximum(int(metrics.cell_detected_genes.max()))
        controls.filter_controls.show()
        table = self.dataset_page.cell_table
        table.setSortingEnabled(False)
        table.setRowCount(self.dataset.n_cells)
        for row, cell_id in enumerate(self.dataset.cell_ids):
            total = float(metrics.cell_total_counts[row])
            detected = int(metrics.cell_detected_genes[row])
            table.setItem(row, 0, QTableWidgetItem(cell_id))
            total_item = _SortableTableItem(f"{total:g}")
            total_item.setData(Qt.ItemDataRole.UserRole, total)
            table.setItem(row, 1, total_item)
            detected_item = _SortableTableItem(str(detected))
            detected_item.setData(Qt.ItemDataRole.UserRole, detected)
            table.setItem(row, 2, detected_item)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
        table.show()
        self.preview_filter()

    @Slot()
    def preview_filter(self) -> None:
        """Show how many cells meet the currently selected thresholds."""
        if self.dataset is None:
            return
        metrics = self._qc_metrics
        if metrics is None:
            metrics = calculate_quality_metrics(self.dataset)
            self._qc_metrics = metrics
        page = self.dataset_page
        keep = (metrics.cell_total_counts >= page.min_counts.value()) & (
            metrics.cell_detected_genes >= page.min_genes.value()
        )
        remaining = int(keep.sum())
        page.filter_preview.setText(
            f"{remaining:,} of {self.dataset.n_cells:,} cells would remain"
        )
        page.apply_filter_button.setEnabled(remaining > 0 and remaining < self.dataset.n_cells)

    @Slot()
    def apply_cell_filter(self) -> None:
        """Replace the current dataset with cells meeting both thresholds."""
        if self.dataset is None:
            return
        try:
            self.dataset = filter_cells(
                self.dataset,
                min_total_counts=self.dataset_page.min_counts.value(),
                min_detected_genes=self.dataset_page.min_genes.value(),
            )
        except ValueError as error:
            self.report_error(str(error))
            return
        self.dataset_page.summary.setText(self.dataset.summary())
        self.calculate_qc()

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
