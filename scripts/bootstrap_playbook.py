#!/usr/bin/env python3
"""
One-shot bootstrap: register the CVE Remediation Playbook with Devin.

Run once per environment after deploying:

    python scripts/bootstrap_playbook.py

Idempotent: if a playbook with the same name already exists, prints its ID
and exits without creating a duplicate.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from orchestrator.devin_client import get_client  # noqa: E402

PLAYBOOK_NAME = "CVE Remediation SOP v1"
PLAYBOOK_FILE = ROOT / "playbooks" / "cve_remediation_v1.md"


def main() -> int:
    client = get_client()
    me = client.whoami()
    print(f"Authenticated: {me.get('service_user_name', '?')} "
          f"(org: {me.get('org_id', '?')})")

    instructions = PLAYBOOK_FILE.read_text()

    # Check for existing
    existing = client.list_playbooks()
    items = existing.get("items", existing) if isinstance(existing, dict) else []
    for pb in items if isinstance(items, list) else []:
        if pb.get("name") == PLAYBOOK_NAME:
            print(f"Playbook already registered: {pb.get('playbook_id')}")
            return 0

    created = client.create_playbook(
        name=PLAYBOOK_NAME, instructions=instructions
    )
    print(f"Created playbook: {created.get('playbook_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
