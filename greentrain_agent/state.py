from dataclasses import dataclass
from enum import StrEnum


class CarbonState(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass(frozen=True)
class ThrottleConfig:
    # sleep_seconds = batch_compute_seconds * sleep_ratio
    # 0.0 → full speed, 1.0 → 50% throughput, 4.0 → 20% throughput
    sleep_ratio: float
    # When True, the agent will (Phase 2) checkpoint + halt until GREEN.
    # Phase 1: treated as long throttle.
    pause: bool = False


THROTTLE_TABLE: dict[CarbonState, ThrottleConfig] = {
    CarbonState.GREEN: ThrottleConfig(sleep_ratio=0.0),
    CarbonState.YELLOW: ThrottleConfig(sleep_ratio=1.0),
    CarbonState.RED: ThrottleConfig(sleep_ratio=4.0, pause=True),
}
