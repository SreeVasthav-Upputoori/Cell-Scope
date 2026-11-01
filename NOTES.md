# CellScope development notes

CellScope is built one feature at a time. Each feature is finished, tested, and
committed on its own before the next one starts. This file records what every
module is for and why each step was taken, so the reasoning survives after the
code is written. The README describes how to use the application; these notes
describe how it came to be shaped this way.

## Purpose of each module

| File | Purpose | Why it exists separately |
| --- | --- | --- |
| `src/cellscope/__init__.py` | Marks the package and names the application in one docstring. | Keeps the package importable without executing any startup work. |
| `src/cellscope/__main__.py` | Startup: creates the Qt application object, sets up logging, shows the window, runs the event loop, and logs shutdown. | Startup order matters and is easy to get wrong. Keeping it in one place means `gui.py` never has to know how the process was launched. |
| `src/cellscope/gui.py` | The visible interface: main window, sidebar navigation, stacked pages, and the error dialog slot. | All Qt widget code lives here so analysis code can be tested without a display. |
| `src/cellscope/tasks.py` | `BackgroundTask`: runs one finite callable on a worker thread and reports its result or exception as a Qt signal. | Long reads and computations must not freeze the interface. Separating the mechanism from any particular job makes it reusable and testable with a dummy function. |
| `src/cellscope/logging_setup.py` | Attaches a rotating file handler to the `cellscope` logger. | Diagnostics must be configurable and testable in isolation, and must never silently reconfigure Python's root logger for other libraries. |
| `src/cellscope/dataset.py` | The data layer: the immutable `Dataset` record (counts matrix plus cell and gene labels) and `load_counts_table`, which reads a delimited text table. | Data handling is deliberately outside the GUI. It has no Qt import at all, so it can be tested, reused, and later replaced with a sparse or HDF5 backend without touching the interface. |
| `tests/test_gui.py` | Smoke test of welcome content, mouse and keyboard navigation, and window lifecycle, using Qt's offscreen platform. | Catches breakage in the window wiring without needing a visible display. |
| `tests/test_tasks.py` | Checks result delivery, error handling, thread exit, and main-thread responsiveness while a worker waits. | Threading faults are intermittent; these tests pin the contract down. |
| `tests/test_logging.py` | Checks file creation, rotation, and the startup fallback path. | Logging is the thing that reports other failures, so it needs its own proof. |
| `tests/test_dataset.py` | Checks correct reading plus every rejection case: bad extension, header-only file, ragged row, non-numeric, negative, missing, duplicate, and blank labels. | A reader that quietly invents data is worse than one that refuses to load, so the refusals are tested as carefully as the success. |

## Build log

### 1. Welcome window — `a40c8b1`

Started with the smallest thing that could be run and seen: a titled window of a
fixed starting size. Choosing PySide6 at this point fixed the toolkit decision
early, while nothing depended on it yet.

### 2. Welcome and dataset navigation — `c293d01`

Added the sidebar and a stacked page area, driven by one signal connection from
the list's `currentRowChanged`. The Dataset page is a placeholder that says so
plainly. The shape of the application — a workflow of pages — is now visible
before any science exists to put in it.

### 3. Background task execution — `74e4395`

Added `BackgroundTask` before any slow work existed, because retrofitting
threading onto code written synchronously is far harder. It carries no knowledge
of datasets; it takes a callable. Deliberately left out: cancellation, progress
reporting, and shutdown handling.

### 4. Diagnostic logging and error reporting — `e67f9dd`

Added rotating file logs and `MainWindow.report_error`, so that from this point
on every later feature has somewhere to record a failure. Built before the
features that would need it, rather than after the first unexplained crash.

### 5. Dataset model and counts reader — this commit

**What was added.** `src/cellscope/dataset.py` and `tests/test_dataset.py`;
`numpy==2.5.4` pinned as the second runtime dependency.

**Why now.** The interface has a Dataset page with nothing to show. Before the
page can show anything, something has to define what a loaded dataset *is*. This
step answers that and nothing else.

**Decisions.**

- *Cells as rows.* `counts` is cells × genes, matching AnnData, so a future
  AnnData or HDF5 reader will not need to transpose and confuse the convention.
- *numpy, not lists.* An expression matrix of lists of floats would have to be
  thrown away as soon as real data arrives. float32 halves memory against
  float64 and is ample for counts.
- *Frozen dataclass.* A loaded dataset is a record, not a mutable workspace.
  Analysis steps will return new objects instead of editing one in place. The
  array itself is shared by reference, which is noted in its docstring.
- *Extension decides the delimiter.* Sniffing a delimiter guesses, and a wrong
  guess produces a plausible but wrong matrix. An unknown extension is refused.
- *`DatasetError` is its own exception.* It separates "this file is bad", which
  the user should see in a dialog, from a bug in our own code. File system
  problems stay as `OSError` so the caller can word those differently.
- *Loud refusals.* Ragged rows, non-numeric text, negatives, infinities, and
  duplicate or blank identifiers all raise, with the row number where known.
  Padding a short row would silently fabricate zero counts.

**Deliberately left out.** Sparse matrices, HDF5/`.h5ad`/Matrix Market formats,
gene or cell metadata columns, normalisation, and any quality-control filtering.
The reader loads the whole table densely into memory, so it suits exported
tables of modest size, not a full experiment. This limit is written in the
function's docstring rather than left for a user to discover.

**Not yet connected.** Nothing calls `load_counts_table`. The GUI still shows a
placeholder.

**Next step.** Wire the Dataset page to this module: a file-open action that runs
`load_counts_table` through `BackgroundTask`, shows `Dataset.summary()` on
success, and routes `DatasetError` to `report_error`. That single step also
closes the two loose ends the README notes — the worker is not connected to the
interface, and there is no shutdown handling for a running task.
