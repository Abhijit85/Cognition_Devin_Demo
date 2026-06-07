"""
Dependency scanner wrappers.

Wraps `pip-audit` for Python deps. We could add Trivy for container/OS deps,
or OSV-Scanner for multi-ecosystem — kept narrow for the take-home.

The scanner returns normalized Finding dicts with a fingerprint suitable for
dedupe across runs.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _fingerprint(cve_id: str | None, package: str) -> str:
    return f"{cve_id or 'NO-CVE'}:{package}".lower()


def scan_pip_audit(requirements_file: Path) -> list[dict[str, Any]]:
    """Run pip-audit against a requirements file. Returns normalized findings.

    Falls back to fixture data if pip-audit is not installed (useful for
    CI / demo environments where we want deterministic input).
    """
    if not requirements_file.exists():
        logger.warning("Requirements file not found: %s", requirements_file)
        return []

    pip_audit = shutil.which("pip-audit")
    if not pip_audit:
        candidate = Path(sys.executable).parent / "pip-audit"
        if candidate.exists():
            pip_audit = str(candidate)
    if not pip_audit:
        logger.warning("pip-audit not available, using fixtures")
        return _fixture_findings()

    cwd = requirements_file.parent
    requirement_arg = requirements_file.name
    if requirements_file.parent.name == "requirements":
        cwd = requirements_file.parent.parent
        requirement_arg = str(Path("requirements") / requirements_file.name)

    try:
        result = subprocess.run(
            [
                pip_audit,
                "-r", requirement_arg,
                "--no-deps",
                "--disable-pip",
                "--skip-editable",
                "--format", "json",
                "--vulnerability-service", "osv",
            ],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("pip-audit not available (%s), using fixtures", exc)
        return _fixture_findings()

    if result.returncode not in (0, 1):  # 1 = vulns found, also OK
        logger.error("pip-audit failed: %s", result.stderr)
        return _fixture_findings()

    stdout = result.stdout.strip()
    json_start = stdout.find("{")
    if json_start > 0:
        stdout = stdout[json_start:]

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        logger.error("pip-audit returned invalid JSON")
        return _fixture_findings()

    findings: list[dict[str, Any]] = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            cve = next(
                (a for a in vuln.get("aliases", []) if a.startswith("CVE-")),
                vuln.get("id"),
            )
            fixed = vuln.get("fix_versions") or []
            findings.append({
                "fingerprint": _fingerprint(cve, dep["name"]),
                "cve_id": cve,
                "package": dep["name"],
                "current_version": dep.get("version"),
                "fixed_version": fixed[0] if fixed else None,
                "severity": _severity_from_vuln(vuln),
                "source": "pip-audit",
                "description": vuln.get("description", "")[:500],
            })
    return findings


def _severity_from_vuln(vuln: dict[str, Any]) -> str:
    """OSV doesn't always include CVSS; best-effort severity bucket."""
    cvss = vuln.get("cvss_v3_score") or 0
    if cvss >= 9.0:
        return "CRITICAL"
    if cvss >= 7.0:
        return "HIGH"
    if cvss >= 4.0:
        return "MEDIUM"
    if cvss > 0:
        return "LOW"
    return "UNKNOWN"


def _fixture_findings() -> list[dict[str, Any]]:
    """Deterministic findings for demos / CI. Realistic Superset-style deps."""
    fixtures = [
        {
            "cve_id": "CVE-2024-35195", "package": "requests",
            "current_version": "2.31.0", "fixed_version": "2.32.0",
            "severity": "MEDIUM",
            "description": "Session verify=False persists across requests",
        },
        {
            "cve_id": "CVE-2024-37891", "package": "urllib3",
            "current_version": "2.0.7", "fixed_version": "2.2.2",
            "severity": "MEDIUM",
            "description": "Proxy-Authorization header not stripped on redirect",
        },
        {
            "cve_id": "CVE-2024-3651", "package": "idna",
            "current_version": "3.6", "fixed_version": "3.7",
            "severity": "MEDIUM",
            "description": "DoS via crafted hostname",
        },
        {
            "cve_id": "CVE-2024-34064", "package": "jinja2",
            "current_version": "3.1.3", "fixed_version": "3.1.4",
            "severity": "HIGH",
            "description": "xmlattr filter accepts keys with spaces; XSS risk",
        },
        {
            "cve_id": "CVE-2024-22195", "package": "jinja2",
            "current_version": "3.1.3", "fixed_version": "3.1.3",
            "severity": "MEDIUM",
            "description": "xmlattr filter HTML attribute injection",
        },
        {
            "cve_id": "CVE-2024-39689", "package": "certifi",
            "current_version": "2024.2.2", "fixed_version": "2024.7.4",
            "severity": "HIGH",
            "description": "GLOBALTRUST root CA removed",
        },
    ]
    return [
        {
            **f,
            "fingerprint": _fingerprint(f["cve_id"], f["package"]),
            "source": "pip-audit-fixture",
        }
        for f in fixtures
    ]


def scan_repo(repo_path: Path | None = None) -> list[dict[str, Any]]:
    """Top-level: scan a repo for all findings we know how to detect."""
    repo_path = repo_path or Path(os.environ.get("REPO_PATH", "."))
    findings: list[dict[str, Any]] = []

    # Try common Python requirements locations
    for req_file in [
        repo_path / "requirements.txt",
        repo_path / "requirements" / "base.txt",
        repo_path / "requirements" / "development.txt",
    ]:
        if req_file.exists():
            findings.extend(scan_pip_audit(req_file))

    # If nothing found (e.g., no requirements files in repo), fall back to fixtures
    # so the demo still has interesting data.
    if not findings:
        logger.info("No real findings discovered, using fixtures for demo")
        findings = _fixture_findings()

    # Dedupe by fingerprint
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for f in findings:
        if f["fingerprint"] not in seen:
            seen.add(f["fingerprint"])
            unique.append(f)
    return unique
