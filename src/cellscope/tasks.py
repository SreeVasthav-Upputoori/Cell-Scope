"""Run finite, non-GUI functions in a background Qt thread."""

from collections.abc import Callable
import logging

from PySide6.QtCore import QThread, Signal


class BackgroundTask(QThread):
    """Execute a callable and report its result or an ordinary Python exception.

    Keep a reference to the task until its inherited ``finished`` signal fires.
    Connect results to QObject methods decorated with ``Slot`` on the GUI thread;
    use a queued connection when updating widgets. Release the Qt object with
    ``deleteLater`` after completion. Never destroy a running task.

    Functions must not access widgets or mutate data concurrently used elsewhere.
    Results are passed by reference, not copied. This class does not interpret
    biological data, provide cancellation, or run a worker-side Qt event loop.
    """

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function: Callable[[], object]) -> None:
        """Store a no-argument callable whose return value becomes the result.

        Use ``functools.partial`` to bind arguments when needed. Construction
        does not start work; call ``start()`` once connections are in place.
        """
        super().__init__()
        self._function = function

    def run(self) -> None:
        """Execute in the worker thread, emit an outcome, then return None.

        Qt calls this method through ``start()`` and emits ``finished`` when it
        returns, including after a handled exception. Do not call run directly.
        """
        try:
            result = self._function()
        except Exception as error:
            # Preserve the traceback locally; the signal carries a short summary.
            logging.getLogger(__name__).exception("Background task failed")
            # Include the exception type so even an empty message is informative.
            self.failed.emit(f"{type(error).__name__}: {error}")
        else:
            # None is a valid successful result, distinct from a failed task.
            self.succeeded.emit(result)
