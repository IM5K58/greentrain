"""
Triggered by EventBridge every 15 minutes.
Fetches current grid carbon intensity from ElectricityMap,
classifies GREEN/YELLOW/RED, writes to state table.

Honors a simulator override: if state.source == 'simulator' and
sim_until is in the future, skip the upstream write.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

import boto3

STATE_TABLE = os.environ["STATE_TABLE"]
ZONE = os.environ.get("ELECTRICITY_MAP_ZONE", "KR")
API_KEY = os.environ.get("ELECTRICITY_MAP_API_KEY", "")
THRESH_GREEN = float(os.environ.get("THRESH_GREEN", "400"))
THRESH_RED = float(os.environ.get("THRESH_RED", "600"))

ddb = boto3.resource("dynamodb")
table = ddb.Table(STATE_TABLE)


def classify(g_per_kwh: float) -> str:
    if g_per_kwh < THRESH_GREEN:
        return "GREEN"
    if g_per_kwh < THRESH_RED:
        return "YELLOW"
    return "RED"


def fetch_intensity() -> float | None:
    if not API_KEY:
        return None
    url = f"https://api.electricitymap.org/v3/carbon-intensity/latest?zone={ZONE}"
    req = urllib.request.Request(url, headers={"auth-token": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return float(data["carbonIntensity"])
    except (urllib.error.URLError, KeyError, ValueError) as e:
        print(f"[carbon_judge] fetch failed: {e}")
        return None


def handler(event, context):
    now = datetime.now(timezone.utc)
    existing = table.get_item(Key={"id": "current"}).get("Item", {})

    if existing.get("source") == "simulator":
        sim_until = existing.get("sim_until", "")
        if sim_until and now.isoformat() < sim_until:
            print(f"[carbon_judge] simulator override active until {sim_until}, skipping")
            return {"skipped": True, "reason": "simulator_override"}

    intensity = fetch_intensity()
    if intensity is None:
        kept = existing.get("state", "GREEN")
        print(f"[carbon_judge] no upstream data, keeping {kept}")
        return {"skipped": True, "reason": "no_upstream", "state": kept}

    state = classify(intensity)
    item = {
        "id": "current",
        "state": state,
        "carbon_g_kwh": Decimal(str(round(intensity, 2))),
        "zone": ZONE,
        "source": "electricitymap",
        "updated_at": now.isoformat(),
    }
    table.put_item(Item=item)
    print(f"[carbon_judge] state={state} intensity={intensity:.1f} gCO2/kWh")
    return {"state": state, "intensity": intensity}
