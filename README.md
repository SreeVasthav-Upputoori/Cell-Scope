# CellScope

A Python desktop application for single-cell RNA sequencing analysis, developed
one feature at a time. The current version provides Welcome and Dataset pages;
dataset import and scientific analysis are not implemented yet.

## Setup (Windows PowerShell)

Use 64-bit Python 3.12. Verify that `python --version` selects that interpreter;
the Windows `py` launcher may select a different installation.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

The virtual environment isolates project dependencies from other Python projects.
PySide6 and NumPy are the direct runtime dependencies at this stage. Their
versions are pinned in `pyproject.toml`; this is not yet a complete transitive
dependency lockfile.
The editable installation makes local source edits available without reinstalling.
No activation script is required when using the environment's Python directly.

## Run

```powershell
.\.venv\Scripts\python.exe -m cellscope
```

Expected result: a window titled **CellScope** with a sidebar and welcome text.
Click **Dataset**, then **Open counts table…** and choose a `.csv`, `.tsv`, or
`.txt` table; the page reports the file name, its cell and gene totals, and the
matrix size in memory. Opening a malformed table raises an error dialog and
leaves the previous summary in place. With the sidebar focused, the up/down arrow
keys also switch pages. Resize the window to check the layout, then close it
using the close button.

After loading a table, choose **Calculate quality metrics** to see per-cell and
per-gene summaries and a cell table with total counts and detected genes. Click a
column heading to sort; numeric columns sort by value. Set minimum total counts
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

`Dataset` holds a counts matrix as a float32 NumPy array with one row per cell
and one column per gene, matching AnnData's orientation, alongside immutable
tuples of cell and gene identifiers. It is a frozen record: analysis steps will
return new objects rather than edit one in place. The array is shared by
reference and is not copied, so treat a displayed dataset as read-only.

`load_counts_table(path)` reads a `.csv`, `.tsv`, or `.txt` table whose first row
lists genes and whose first column lists cells. The delimiter is chosen by
extension rather than guessed, and an unknown extension is refused. The entire
table is read into memory as a dense array, which suits exported tables of
modest size but not a full sparse experiment.

Malformed input raises `DatasetError`, whose message is written for display in a
dialog: a ragged row, non-numeric text, a negative count, a missing or infinite
value, or a duplicate or blank identifier. Nothing is padded or coerced, because
a quietly fabricated zero is worse than a refused file. Unreadable files raise
`OSError` so the caller can word that case differently.

The Dataset page reads tables through this module on a worker thread. A failed
read keeps the previously loaded dataset, because a dialog the user dismisses
should not also lose their data.

Not implemented yet: sparse matrices, `.h5ad` and Matrix Market formats, cell or
gene metadata, normalisation, and quality-control filtering. Only one dataset is
held at a time, and it is not written back to disk.

Future scientific analysis will likewise live outside the GUI module.
Research datasets, local environments, credentials, and generated outputs must
not be committed. Common local paths and dataset formats are in `.gitignore`.
