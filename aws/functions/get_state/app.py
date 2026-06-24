"""
GET /state — return current grid state.
Response:
  { "state": "GREEN" | "YELLOW" | "RED", "carbon_g_kwh": number, "source": "...", "updated_at": "...", "zone": "KR" }
"""
import json
import os
from decimal import Decimal

import boto3

STATE_TABLE = os.environ["STATE_TABLE"]
ddb = boto3.resource("dynamodb")
table = ddb.Table(STATE_TABLE)


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _resp(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def handler(event, context):
    item = table.get_item(Key={"id": "current"}).get("Item")
    if not item:
        return _resp(200, {
            "state": "GREEN",
            "source": "default",
            "carbon_g_kwh": None,
            "updated_at": None,
            "zone": None,
        })
    return _resp(200, {
        "state": item.get("state", "GREEN"),
        "carbon_g_kwh": item.get("carbon_g_kwh"),
        "source": item.get("source"),
        "updated_at": item.get("updated_at"),
        "zone": item.get("zone"),
        "sim_until": item.get("sim_until"),
    })
