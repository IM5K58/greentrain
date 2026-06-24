"""
Smoke test: poll GPU telemetry for 10 seconds.
Use this to verify nvidia-smi + agent are wired up before installing torch.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from greentrain_agent import sample_gpu


def main() -> None:
    print(f"{'t(s)':>5} | {'power':>8} | {'util':>5} | {'temp':>5} | {'mem':>13}")
    print("-" * 55)
    start = time.time()
    while time.time() - start < 10:
        s = sample_gpu()
        elapsed = time.time() - start
        print(
            f"{elapsed:5.1f} | {s.power_w:6.2f}W | "
            f"{s.util_percent:3d}% | {s.temp_c:3d}C | "
            f"{s.mem_used_mib:5d}/{s.mem_total_mib}MiB"
        )
        time.sleep(1)


if __name__ == "__main__":
    main()
