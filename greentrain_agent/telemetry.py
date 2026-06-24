import subprocess
from dataclasses import dataclass


@dataclass
class GPUSample:
    power_w: float
    util_percent: int
    temp_c: int
    mem_used_mib: int
    mem_total_mib: int


def sample_gpu(index: int = 0) -> GPUSample:
    result = subprocess.run(
        [
            "nvidia-smi",
            f"--id={index}",
            "--query-gpu=power.draw,utilization.gpu,temperature.gpu,memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    parts = [p.strip() for p in result.stdout.strip().split(",")]
    return GPUSample(
        power_w=float(parts[0]),
        util_percent=int(parts[1]),
        temp_c=int(parts[2]),
        mem_used_mib=int(parts[3]),
        mem_total_mib=int(parts[4]),
    )
