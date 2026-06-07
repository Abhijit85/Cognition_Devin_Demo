#!/usr/bin/env python3
"""Spawn Devin remediation sessions from existing GitHub issues."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from orchestrator import db  # noqa: E402
from orchestrator.main import _spawn_session_for_finding  # noqa: E402


def field(body: str, name: str) -> str | None:
    pattern = rf"\*\*{re.escape(name)}:\*\*\s*`?([^`\n]+)`?"
    match = re.search(pattern, body)
    if not match:
        return None
    value = match.group(1).strip()
    if value in {"None", "unknown", "unavailable from scanner"}:
        return None
    return value


def cve_from_issue(issue: dict[str, Any]) -> str | None:
    text = f"{issue.get('title', '')}\n{issue.get('body', '')}"
    match = re.search(r"CVE-\d{4}-\d+", text)
    return match.group(0) if match else None


def finding_from_issue(repo: str, issue: dict[str, Any]) -> dict[str, Any]:
    body = issue.get("body") or ""
    package = field(body, "Package") or "unknown"
    cve = cve_from_issue(issue)
    return {
        "fingerprint": f"github:{repo}#{issue['number']}",
        "cve_id": cve,
        "package": package,
        "current_version": field(body, "Current version"),
        "fixed_version": field(body, "Fixed version"),
        "severity": field(body, "Severity") or "UNKNOWN",
        "source": "github-issue",
        "github_issue_number": issue["number"],
        "github_issue_url": issue["html_url"],
    }


def existing_issue_sessions() -> set[int]:
    sessions = db.get_sessions_with_findings()
    issue_numbers: set[int] = set()
    for session in sessions:
        issue_url = session.get("github_issue_url") or ""
        match = re.search(r"/issues/(\d+)$", issue_url)
        if match:
            issue_numbers.add(int(match.group(1)))
    return issue_numbers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--label", default="devin-remediate")
    args = parser.parse_args()

    repo = os.environ["GH_REPO"]
    token = os.environ["GH_TOKEN"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    db.init_db()
    already_spawned = existing_issue_sessions()

    with httpx.Client(timeout=30.0, headers=headers) as client:
        response = client.get(
            f"https://api.github.com/repos/{repo}/issues",
            params={
                "state": "open",
                "labels": args.label,
                "per_page": 100,
                "sort": "created",
                "direction": "asc",
            },
        )
        response.raise_for_status()
        issues = [
            issue for issue in response.json()
            if "pull_request" not in issue
            and issue["number"] not in already_spawned
        ]

    if args.limit:
        issues = issues[:args.limit]

    spawned = 0
    skipped = len(already_spawned)
    for issue in issues:
        finding = finding_from_issue(repo, issue)
        row = db.upsert_finding(**finding)
        if row["status"] != "open":
            print(f"skip #{issue['number']}: status={row['status']}")
            skipped += 1
            continue
        _spawn_session_for_finding(row)
        spawned += 1
        print(f"spawned #{issue['number']}: {issue['html_url']}")

    print(f"spawned={spawned} skipped_existing={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
