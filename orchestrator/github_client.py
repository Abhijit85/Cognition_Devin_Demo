"""
Minimal GitHub REST client. Used to:
  - Create issues for newly-discovered findings
  - Comment on issues with the Devin session URL and PR URL when ready

We don't use PyGithub — keeping deps minimal. Auth via a GH PAT.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    pass


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        repo: str | None = None,  # "owner/repo"
        base_url: str = "https://api.github.com",
    ) -> None:
        self.token = token or os.environ.get("GH_TOKEN", "")
        self.repo = repo or os.environ.get("GH_REPO", "")
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=20.0,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}" if self.token else "",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repo)

    def create_issue(
        self, title: str, body: str, labels: list[str] | None = None
    ) -> dict[str, Any]:
        if not self.enabled:
            logger.info("GitHub disabled — would create issue: %s", title)
            return {"number": 0, "html_url": "", "title": title}

        r = self._client.post(
            f"{self.base_url}/repos/{self.repo}/issues",
            json={"title": title, "body": body, "labels": labels or []},
        )
        if r.status_code >= 400:
            raise GitHubAPIError(f"create_issue failed: {r.status_code} {r.text}")
        return r.json()

    def comment_on_issue(self, issue_number: int, body: str) -> dict[str, Any]:
        if not self.enabled or not issue_number:
            logger.info(
                "GitHub disabled — would comment on #%s: %s",
                issue_number, body[:80],
            )
            return {}
        r = self._client.post(
            f"{self.base_url}/repos/{self.repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        if r.status_code >= 400:
            raise GitHubAPIError(f"comment failed: {r.status_code} {r.text}")
        return r.json()

    def close(self) -> None:
        self._client.close()


def issue_body_for_finding(finding: dict[str, Any]) -> str:
    """Render a structured issue body that's also a clear prompt for Devin."""
    return f"""## Security finding: {finding.get('cve_id', 'N/A')}

**Package:** `{finding['package']}`
**Current version:** `{finding.get('current_version', 'unknown')}`
**Fixed version:** `{finding.get('fixed_version', 'unknown')}`
**Severity:** {finding.get('severity', 'UNKNOWN')}
**Source:** {finding.get('source', 'scanner')}

### Description
{finding.get('description', 'No description provided.')}

### Remediation requested
Upgrade `{finding['package']}` from `{finding.get('current_version')}` \
to `{finding.get('fixed_version')}` (or latest compatible version). \
Resolve any breaking changes, ensure the test suite passes, and open a PR.

---
_This issue was filed automatically by the Devin CVE Remediation orchestrator. \
A Devin session will be spawned to remediate it; updates will be posted here._
"""
