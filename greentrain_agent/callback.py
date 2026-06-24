import time
from dataclasses import dataclass, field

from .state import CarbonState
from .telemetry import GPUSample, sample_gpu
from .throttle import Throttler


@dataclass
class TrainingMetrics:
    total_batches: int = 0
    total_compute_seconds: float = 0.0
    total_sleep_seconds: float = 0.0
    total_energy_wh: float = 0.0
    samples: list[GPUSample] = field(default_factory=list)


class GreenTrainCallback:
    def __init__(self, throttler: Throttler | None = None) -> None:
        self.throttler = throttler or Throttler()
        self.metrics = TrainingMetrics()
        self._batch_start: float | None = None

    @property
    def state(self) -> CarbonState:
        return self.throttler.state

    def on_batch_start(self) -> None:
        self._batch_start = time.perf_counter()

    def on_batch_end(self) -> GPUSample:
        if self._batch_start is None:
            raise RuntimeError("on_batch_start() must be called before on_batch_end()")
        batch_time = time.perf_counter() - self._batch_start
        self._batch_start = None

        sample = sample_gpu()
        self.metrics.samples.append(sample)
        self.metrics.total_batches += 1
        self.metrics.total_compute_seconds += batch_time
        self.metrics.total_energy_wh += sample.power_w * batch_time / 3600.0

        slept = self.throttler.apply(batch_time)
        self.metrics.total_sleep_seconds += slept
        return sample
