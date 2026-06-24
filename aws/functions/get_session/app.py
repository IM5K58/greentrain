"""
GET /session/{session_id}?limit=60 — return the most recent N metric samples
for a training session, plus the latest sample (which carries cumulative totals).
"""
import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

METRICS_TABLE = os.environ["METRICS_TABLE"]
ddb = boto3.resource("dynamodb")
table = ddb.Table(METRICS_TABLE)


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
    path_params = event.get("pathParameters") or {}
    session_id = path_params.get("session_id")
    if not session_id:
        return _resp(400, {"error": "missing_session_id"})

    qs = event.get("queryStringParameters") or {}
    try:
        limit = max(1, min(int(qs.get("limit", "60")), 200))
    except (TypeError, ValueError):
        limit = 60

    resp = table.query(
        KeyConditionExpression=Key("session_id").eq(session_id),
        ScanIndexForward=False,
        Limit=limit,
    )
    items = resp.get("Items", [])
    latest = items[0] if items else None
    return _resp(200, {
        "session_id": session_id,
        "count": len(items),
        "latest": latest,
        "samples": list(reversed(items)),
    })
