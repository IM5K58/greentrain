"""Quick GET /state and pretty-print. Use to verify backend health."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from greentrain_agent.client import GreenTrainClient


def main() -> None:
    client = GreenTrainClient()
    data = client._request("GET", "/state")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
