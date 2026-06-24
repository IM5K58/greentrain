"""
Phase 1 / Phase 3 demo:

  - Without --remote: state is flipped locally at --switch-at / --red-at (Phase 1 mode)
  - With --remote: state is fetched from the deployed AWS backend on a background
    poll, and metrics are POSTed to /metric. Trigger transitions by running
    `python scripts/simulate.py RED` in another shell.

Run:
  python examples/train_demo.py --batches 300                  # local-only
  python examples/train_demo.py --batches 600 --remote         # AWS-driven
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import os

import torch
import torch.nn as nn

from greentrain_agent import (
    CarbonState,
    GreenTrainCallback,
    GreenTrainClient,
    MetricReporter,
    StatePoller,
    Throttler,
)

CO2_FACTOR_G_PER_WH = float(os.environ.get("GREENTRAIN_CO2_FACTOR", "0.45"))


def make_workload(batch: int, dim: int, hidden: int, depth: int, device: str):
    layers: list[nn.Module] = [nn.Linear(dim, hidden), nn.ReLU()]
    for _ in range(depth - 2):
        layers += [nn.Linear(hidden, hidden), nn.ReLU()]
    layers += [nn.Linear(hidden, dim)]
    model = nn.Sequential(*layers).to(device)
    x = torch.randn(batch, dim, device=device)
    y = torch.randn(batch, dim, device=device)
    return model, x, y


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batches", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--dim", type=int, default=2048, help="input/output dim")
    parser.add_argument("--hidden", type=int, default=8192, help="hidden dim — bigger = more GPU power draw")
    parser.add_argument("--depth", type=int, default=6, help="layer count")
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Use AWS-driven state polling + metric reporting",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.environ.get("GREENTRAIN_POLL_INTERVAL", "15")),
        help="seconds between /state polls (remote mode)",
    )
    parser.add_argument(
        "--switch-at", type=int, default=50,
        help="(local-only) batch idx to flip GREEN -> YELLOW",
    )
    parser.add_argument(
        "--red-at", type=int, default=120,
        help="(local-only) batch idx to flip YELLOW -> RED (0 disables)",
    )
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        print("[warn] CUDA not available — GPU throttle demo won't be meaningful on CPU.")

    model, x, y = make_workload(args.batch_size, args.dim, args.hidden, args.depth, device)
    optim = torch.optim.SGD(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()

    throttler = Throttler()
    cb = GreenTrainCallback(throttler=throttler)

    poller = None
    reporter = None
    session_id = str(uuid.uuid4())[:8]

    if args.remote:
        client = GreenTrainClient()
        def on_change(old, new):
            print(f"\n>>> grid (remote): {old.value} -> {new.value} <<<\n")
        poller = StatePoller(client, throttler, args.poll_interval, on_change=on_change)
        poller.start()
        reporter = MetricReporter(client, session_id)
        reporter.start()
        # write session_id where the dashboard can find it
        Path(Path(__file__).resolve().parent.parent / ".active_session").write_text(session_id)
        print(f"[init] device={device}  session={session_id}  mode=REMOTE")
        print(f"[init] polling /state every {args.poll_interval}s")
        print("[init] flip state via:  python scripts/simulate.py RED")
        print("[init] live dashboard:   python scripts/dashboard.py\n")
    else:
        print(f"[init] device={device}  session={session_id}  mode=LOCAL")
        print(f"[init] schedule: YELLOW@{args.switch_at}  RED@{args.red_at or '-'}\n")

    cumulative_energy_wh = 0.0

    try:
        for step in range(args.batches):
            if not args.remote:
                if step == args.switch_at:
                    throttler.state = CarbonState.YELLOW
                    print(f"\n>>> grid (local): GREEN -> YELLOW <<<\n")
                if args.red_at and step == args.red_at:
                    throttler.state = CarbonState.RED
                    print(f"\n>>> grid (local): YELLOW -> RED <<<\n")

            cb.on_batch_start()
            optim.zero_grad()
            out = model(x)
            loss = loss_fn(out, y)
            loss.backward()
            optim.step()
            if device == "cuda":
                torch.cuda.synchronize()
            sample = cb.on_batch_end()

            last_batch_energy = sample.power_w * cb.metrics.total_compute_seconds / max(cb.metrics.total_batches, 1) / 3600.0
            cumulative_energy_wh = cb.metrics.total_energy_wh

            if reporter is not None:
                reporter.submit(
                    power_w=sample.power_w,
                    util_pct=sample.util_percent,
                    batch_seconds=cb.metrics.total_compute_seconds / max(cb.metrics.total_batches, 1),
                    sleep_seconds=cb.metrics.total_sleep_seconds / max(cb.metrics.total_batches, 1),
                    state=cb.state.value,
                    energy_wh=last_batch_energy,
                    cumulative_energy_wh=cumulative_energy_wh,
                    cumulative_co2_g=cumulative_energy_wh * CO2_FACTOR_G_PER_WH,
                    cumulative_compute_seconds=cb.metrics.total_compute_seconds,
                    cumulative_throttle_seconds=cb.metrics.total_sleep_seconds,
                )

            if step % 10 == 0:
                print(
                    f"[step {step:4d}] state={cb.state.value:6s} "
                    f"power={sample.power_w:5.1f}W util={sample.util_percent:3d}% "
                    f"loss={loss.item():.4f}"
                )
    finally:
        if poller:
            poller.stop()
        if reporter:
            reporter.stop()

    m = cb.metrics
    avg_power = sum(s.power_w for s in m.samples) / len(m.samples)
    co2_saved_g = m.total_sleep_seconds / 3600.0 * avg_power * CO2_FACTOR_G_PER_WH
    print("\n=== SUMMARY ===")
    print(f"session_id:    {session_id}")
    print(f"batches:       {m.total_batches}")
    print(f"compute time:  {m.total_compute_seconds:6.2f} s")
    print(f"throttle time: {m.total_sleep_seconds:6.2f} s")
    print(f"energy used:   {m.total_energy_wh:6.3f} Wh")
    print(f"avg power:     {avg_power:6.1f} W")
    print(f"~CO2 avoided:  {co2_saved_g:6.3f} g  (factor={CO2_FACTOR_G_PER_WH} gCO2/Wh)")


if __name__ == "__main__":
    main()
