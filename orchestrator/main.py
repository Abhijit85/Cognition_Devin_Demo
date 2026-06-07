"""
FastAPI orchestrator.

Endpoints:
  POST /scan/run           — Triggered by GitHub Action / cron / manual. Runs
                             a scan, files issues, spawns Devin sessions.
  POST /github/webhook     — Triggered when a new issue with label
                             `devin-remediate` is opened. Spawns one session.
  GET  /healthz            — Liveness.
  GET  /findings           — List known findings (for the dashboard).
  GET  /sessions           — List Devin sessions we've spawned.
  GET  /runs               — List scan runs.

Design notes:
  - We start a background poller on app startup that periodically updates
    session status from Devin and posts PR links back to GitHub issues.
  - All Devin calls go through DevinClient (or MockDevinClient).
  - State lives in SQLite.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

load_dotenv()

from . import db
from .devin_client import DevinAPIError, get_client
from .github_client import GitHubClient, issue_body_for_finding
from .poller import poll_once
from .scanner import scan_repo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")

PLAYBOOK_PATH = Path(__file__).parent.parent / "playbooks" / "cve_remediation_v1.md"


def _load_playbook() -> str:
    try:
        return PLAYBOOK_PATH.read_text()
    except FileNotFoundError:
        logger.warning("Playbook file not found at %s", PLAYBOOK_PATH)
        return "Remediate the dependency issue described below."


def _build_prompt(finding: dict[str, Any], playbook: str) -> str:
    """Compose the prompt sent to Devin: playbook SOP + finding payload."""
    gh_repo = os.environ.get("GH_REPO", "Abhijit85/superset")
    repo_url = f"https://github.com/{gh_repo}.git"
    return f"""{playbook}

---
## Finding to remediate

- **Repository**: {repo_url}
- **Default branch**: master
- **CVE**: {finding.get('cve_id', 'N/A')}
- **Package**: {finding['package']}
- **Current version**: {finding.get('current_version', 'unknown')}
- **Target fixed version**: {finding.get('fixed_version', 'latest')}
- **Severity**: {finding.get('severity', 'UNKNOWN')}
- **Source GitHub issue**: {finding.get('github_issue_url') or 'N/A'}

