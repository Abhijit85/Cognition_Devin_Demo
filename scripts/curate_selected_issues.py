#!/usr/bin/env python3
"""Focus the demo on a small set of high-value remediation issues."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from orchestrator import db  # noqa: E402
from orchestrator.devin_client import get_client  # noqa: E402


SELECTED_ISSUES = {
    1: "Core web framework exposure: Flask affects Superset request handling and extension compatibility.",
    3: "Data-plane exposure: PyArrow is central to analytics serialization and file/data interchange paths.",
    4: "Authentication exposure: PyJWT handles signed token behavior; this PR should use the 2.13.0 bump that also covers the related PyJWT CVE cluster.",
}


SELECTED_MESSAGE = """
This finding is part of the curated demo remediation scope.
Please continue the remediation, push your branch to Abhijit85/superset,
open the PR, and comment the PR link on the source GitHub issue.

Scope note: focus on the issue linked in your prompt. For PyJWT, use the
2.13.0 target and mention that the same dependency bump addresses the related
PyJWT CVE cluster where applicable.
""".strip()


DEFERRED_MESSAGE = """
This finding is deferred from the curated demo scope.
Do not open a PR for this issue. Please stop active remediation work and leave
the repository unchanged for this finding.
""".strip()


def issue_number(row: dict[str, object]) -> int | None:
    url = str(row.get("github_issue_url") or "")
    if not url:
        return None
    try:
        return int(url.rstrip("/").rsplit("/", 1)[-1])
    except ValueError:
        return None


def github_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def ensure_labels(client: httpx.Client, repo: str, number: int, labels: list[str]) -> None:
    response = client.post(
        f"https://api.github.com/repos/{repo}/issues/{number}/labels",
        json={"labels": labels},
    )
    response.raise_for_status()


def remove_label(client: httpx.Client, repo: str, number: int, label: str) -> None:
    response = client.delete(
        f"https://api.github.com/repos/{repo}/issues/{number}/labels/{label}",
    )
    if response.status_code not in {200, 204, 404}:
        response.raise_for_status()


def comment(client: httpx.Client, repo: str, number: int, body: str) -> None:
    response = client.post(
        f"https://api.github.com/repos/{repo}/issues/{number}/comments",
        json={"body": body},
    )
    response.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = os.environ["GH_REPO"]
    rows = [
        row for row in db.get_sessions_with_findings()
        if row.get("github_issue_url") and not row["devin_session_id"].startswith("devin-mock")
    ]
    devin = get_client()

    selected_count = 0
    deferred_count = 0

    with httpx.Client(timeout=30.0, headers=github_headers()) as gh:
        for row in rows:
            number = issue_number(row)
            if number is None:
                continue

            if number in SELECTED_ISSUES:
                selected_count += 1
                print(f"selected #{number}: {row['package']} {row['cve_id']}")
                if args.dry_run:
                    continue
                db.update_finding_status(row["finding_id"], "in_progress")
                if row["status"] == "deferred":
                    db.update_session(row["devin_session_id"], status="running")
                ensure_labels(gh, repo, number, ["demo-selected", "deep-importance"])
                comment(
                    gh,
                    repo,
                    number,
                    "Selected for the curated Devin remediation demo.\n\n"
                    f"Reason: {SELECTED_ISSUES[number]}",
                )
                devin.send_message(row["devin_session_id"], SELECTED_MESSAGE)
            else:
                deferred_count += 1
                print(f"deferred #{number}: {row['package']} {row['cve_id']}")
                if args.dry_run:
                    continue
                db.update_finding_status(row["finding_id"], "deferred")
                db.update_session(row["devin_session_id"], status="deferred")
                ensure_labels(gh, repo, number, ["demo-deferred"])
                remove_label(gh, repo, number, "devin-remediate")
                comment(
                    gh,
                    repo,
                    number,
                    "Deferred from the curated Devin remediation demo. "
                    "This issue remains documented, but it is not part of the active selected set.",
                )
                devin.send_message(row["devin_session_id"], DEFERRED_MESSAGE)

    print(f"selected={selected_count} deferred={deferred_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
