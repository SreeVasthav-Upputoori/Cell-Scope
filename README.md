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

## Code layout

- `src/cellscope/__main__.py`: creates the application and starts its event loop.
- `src/cellscope/gui.py`: defines the window, sidebar, and information pages.
- `tests/test_gui.py`: automated GUI smoke test.

Future data management and scientific analysis will live outside the GUI module.
Research datasets, local environments, credentials, and generated outputs must
not be committed. Common local paths and dataset formats are in `.gitignore`.
