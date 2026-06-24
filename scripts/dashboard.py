"""
Live terminal dashboard pulling from the AWS backend.

Reads:
  - GET /state           (grid carbon state)
  - GET /session/{id}    (recent training metrics + cumulative)

The active session_id is read from greentrain/.active_session (written by
train_demo.py --remote). Override with --session-id.

Run:
  python scripts/dashboard.py
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from greentrain_agent import GreenTrainClient


ROOT = Path(__file__).resolve().parent.parent

STATE_COLOR = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}
STATE_ICON = {"GREEN": "●", "YELLOW": "●", "RED": "●"}
SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[float], width: int = 50) -> str:
    if not values:
        return ""
    vals = values[-width:]
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return SPARK_CHARS[1] * len(vals)
    out = []
    for v in vals:
        idx = int((v - lo) / (hi - lo) * (len(SPARK_CHARS) - 1))
        out.append(SPARK_CHARS[max(0, min(idx, len(SPARK_CHARS) - 1))])
    return "".join(out)


def render_grid_panel(state_data: dict | None) -> Panel:
    if not state_data:
        return Panel(Text("…connecting…", style="dim"), title="Grid", border_style="dim")
    state = state_data.get("state", "GREEN")
    color = STATE_COLOR.get(state, "white")
    icon = STATE_ICON.get(state, "?")
    body = Table.grid(padding=(0, 1))
    body.add_column(justify="right", style="bold")
    body.add_column()
    body.add_row(
        f"[{color}]{icon}[/{color}]",
        f"[bold {color}]{state}[/bold {color}]   {state_data.get('zone') or '?'}   {state_data.get('carbon_g_kwh') or '—'} gCO₂/kWh",
    )
    body.add_row("source:", str(state_data.get("source") or "—"))
    body.add_row("updated:", str(state_data.get("updated_at") or "—"))
    if state_data.get("sim_until"):
        body.add_row("[dim]sim until:[/dim]", str(state_data.get("sim_until")))
    return Panel(body, title="Grid (AWS Lambda → DynamoDB)", border_style=color)


def render_session_panel(session_data: dict | None, session_id: str) -> Panel:
    if not session_data or not session_data.get("samples"):
        return Panel(
            Text(f"…no samples yet for session {session_id}…", style="dim"),
            title=f"Session {session_id}",
            border_style="dim",
        )

    samples = session_data["samples"]
    latest = session_data.get("latest") or samples[-1]
    powers = [float(s.get("power_w", 0)) for s in samples]

    state = latest.get("state", "GREEN")
    color = STATE_COLOR.get(state, "white")

    grid = Table.grid(padding=(0, 1))
    grid.add_column(justify="right", style="bold")
    grid.add_column()
    grid.add_row("power:", f"[bold]{float(latest.get('power_w', 0)):.1f} W[/bold]   util {int(latest.get('util_pct', 0))}%")
    grid.add_row("state:", f"[{color}]{state}[/{color}]")
    grid.add_row("batch avg:", f"{float(latest.get('batch_seconds', 0)):.3f} s   sleep avg {float(latest.get('sleep_seconds', 0)):.3f} s")
    grid.add_row("samples:", f"{len(samples)} (showing last {len(samples)})")
    grid.add_row("sparkline:", f"[bold]{sparkline(powers)}[/bold]")
    grid.add_row("range:", f"{min(powers):.1f} — {max(powers):.1f} W")
    grid.add_row("", "")
    grid.add_row("[bold]Σ energy:[/bold]", f"{float(latest.get('cumulative_energy_wh', 0)):.3f} Wh")
    grid.add_row("[bold]Σ CO₂ used:[/bold]", f"{float(latest.get('cumulative_co2_g', 0)):.3f} g")

    return Panel(grid, title=f"Session {session_id}", border_style=color)


def render(state_data, session_data, session_id) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="grid", size=8),
        Layout(name="session"),
    )
    layout["grid"].update(render_grid_panel(state_data))
    layout["session"].update(render_session_panel(session_data, session_id))
    return layout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()

    session_id = args.session_id
    if not session_id:
        active_file = ROOT / ".active_session"
        if active_file.exists():
            session_id = active_file.read_text().strip()
        else:
            print("No session_id given and .active_session not found.")
            print("Pass --session-id or run train_demo.py --remote first.")
            sys.exit(1)

    client = GreenTrainClient()
    console = Console()

    state_data = None
    session_data = None

    with Live(render(state_data, session_data, session_id), console=console, refresh_per_second=4, screen=True) as live:
        while True:
            try:
                state_data = client._request("GET", "/state")
            except Exception as e:
                state_data = {"state": "ERR", "source": f"fetch failed: {e}"}
            try:
                session_data = client.get_session(session_id, limit=args.limit)
            except Exception as e:
                session_data = None
            live.update(render(state_data, session_data, session_id))
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
