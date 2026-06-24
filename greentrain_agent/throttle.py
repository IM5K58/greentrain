import time

from .state import CarbonState, THROTTLE_TABLE


class Throttler:
    def __init__(self, state: CarbonState = CarbonState.GREEN) -> None:
        self._state = state

    @property
    def state(self) -> CarbonState:
        return self._state

    @state.setter
    def state(self, value: CarbonState) -> None:
        self._state = value

    def apply(self, last_batch_seconds: float) -> float:
        cfg = THROTTLE_TABLE[self._state]
        sleep_s = last_batch_seconds * cfg.sleep_ratio
        if sleep_s > 0:
            time.sleep(sleep_s)
        return sleep_s
