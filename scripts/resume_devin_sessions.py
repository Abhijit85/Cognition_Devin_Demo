#!/usr/bin/env python3
"""Send a resume message to active Devin remediation sessions."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from orchestrator import db  # noqa: E402
from orchestrator.devin_client import get_client  # noqa: E402


DEFAULT_MESSAGE = """
Repository access has been granted for https://github.com/Abhijit85/superset.
Please continue the remediation task, push your branch to Abhijit85/superset,
open the PR, and comment the PR link on the source GitHub issue.
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message", default=DEFAULT_MESSAGE)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    client = get_client()
    rows = [
        row for row in db.get_sessions_with_findings()
        if not row["devin_session_id"].startswith("devin-mock")
        and row["status"] in {"new", "running", "suspended"}
    ]
    if args.limit:
        rows = rows[:args.limit]

    for row in rows:
        client.send_message(row["devin_session_id"], args.message)
        print(f"resumed {row['devin_session_id']} {row.get('github_issue_url')}")

    print(f"resumed={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
