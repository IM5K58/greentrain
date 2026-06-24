"""Background thread that polls /state and updates the Throttler."""
import threading

from .client import GreenTrainClient
from .throttle import Throttler


class StatePoller:
    def __init__(
        self,
        client: GreenTrainClient,
        throttler: Throttler,
        interval_seconds: float = 30.0,
        on_change=None,
    ) -> None:
        self.client = client
        self.throttler = throttler
        self.interval = interval_seconds
        self.on_change = on_change
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="greentrain-state-poller", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                new_state = self.client.get_state()
                if new_state != self.throttler.state:
                    old = self.throttler.state
                    self.throttler.state = new_state
                    if self.on_change is not None:
                        try:
                            self.on_change(old, new_state)
                        except Exception as e:
                            print(f"[poller] on_change callback raised: {e}")
            except Exception as e:
                print(f"[poller] poll failed: {e}")
            self._stop.wait(self.interval)