Execute the SOP above against the forked Apache Superset repository at \
`{repo_url}`. Open the PR against `{gh_repo}`, not upstream Apache. Open one \
PR per finding. The PR title MUST start with `chore(deps): bump \
{finding['package']}` and include the CVE ID in the body.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    logger.info("DB initialized at %s", db.DB_PATH)

    # Light background poller — every POLL_INTERVAL seconds, check active
    # sessions and update their status. Avoids us needing a separate process.
    interval = int(os.environ.get("POLL_INTERVAL", "30"))
    stop_event = asyncio.Event()

    async def poller_loop() -> None:
        while not stop_event.is_set():
            try:
                poll_once()
            except Exception:
                logger.exception("Poller iteration failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    task = asyncio.create_task(poller_loop())
    logger.info("Background poller started (interval=%ss)", interval)

    yield

    stop_event.set()
    await task


app = FastAPI(
    title="Devin CVE Remediation Orchestrator",
    description="Event-driven automation that fans CVE findings out to Devin "
                "sessions and tracks remediation PRs.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scan/run")
def trigger_scan(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """Run a scan, file issues, and spawn Devin sessions.

    Returns immediately with a run_id; work happens in the background to
    keep the HTTP call cheap for the GitHub Action that triggers it.
    """
    run_id = str(uuid.uuid4())
    db.start_run(run_id, trigger="scheduled")
    background_tasks.add_task(_execute_scan, run_id)
    return {"run_id": run_id, "status": "started"}


@app.post("/github/webhook")
async def github_webhook(request: Request) -> dict[str, Any]:
    """Handle GitHub issue webhooks.

    We only act on `issues.opened` for issues labeled `devin-remediate`.
    Production: validate the X-Hub-Signature-256 HMAC header.
    """
    payload = await request.json()
    action = payload.get("action")
    issue = payload.get("issue", {})
    labels = [l.get("name") for l in issue.get("labels", [])]

    if action != "opened" or "devin-remediate" not in labels:
        return {"ignored": True, "reason": "not a remediation request"}

    # Build a finding from the issue body (minimal parse for the demo)
    finding = {
        "fingerprint": f"webhook:{issue['number']}",
        "cve_id": _extract_cve(issue.get("title", "")),
        "package": _extract_package(issue.get("body", "")),
        "current_version": None,
        "fixed_version": None,
        "severity": "UNKNOWN",
        "source": "webhook",
        "github_issue_number": issue["number"],
        "github_issue_url": issue.get("html_url"),
    }
    row = db.upsert_finding(**{
        k: finding[k] for k in [
            "fingerprint", "cve_id", "package", "current_version",
            "fixed_version", "severity", "source",
            "github_issue_number", "github_issue_url",
        ]
    })
    _spawn_session_for_finding(row)
    return {"accepted": True, "finding_id": row["id"]}


@app.get("/findings")
def list_findings_endpoint(status: str | None = None) -> list[dict[str, Any]]:
    return db.list_findings(status=status)


@app.get("/sessions")
def list_sessions_endpoint() -> list[dict[str, Any]]:
    return db.get_sessions_with_findings()


@app.get("/runs")
def list_runs_endpoint() -> list[dict[str, Any]]:
    return db.list_runs()


# ----------------- internals -----------------

def _execute_scan(run_id: str) -> None:
    """Background task: scan, file issues, spawn sessions."""
    logger.info("Run %s: starting scan", run_id)
    repo_path = Path(os.environ.get("REPO_PATH", "."))
    findings = scan_repo(repo_path)
    logger.info("Run %s: scanner returned %d findings", run_id, len(findings))

    gh = GitHubClient()
    sessions_spawned = 0
    for f in findings:
        # File GitHub issue (idempotent at the DB level via fingerprint)
        row = db.upsert_finding(
            fingerprint=f["fingerprint"],
            cve_id=f.get("cve_id"),
            package=f["package"],
            current_version=f.get("current_version"),
            fixed_version=f.get("fixed_version"),
            severity=f.get("severity"),
            source=f.get("source", "scanner"),
        )

        # Only file GH issue + spawn session if status is still 'open'
        if row["status"] != "open":
            continue

        if gh.enabled and not row.get("github_issue_url"):
            try:
                issue = gh.create_issue(
                    title=f"[{f.get('severity', 'UNKNOWN')}] "
                          f"{f.get('cve_id', 'CVE-UNKNOWN')} in {f['package']}",
                    body=issue_body_for_finding(f),
                    labels=["devin-remediate", "security",
                            f.get("severity", "unknown").lower()],
                )
                # Update DB with issue URL
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE findings SET github_issue_number = ?, "
                        "github_issue_url = ? WHERE id = ?",
                        (issue["number"], issue["html_url"], row["id"]),
                    )
                row["github_issue_url"] = issue["html_url"]
                row["github_issue_number"] = issue["number"]
            except Exception:
                logger.exception("Failed to file GH issue for %s",
                                 f["fingerprint"])

        _spawn_session_for_finding(row)
        sessions_spawned += 1

    db.finish_run(run_id, len(findings), sessions_spawned)
    logger.info("Run %s: done. %d sessions spawned.", run_id, sessions_spawned)


def _spawn_session_for_finding(finding: dict[str, Any]) -> None:
    """Create one Devin session for the given finding."""
    playbook = _load_playbook()
    prompt = _build_prompt(finding, playbook)

    tags = [
        "cve-remediation",
        f"severity:{(finding.get('severity') or 'unknown').lower()}",
        f"package:{finding['package']}",
        f"source:{finding.get('source', 'unknown')}",
    ]

    client = get_client()
    try:
        session = client.create_session(prompt=prompt, tags=tags)
    except DevinAPIError as exc:
        logger.error("Failed to create Devin session: %s", exc)
        db.update_finding_status(finding["id"], "failed")
        return

    db.record_session(
        finding_id=finding["id"],
        devin_session_id=session["session_id"],
        devin_session_url=session.get("url", ""),
        status=session.get("status", "running"),
        tags=tags,
    )
    db.update_finding_status(finding["id"], "in_progress")

    # Post the session link back to the GitHub issue
    if finding.get("github_issue_number"):
        gh = GitHubClient()
        gh.comment_on_issue(
            finding["github_issue_number"],
            f"🤖 Devin session started: {session.get('url')}\n\n"
            f"Session ID: `{session['session_id']}`\n"
            f"Tags: `{', '.join(tags)}`",
        )

    logger.info(
        "Spawned Devin session %s for finding %s (%s)",
        session["session_id"], finding["id"], finding["fingerprint"],
    )


def _extract_cve(text: str) -> str | None:
    import re
    m = re.search(r"CVE-\d{4}-\d+", text or "")
    return m.group(0) if m else None


def _extract_package(text: str) -> str:
    r"""Naive extraction — look for `**Package:** \`name\`` line."""
    import re
    m = re.search(r"\*\*Package:\*\*\s*`([^`]+)`", text or "")
    return m.group(1) if m else "unknown"
