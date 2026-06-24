"""Thin HTTP client for the GreenTrain AWS backend."""
import json
import os
import urllib.error
import urllib.request

from .state import CarbonState


class GreenTrainClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = (base_url or os.environ.get("GREENTRAIN_API_URL", "")).rstrip("/")
        if not self.base_url:
            raise RuntimeError(
                "GREENTRAIN_API_URL not set. Put it in .env or pass base_url=."
            )
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["content-type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    def get_state(self) -> CarbonState:
        data = self._request("GET", "/state")
        return CarbonState(data.get("state", "GREEN"))

    def post_metric(self, **metric) -> dict:
        return self._request("POST", "/metric", metric)

    def simulate(self, state: str, duration_minutes: int = 5) -> dict:
        return self._request(
            "POST",
            "/simulate",
            {"state": state, "duration_minutes": duration_minutes},
        )

    def get_session(self, session_id: str, limit: int = 60) -> dict:
        return self._request("GET", f"/session/{session_id}?limit={limit}")
