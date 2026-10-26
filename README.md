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
PySide6 is the only direct runtime dependency at this stage. Its version is pinned
in `pyproject.toml`; this is not yet a complete transitive dependency lockfile.
The editable installation makes local source edits available without reinstalling.
No activation script is required when using the environment's Python directly.

## Run

```powershell
.\.venv\Scripts\python.exe -m cellscope
```

Expected result: a window titled **CellScope** with a sidebar and welcome text.
Click **Dataset** to see the import placeholder, then select **Welcome** again.
With the sidebar focused, the up/down arrow keys also switch pages.
Resize the window to check the layout, then close it using the close button.

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
- `src/cellscope/gui.py`: defines the window, sidebar, and information pages.
- `src/cellscope/tasks.py`: runs finite functions in a background Qt thread.
- `tests/test_gui.py`: automated GUI smoke test.
- `tests/test_tasks.py`: background-task and signal-delivery tests.

## Background tasks

`BackgroundTask(function)` accepts a no-argument callable. Connect its `succeeded`
and `failed` signals before calling `start()`. A successful function emits its
return value (including `None`); an ordinary exception emits its type and message.
Qt's inherited `finished` signal indicates completion in either case.

Retain the task until it finishes, then use `deleteLater()` to release its Qt
object. GUI receivers should be QObject methods decorated with `Slot`, connected
using `Qt.ConnectionType.QueuedConnection`. Worker functions must not touch widgets
or modify datasets concurrently used by the GUI. Signal payloads are not copied.

The worker is not connected to the interface yet. It has no cancellation or
progress reporting; `quit()` cannot interrupt the supplied function. Application
shutdown handling will be added when tasks are integrated into the interface.
Threads do not guarantee faster CPU-bound Python execution because of the GIL.
The current tests establish event-loop responsiveness for a waiting dummy task,
not performance guarantees for future scientific algorithms.

Future data management and scientific analysis will live outside the GUI module.
Research datasets, local environments, credentials, and generated outputs must
not be committed. Common local paths and dataset formats are in `.gitignore`.
