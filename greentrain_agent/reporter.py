"""Background thread that drains a metric queue and POSTs to /metric."""
import queue
import threading

from .client import GreenTrainClient


class MetricReporter:
    def __init__(self, client: GreenTrainClient, session_id: str) -> None:
        self.client = client
        self.session_id = session_id
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="greentrain-metric-reporter", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def submit(self, **metric) -> None:
        metric["session_id"] = self.session_id
        self._queue.put(metric)

    def _loop(self) -> None:
        while True:
            try:
                m = self._queue.get(timeout=1.0)
            except queue.Empty:
                if self._stop.is_set():
                    break
                continue
            if m is None:
                break
            try:
                self.client.post_metric(**m)
            except Exception as e:
                print(f"[reporter] post failed: {e}")
