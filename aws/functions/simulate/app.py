"""
POST /simulate — force-set the grid state for demo purposes.
Body:
  { "state": "GREEN" | "YELLOW" | "RED", "duration_minutes": 5 }

The override expires after `duration_minutes`, after which carbon_judge resumes
writing real data from ElectricityMap.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

STATE_TABLE = os.environ["STATE_TABLE"]
ALLOWED = {"GREEN", "YELLOW", "RED"}

ddb = boto3.resource("dynamodb")
table = ddb.Table(STATE_TABLE)


def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid_json"})

    state = (body.get("state") or "").upper()
    if state not in ALLOWED:
        return _resp(400, {"error": "invalid_state", "allowed": sorted(ALLOWED)})

    try:
        duration = int(body.get("duration_minutes", 5))
    except (TypeError, ValueError):
        return _resp(400, {"error": "invalid_duration"})

    now = datetime.now(timezone.utc)
    sim_until = now + timedelta(minutes=duration)

    item = {
        "id": "current",
        "state": state,
        "source": "simulator",
        "updated_at": now.isoformat(),
        "sim_until": sim_until.isoformat(),
        "carbon_g_kwh": Decimal("999") if state == "RED" else Decimal("500") if state == "YELLOW" else Decimal("250"),
    }
    table.put_item(Item=item)
    return _resp(200, {
        "state": state,
        "sim_until": sim_until.isoformat(),
        "duration_minutes": duration,
    })
