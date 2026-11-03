# CellScope

A desktop workbench for single-cell RNA sequencing data. CellScope can load
delimited count tables, AnnData `.h5ad` files, and 10x Matrix Market folders,
then calculate and explore basic cell and gene quality metrics.

## Setup (Windows PowerShell)

Use 64-bit Python 3.12. Verify that `python --version` selects that interpreter;
the Windows `py` launcher may select a different installation.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

The virtual environment isolates project dependencies from other Python projects.
Direct runtime dependencies are pinned in `pyproject.toml`; this is not yet a
complete transitive dependency lockfile.
The editable installation makes local source edits available without reinstalling.
AnnData and SciPy provide the annotated and sparse matrix support used by the
importers. No activation script is required when using the environment Python.

## Run

```powershell
.\.venv\Scripts\python.exe -m cellscope
```

Click **Dataset**, then **Open dataset…** for a `.csv`, `.tsv`, `.txt`, or
`.h5ad` file, or **Open 10x folder…** for a directory containing a 10x Matrix
Market dataset. The page reports dimensions and memory use. A malformed import
raises an error dialog and leaves the previous dataset in place.

After loading a dataset, choose **Calculate quality metrics** to see per-cell and
per-gene summaries and a cell table with total counts and detected genes. Click a
column heading to sort; numeric columns sort by value. The page also plots the
per-cell total-count and detected-gene distributions. Set minimum total counts
and detected genes to preview how many cells remain, then apply the filter to
make a new in-memory dataset containing those cells.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

The standard-library test uses Qt's offscreen platform to check the welcome
content, mouse/keyboard navigation, window lifecycle, and event-loop exit without
opening a visible window.
It does not replace a manual check of appearance on your display.
Background-task tests also verify result delivery, error handling, thread exit,
and main-thread timer processing while a worker is waiting.

## Code layout

- `src/cellscope/__main__.py`: creates the application and starts its event loop.
- `src/cellscope/gui.py`: defines the window, sidebar, pages, and dataset loading.
- `src/cellscope/tasks.py`: runs finite functions in a background Qt thread.
- `src/cellscope/logging_setup.py`: configures rotating diagnostic logs.
- `src/cellscope/dataset.py`: holds an expression matrix and reads counts tables.
- `src/cellscope/analysis.py`: calculates per-cell and per-gene quality metrics
  and returns filtered cell subsets.
- `tests/test_gui.py`: automated GUI smoke test.
- `tests/test_tasks.py`: background-task and signal-delivery tests.
- `tests/test_logging.py`: file logging, rotation, and startup fallback tests.
- `tests/test_dataset.py`: matrix reading and malformed-table rejection tests.
- `NOTES.md`: the purpose of each module and a log of why each step was taken.

## Errors and diagnostic logs

On launch, CellScope writes `cellscope.log` in Qt's application-local data
directory under `logs` (normally `%LOCALAPPDATA%\CellScope\logs` on Windows).
Logs include timestamps, severity, startup/shutdown events, and background-task
exception tracebacks. Files rotate near 1 MiB, retaining two backups. A single
large entry may exceed that threshold. This handler supports threads in one
application process, not concurrent application processes writing the same file.

If the log cannot be opened at startup, a warning appears and the application
continues without file logging. Runtime disk-write failures are not yet surfaced
in the GUI. Logs can contain paths and exception messages; data matrices are not
deliberately logged. Diagnostic logs are not a scientific analysis history.

`MainWindow.report_error(message)` displays a plain-text error dialog and logs
the summary. Dataset read failures reach it through a queued connection, with
the exception class name stripped from the message. There is no global
unhandled-exception hook yet.

## Background tasks

`BackgroundTask(function)` accepts a no-argument callable. Connect its `succeeded`
and `failed` signals before calling `start()`. A successful function emits its
return value (including `None`); an ordinary exception emits its type and message.
Qt's inherited `finished` signal indicates completion in either case.

Retain the task until it finishes, then use `deleteLater()` to release its Qt
object. GUI receivers should be QObject methods decorated with `Slot`, connected
using `Qt.ConnectionType.QueuedConnection`. Worker functions must not touch widgets
or modify datasets concurrently used by the GUI. Signal payloads are not copied.

`MainWindow.load_dataset` is the first caller: it binds the path with
`functools.partial` and connects all three signals queued. One read runs at a
time, so a stale result cannot overwrite a newer dataset. There is still no
cancellation or progress reporting; `quit()` cannot interrupt the supplied
function, so `closeEvent` waits for a running read rather than destroying a live
thread, which would terminate the process.
Threads do not guarantee faster CPU-bound Python execution because of the GIL.
The current tests establish event-loop responsiveness for a waiting dummy task,
not performance guarantees for future scientific algorithms.

## Datasets

`Dataset` wraps an AnnData object whose matrix is cells × genes. Dense CSV tables
and sparse 10x matrices are both supported. Cell metadata is stored in `obs`,
gene metadata in `var`, and AnnData layers and other annotations are retained
when reading `.h5ad`. A filtered `Dataset` is a view over the original matrix:
the original raw counts and metadata remain available through `raw_counts` and
`adata`, while the active selection is exposed through `counts`, `cell_ids`, and
`cell_metadata`.

`load_dataset(path)` dispatches to the delimited-table, `.h5ad`, or 10x Matrix
Market reader. `.h5ad` imports use the `counts` layer when it exists; otherwise
they use `X`, which must contain non-negative raw counts. The 10x reader accepts
compressed or uncompressed matrix, barcode, and feature files, transposes the
gene × cell Matrix Market matrix into CellScope's cell × gene convention, and
retains feature IDs, names, and types in gene metadata. CSV/TSV/TXT remains a
dense import and is intended for modest-sized tables; use sparse 10x or `.h5ad`
data for larger experiments.

Malformed input raises `DatasetError` for display in the UI. Readers reject
ragged tables, invalid numeric values, negative counts, duplicate identifiers,
and mismatched 10x matrix dimensions. Dataset reads run in a background thread;
a failed read leaves the previously loaded dataset in place.

Future scientific analysis will likewise live outside the GUI module.
Research datasets, local environments, credentials, and generated outputs must
not be committed. Common local paths and dataset formats are in `.gitignore`.
