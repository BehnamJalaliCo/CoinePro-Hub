"""The hub's internal api, as the provisioner uses it (service principal
`provisioner`; prompt 09's api side, contract §18.8):

Under /internal/v1/provisioning/runs:
GET  /next             204, or {run: {...}}: the next run of a SEALED plan
GET  /{id}             the run (its state, the callback's results: cloud_init)
POST /{id}/callback    {token_sha256, expires_at}: the one-time token's digest
POST /{id}/steps       {key, state, started_at?, finished_at?, log_tail}
POST /{id}/server      {hetzner_id, name, ipv4, ipv6, private_ip, labels}
POST /{id}/finish      {state: done|failed, login?, error?}

A run handed out is {id, state, plan: ServerPlan (with digest), sealed_digest,
steps: [{key, state}]}. The token's plaintext never goes to the api (only its
sha256): it lives in the new server's user data and is spent by its callback.
"""

from __future__ import annotations

from typing import Any

import httpx


class HubError(Exception):
    pass


class Hub:
    def __init__(
        self,
        base_url: str,
        token: Any,  # a callable returning the token (read when needed)
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20,
    ) -> None:
        self._token = token
        self._http = httpx.Client(
            base_url=base_url, timeout=timeout, transport=transport, trust_env=False
        )

    def close(self) -> None:
        self._http.close()

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> httpx.Response:
        try:
            r = self._http.request(
                method,
                path,
                json=body,
                headers={"Authorization": f"Bearer {self._token()}"},
            )
        except httpx.HTTPError as exc:
            raise HubError(f"api unreachable ({type(exc).__name__})") from exc
        if r.status_code >= 400:
            raise HubError(f"api answered {r.status_code} on {path}")
        return r

    def next_run(self) -> dict[str, Any] | None:
        r = self._call("GET", "/internal/v1/provisioning/runs/next")
        if r.status_code == 204 or not r.content:
            return None
        run = r.json().get("run")
        return run if isinstance(run, dict) else None

    def run(self, run_id: str) -> dict[str, Any]:
        data: dict[str, Any] = self._call("GET", f"/internal/v1/provisioning/runs/{run_id}").json()
        return data

    def callback(self, run_id: str, token_sha256: str, expires_at: str) -> None:
        self._call(
            "POST",
            f"/internal/v1/provisioning/runs/{run_id}/callback",
            {"token_sha256": token_sha256, "expires_at": expires_at},
        )

    def step(self, run_id: str, body: dict[str, Any]) -> None:
        self._call("POST", f"/internal/v1/provisioning/runs/{run_id}/steps", body)

    def server(self, run_id: str, body: dict[str, Any]) -> None:
        self._call("POST", f"/internal/v1/provisioning/runs/{run_id}/server", body)

    def finish(self, run_id: str, body: dict[str, Any]) -> None:
        self._call("POST", f"/internal/v1/provisioning/runs/{run_id}/finish", body)
