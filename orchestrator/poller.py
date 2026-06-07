"""
Background poller. Periodically asks Devin about the status of every
active session and updates SQLite + the linked GitHub issue.

Runs as an asyncio task inside the FastAPI app (see main.lifespan).
For a production deployment, swap this for a Celery beat / Cloud Tasks /
EventBridge schedule that hits the same DB.
"""
from __future__ import annotations

import logging
from typing import Any

from . import db
from .devin_client import DevinAPIError, get_client
from .github_client import GitHubClient

logger = logging.getLogger(__name__)


def poll_once() -> None:
    """One iteration: poll all active sessions, update state, notify GH."""
    active = db.list_active_sessions()
    if not active:
        return

    client = get_client()
    gh = GitHubClient()
    logger.info("Polling %d active session(s)", len(active))

    for s in active:
        try:
            detail = client.get_session(s["devin_session_id"])
        except DevinAPIError as exc:
            logger.warning("Poll failed for %s: %s", s["devin_session_id"], exc)
            continue

        new_status = detail.get("status", s["status"])
        pr_url = detail.get("pull_request_url") or _extract_pr_from_session(detail)

        if new_status != s["status"] or pr_url:
            db.update_session(
                s["devin_session_id"], status=new_status, pr_url=pr_url,
            )
            logger.info(
                "Session %s: %s -> %s%s",
                s["devin_session_id"], s["status"], new_status,
                f" (PR: {pr_url})" if pr_url else "",
            )

            # Surface back to GitHub
            _notify_github(s, new_status, pr_url, gh)

            # Mark finding accordingly
            if pr_url:
                db.update_finding_status(s["finding_id"], "pr_open")
            elif new_status in {"error", "failed"}:
                db.update_finding_status(s["finding_id"], "failed")


def _extract_pr_from_session(session: dict[str, Any]) -> str | None:
    """Some session schemas expose PR url under different keys; be lenient."""
    for key in ("pull_request_url", "pr_url", "pull_request"):
        if val := session.get(key):
            if isinstance(val, dict):
                return val.get("url") or val.get("html_url")
            return val
    pull_requests = session.get("pull_requests") or []
    if isinstance(pull_requests, list) and pull_requests:
        first = pull_requests[0]
        if isinstance(first, dict):
            return first.get("pr_url") or first.get("url") or first.get("html_url")
        return str(first)
    # Sometimes the PR appears nested in 'output' or 'analysis'
    output = session.get("output") or {}
    if isinstance(output, dict):
        return output.get("pull_request_url")
    return None


def _notify_github(
    session_row: dict[str, Any],
    new_status: str,
    pr_url: str | None,
    gh: GitHubClient,
) -> None:
    """Post a friendly status comment back to the source GitHub issue."""
    # Look up the finding to get its issue number
    findings_by_id = {
        f["id"]: f for f in db.list_findings()
    }
    finding = findings_by_id.get(session_row["finding_id"])
    if not finding or not finding.get("github_issue_number"):
        return

    if new_status == "exit" and pr_url:
        gh.comment_on_issue(
            finding["github_issue_number"],
            f"✅ Devin opened a PR: {pr_url}\n\n"
            f"Session: {session_row['devin_session_url']}",
        )
    elif new_status in {"error", "failed"}:
        gh.comment_on_issue(
            finding["github_issue_number"],
            f"❌ Devin session ended with status `{new_status}`. "
            f"Manual triage needed.\n\n"
            f"Session: {session_row['devin_session_url']}",
        )
