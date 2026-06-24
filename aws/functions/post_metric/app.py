"""
POST /metric — record a batch sample from the local agent.
Body:
  {
    "session_id": "uuid",
    "power_w": 95.2,
    "util_pct": 78,
    "batch_seconds": 0.5,
    "sleep_seconds": 0.0,
    "state": "GREEN",
    "energy_wh": 0.013,
    "cumulative_energy_wh": 1.234,
    "cumulative_co2_g": 0.567
  }
"""
import json
import os
import time
from decimal import Decimal

import boto3

METRICS_TABLE = os.environ["METRICS_TABLE"]
ddb = boto3.resource("dynamodb")
table = ddb.Table(METRICS_TABLE)


def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _num(v) -> Decimal:
    return Decimal(str(v))


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _resp(400, {"error": "invalid_json"})

    session_id = body.get("session_id")
    if not session_id:
        return _resp(400, {"error": "missing_session_id"})

    ts = int(time.time() * 1000)
    item = {
        "session_id": session_id,
        "ts": ts,
    }
    for key in (
        "power_w",
        "util_pct",
        "batch_seconds",
        "sleep_seconds",
        "energy_wh",
        "cumulative_energy_wh",
        "cumulative_co2_g",
        "cumulative_compute_seconds",
        "cumulative_throttle_seconds",
    ):
        if key in body and body[key] is not None:
            item[key] = _num(body[key])
    if "state" in body:
        item["state"] = body["state"]

    table.put_item(Item=item)
    return _resp(200, {"ok": True, "ts": ts})
