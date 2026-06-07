"""
Smoke tests. Verify the orchestrator endpoints work end-to-end in mock
mode. Designed to run in CI without needing real Devin credentials.

Run: pytest tests/
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_env(monkeypatch, tmp_path):
    """Force mock mode and isolate DB per test."""
    monkeypatch.setenv("DEVIN_MOCK", "1")
    monkeypatch.setenv("DEVIN_ORG_ID", "test-org")
    monkeypatch.setenv("GH_TOKEN", "")
    monkeypatch.setenv("GH_REPO", "")
    # Redirect DB to a temp file so tests don't interfere with each other
    from orchestrator import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    # Reset the mock client singleton so each test gets a fresh counter
    from orchestrator import devin_client
    monkeypatch.setattr(devin_client, "_mock_singleton", None)


@pytest.fixture
def client():
    from orchestrator.main import app
    with TestClient(app) as c:
        yield c


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_trigger_scan_creates_findings_and_sessions(client):
    # Trigger a scan
    r = client.post("/scan/run")
    assert r.status_code == 200
    assert "run_id" in r.json()

    # Background tasks complete before TestClient returns response, so
    # findings and sessions should be present immediately
    findings = client.get("/findings").json()
    assert len(findings) > 0, "Scan should have produced findings"

    sessions = client.get("/sessions").json()
    assert len(sessions) > 0, "Findings should have spawned sessions"
    assert all(s["devin_session_id"].startswith("devin-mock-") for s in sessions)


def test_runs_recorded(client):
    client.post("/scan/run")
    runs = client.get("/runs").json()
    assert len(runs) >= 1
    assert runs[0]["trigger"] == "scheduled"


def test_findings_deduped_across_runs(client):
    client.post("/scan/run")
    n_after_first = len(client.get("/findings").json())
    client.post("/scan/run")
    n_after_second = len(client.get("/findings").json())
    # Same fixtures → no new findings on second run
    assert n_after_first == n_after_second


def test_webhook_ignores_unlabeled_issues(client):
    payload = {
        "action": "opened",
        "issue": {
            "number": 42,
            "title": "Random bug report",
            "body": "Something broke",
            "labels": [{"name": "bug"}],
            "html_url": "https://github.com/test/repo/issues/42",
        },
    }
    r = client.post("/github/webhook", json=payload)
    assert r.status_code == 200
    assert r.json().get("ignored") is True


def test_webhook_accepts_labeled_issues(client):
    payload = {
        "action": "opened",
        "issue": {
            "number": 99,
            "title": "CVE-2024-99999 in requests",
            "body": "**Package:** `requests`\n\nVulnerable version pinned.",
            "labels": [{"name": "devin-remediate"}],
            "html_url": "https://github.com/test/repo/issues/99",
        },
    }
    r = client.post("/github/webhook", json=payload)
    assert r.status_code == 200
    assert r.json().get("accepted") is True
