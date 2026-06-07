"""
Thin wrapper around the Devin v3 API.

We deliberately keep this small: most of the orchestration value lives in
Devin's native primitives (Playbooks, Tags, Metrics). Our job is to glue
events to sessions, not to re-implement what Devin already provides.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DevinAPIError(Exception):
    """Raised when the Devin API returns a non-2xx response."""


class DevinClient:
    """Minimal client for the Devin v3 Organization API.

    Auth: service user API key (cog_ prefix).
    Docs: https://docs.devin.ai/api-reference/overview
    """

    def __init__(
        self,
        api_key: str | None = None,
        org_id: str | None = None,
        base_url: str = "https://api.devin.ai/v3",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.environ["DEVIN_API_KEY"]
        self.org_id = org_id or os.environ["DEVIN_ORG_ID"]
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

    # ---------- internal ----------

    def _org_url(self, path: str) -> str:
        return f"{self.base_url}/organizations/{self.org_id}/{path.lstrip('/')}"

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            r = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise DevinAPIError(f"Network error talking to Devin: {exc}") from exc

        if r.status_code >= 400:
            raise DevinAPIError(
                f"Devin API {method} {url} returned {r.status_code}: {r.text[:500]}"
            )
        # 204 No Content possible on some endpoints
        if not r.content:
            return {}
        return r.json()

    # ---------- auth / discovery ----------

    def whoami(self) -> dict[str, Any]:
        """Verify credentials. Returns service user details."""
        return self._request("GET", f"{self.base_url}/self")

    # ---------- sessions ----------

    def create_session(
        self,
        prompt: str,
        tags: list[str] | None = None,
        playbook_id: str | None = None,
        create_as_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Devin session. Returns {session_id, url, status}."""
        body: dict[str, Any] = {"prompt": prompt}
        if tags:
            body["tags"] = tags
        if playbook_id:
            # The v3 API embeds playbook context via the prompt + Knowledge.
            # We pass it explicitly here so the field is available if/when
            # Devin promotes playbook_id to a first-class session field.
            body["playbook_id"] = playbook_id
        if create_as_user_id:
            body["create_as_user_id"] = create_as_user_id
        return self._request("POST", self._org_url("sessions"), json=body)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", self._org_url(f"sessions/{session_id}"))

    def list_session_messages(self, session_id: str) -> dict[str, Any]:
        return self._request(
            "GET", self._org_url(f"sessions/{session_id}/messages")
        )

    def send_message(self, session_id: str, message: str) -> dict[str, Any]:
        return self._request(
            "POST",
            self._org_url(f"sessions/{session_id}/messages"),
            json={"message": message},
        )

    def append_tags(self, session_id: str, tags: list[str]) -> dict[str, Any]:
        return self._request(
            "POST",
            self._org_url(f"sessions/{session_id}/tags"),
            json={"tags": tags},
        )

    def list_sessions(
        self, limit: int = 50, cursor: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", self._org_url("sessions"), params=params)

    # ---------- playbooks ----------

    def create_playbook(self, name: str, instructions: str) -> dict[str, Any]:
        return self._request(
            "POST",
            self._org_url("playbooks"),
            json={"title": name, "body": instructions},
        )

    def list_playbooks(self) -> dict[str, Any]:
        return self._request("GET", self._org_url("playbooks"))

    # ---------- knowledge ----------

    def create_knowledge_note(
        self, name: str, trigger: str, body: str
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            self._org_url("knowledge/notes"),
            json={"name": name, "trigger": trigger, "body": body},
        )

    # ---------- metrics (the observability story) ----------

    def get_session_metrics(
        self, start_date: str, end_date: str
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            self._org_url("metrics/sessions"),
            params={"start_date": start_date, "end_date": end_date},
        )

    def get_pr_metrics(self, start_date: str, end_date: str) -> dict[str, Any]:
        return self._request(
            "GET",
            self._org_url("metrics/prs"),
            params={"start_date": start_date, "end_date": end_date},
        )

    def get_daily_consumption(
        self, start_date: str, end_date: str
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            self._org_url("consumption/daily"),
            params={"start_date": start_date, "end_date": end_date},
        )

    # ---------- schedules ----------

    def create_schedule(
        self, prompt: str, cron: str, timezone: str = "UTC"
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            self._org_url("schedules"),
            json={
                "prompt": prompt,
                "cron_schedule": cron,
                "timezone": timezone,
            },
        )

    def close(self) -> None:
        self._client.close()


class MockDevinClient(DevinClient):
    """Drop-in client for local development without API credentials.

    Useful for: building the orchestrator + dashboard end-to-end without
    burning ACU, and for letting evaluators run the demo without keys.
    Toggled by DEVIN_MOCK=1.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        # Don't call super().__init__ — we don't need real auth.
        self.org_id = kwargs.get("org_id") or os.environ.get(
            "DEVIN_ORG_ID", "mock-org"
        )
        self._counter = 0
        self._sessions: dict[str, dict[str, Any]] = {}

    def whoami(self) -> dict[str, Any]:
        return {
            "principal_type": "service_user",
            "service_user_name": "MockBot",
            "org_id": self.org_id,
        }

    def create_session(
        self,
        prompt: str,
        tags: list[str] | None = None,
        playbook_id: str | None = None,
        create_as_user_id: str | None = None,
    ) -> dict[str, Any]:
        self._counter += 1
        sid = f"devin-mock-{self._counter:04d}"
        self._sessions[sid] = {
            "session_id": sid,
            "url": f"https://app.devin.ai/sessions/{sid}",
            "status": "running",
            "tags": tags or [],
            "prompt": prompt,
            "ticks": 0,
        }
        logger.info("MOCK: created session %s", sid)
        return {
            "session_id": sid,
            "url": self._sessions[sid]["url"],
            "status": "running",
        }

    def get_session(self, session_id: str) -> dict[str, Any]:
        s = self._sessions.get(session_id)
        if not s:
            raise DevinAPIError(f"Mock session {session_id} not found")
        # Simulate progression: running → exit after 3 polls
        s["ticks"] += 1
        if s["ticks"] >= 3 and s["status"] == "running":
            s["status"] = "exit"
            s["pull_request_url"] = (
                f"https://github.com/example/superset/pull/{1000 + self._counter}"
            )
        return dict(s)

    def append_tags(self, session_id: str, tags: list[str]) -> dict[str, Any]:
        if session_id in self._sessions:
            self._sessions[session_id]["tags"] = list(
                set(self._sessions[session_id]["tags"] + tags)
            )
        return {"ok": True}

    def create_playbook(self, name: str, instructions: str) -> dict[str, Any]:
        return {"playbook_id": "pb-mock-001", "name": name}

    def get_session_metrics(
        self, start_date: str, end_date: str
    ) -> dict[str, Any]:
        return {
            "total_sessions": len(self._sessions),
            "completed_sessions": sum(
                1 for s in self._sessions.values() if s["status"] == "exit"
            ),
        }

    def get_pr_metrics(self, start_date: str, end_date: str) -> dict[str, Any]:
        prs = [
            s for s in self._sessions.values() if s.get("pull_request_url")
        ]
        return {"total_prs": len(prs), "merged_prs": 0}

    def get_daily_consumption(
        self, start_date: str, end_date: str
    ) -> dict[str, Any]:
        return {"total_acu": len(self._sessions) * 2.5}


_mock_singleton: MockDevinClient | None = None


def get_client() -> DevinClient:
    """Factory: returns a real or mock client based on env.

    The mock client is a process-level singleton so session IDs don't
    collide across calls within the same orchestrator process.
    """
    global _mock_singleton
    if os.environ.get("DEVIN_MOCK") == "1":
        if _mock_singleton is None:
            logger.warning("Using MOCK Devin client (DEVIN_MOCK=1)")
            _mock_singleton = MockDevinClient()
        return _mock_singleton
    return DevinClient()
