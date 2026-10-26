"""Check background execution and queued delivery without biological datasets."""

import os
import threading
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QEvent, QEventLoop, QObject, Qt, QTimer, Slot
from PySide6.QtWidgets import QApplication

from cellscope.tasks import BackgroundTask


class OutcomeReceiver(QObject):
    """Collect outcomes in the thread that owns this QObject."""

    def __init__(self) -> None:
        """Initialize empty outcome and delivery-thread records."""
        super().__init__()
        self.results = []
        self.errors = []
        self.threads = []

    @Slot(object)
    def receive_result(self, result: object) -> None:
        """Record a successful result and the receiving thread identifier."""
        self.results.append(result)
        self.threads.append(threading.get_ident())

    @Slot(str)
    def receive_error(self, message: str) -> None:
        """Record an error message and the receiving thread identifier."""
        self.errors.append(message)
        self.threads.append(threading.get_ident())


class BackgroundTaskTest(unittest.TestCase):
    """Verify results, failures, responsiveness, and thread completion."""

    @classmethod
    def setUpClass(cls) -> None:
        """Keep one application alive for the Qt event loops in these tests."""
        cls.app = QApplication.instance() or QApplication([])

    def run_task(self, task: BackgroundTask) -> OutcomeReceiver:
        """Run a bounded test task, collect queued signals, and release it."""
        receiver = OutcomeReceiver()
        task.succeeded.connect(receiver.receive_result, Qt.ConnectionType.QueuedConnection)
        task.failed.connect(receiver.receive_error, Qt.ConnectionType.QueuedConnection)
        loop = QEventLoop()
        task.finished.connect(loop.quit, Qt.ConnectionType.QueuedConnection)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(5000)
        try:
            task.start()
            loop.exec()
            self.assertTrue(timeout.isActive(), "Task completion timed out")
            # Waiting is appropriate in a bounded test teardown, not a GUI handler.
            self.assertTrue(task.wait(1000), "Worker thread did not exit")
            self.assertTrue(task.isFinished())
            self.assertFalse(task.isRunning())
            self.assertEqual(receiver.threads, [threading.get_ident()])
            return receiver
        finally:
            timeout.stop()
            task.wait(5000)
            if not task.isRunning():
                task.deleteLater()
                self.app.sendPostedEvents(task, QEvent.Type.DeferredDelete)

    def test_result_and_responsiveness(self) -> None:
        """A main-thread timer can release a task while it is still running."""
        entered = threading.Event()
        release = threading.Event()
        worker_threads = []
        timer_threads = []
        payload = {"cells": 3, "genes": 2}

        def work() -> object:
            worker_threads.append(threading.get_ident())
            entered.set()
            if not release.wait(2):
                raise TimeoutError("Main-thread timer did not release the task")
            return payload

        def release_from_gui() -> None:
            if entered.is_set():
                timer_threads.append(threading.get_ident())
                release.set()
                heartbeat.stop()

        heartbeat = QTimer()
        heartbeat.timeout.connect(release_from_gui)
        heartbeat.start(5)
        try:
            receiver = self.run_task(BackgroundTask(work))
        finally:
            release.set()
            heartbeat.stop()
        self.assertEqual(receiver.errors, [])
        self.assertEqual(receiver.results, [payload])
        self.assertIs(receiver.results[0], payload)
        self.assertNotEqual(worker_threads[0], threading.get_ident())
        self.assertEqual(timer_threads, [threading.get_ident()])

    def test_none_is_success(self) -> None:
        """Functions without a result still emit one successful outcome."""
        receiver = self.run_task(BackgroundTask(lambda: None))
        self.assertEqual(receiver.results, [None])
        self.assertEqual(receiver.errors, [])

    def test_exception_is_reported(self) -> None:
        """A failed function reports its error and allows the thread to finish."""
        def fail() -> None:
            raise ValueError("Example invalid input")

        with self.assertLogs("cellscope.tasks", level="ERROR") as captured:
            receiver = self.run_task(BackgroundTask(fail))
        self.assertEqual(receiver.results, [])
        self.assertEqual(receiver.errors, ["ValueError: Example invalid input"])
        self.assertIn("Traceback", captured.output[0])
        self.assertIn("ValueError: Example invalid input", captured.output[0])


if __name__ == "__main__":
    unittest.main()
