"""
Trigger /simulate to force the grid state. Use during live demo.

Usage:
  python scripts/simulate.py RED
  python scripts/simulate.py YELLOW --duration 3
  python scripts/simulate.py GREEN
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from greentrain_agent import GreenTrainClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", choices=["GREEN", "YELLOW", "RED"])
    parser.add_argument("--duration", type=int, default=5, help="minutes to hold the override")
    args = parser.parse_args()

    client = GreenTrainClient()
    result = client.simulate(args.state, args.duration)
    print(f"-> grid forced to {result['state']} until {result['sim_until']}")


if __name__ == "__main__":
    main()
