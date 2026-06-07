"""
SQLite state for the orchestrator.

We track:
  - findings: discovered CVEs / dependency issues (from scanners or webhooks)
  - sessions: Devin sessions spawned to remediate findings
  - runs:     scheduled scan invocations (for the throughput chart)

Why SQLite: the orchestrator is intentionally lightweight. A real partner
deployment would swap this for Postgres + Alembic, but SQLite keeps the
demo to one container.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(os.environ.get("DATABASE_PATH", "/data/orchestrator.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT UNIQUE NOT NULL,   -- dedupe key: e.g. "CVE-2024-1234:requests"
    cve_id TEXT,
    package TEXT NOT NULL,
    current_version TEXT,
    fixed_version TEXT,
    severity TEXT,
    source TEXT,                        -- "pip-audit" | "trivy" | "webhook" | "manual"
    github_issue_number INTEGER,
    github_issue_url TEXT,
    discovered_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' -- open | in_progress | pr_open | merged | failed
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL,
    devin_session_id TEXT UNIQUE NOT NULL,
    devin_session_url TEXT,
    status TEXT NOT NULL,               -- running | exit | error | suspended
    pr_url TEXT,
    created_at TEXT NOT NULL,
    last_polled_at TEXT,
    completed_at TEXT,
    tags TEXT,                          -- JSON list as string
    FOREIGN KEY (finding_id) REFERENCES findings(id)
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,        -- uuid per scan invocation
    trigger TEXT NOT NULL,              -- "scheduled" | "webhook" | "manual"
    started_at TEXT NOT NULL,
    finished_at TEXT,
    findings_count INTEGER DEFAULT 0,
    sessions_spawned INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA)


# ---------- findings ----------

def upsert_finding(
    fingerprint: str,
    cve_id: str | None,
    package: str,
    current_version: str | None,
    fixed_version: str | None,
    severity: str | None,
    source: str,
    github_issue_number: int | None = None,
    github_issue_url: str | None = None,
) -> dict[str, Any]:
    """Insert finding if not seen before; return the row."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM findings WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        if existing:
            return dict(existing)
        cur = conn.execute(
            """INSERT INTO findings
               (fingerprint, cve_id, package, current_version, fixed_version,
                severity, source, github_issue_number, github_issue_url,
                discovered_at, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fingerprint, cve_id, package, current_version, fixed_version,
                severity, source, github_issue_number, github_issue_url,
                now_iso(), "open",
            ),
        )
        finding_id = cur.lastrowid
        return dict(
            conn.execute(
                "SELECT * FROM findings WHERE id = ?", (finding_id,)
            ).fetchone()
        )


def update_finding_status(finding_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE findings SET status = ? WHERE id = ?",
            (status, finding_id),
        )


def list_findings(status: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM findings WHERE status = ? ORDER BY discovered_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM findings ORDER BY discovered_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


# ---------- sessions ----------

def record_session(
    finding_id: int,
    devin_session_id: str,
    devin_session_url: str,
    status: str,
    tags: list[str] | None = None,
) -> None:
    import json
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO sessions
               (finding_id, devin_session_id, devin_session_url, status,
                created_at, tags)
               VALUES (?,?,?,?,?,?)""",
            (
                finding_id, devin_session_id, devin_session_url, status,
                now_iso(), json.dumps(tags or []),
            ),
        )


def update_session(
    devin_session_id: str,
    status: str | None = None,
    pr_url: str | None = None,
) -> None:
    fields, values = [], []
    if status is not None:
        fields.append("status = ?")
        values.append(status)
        if status in {"exit", "error"}:
            fields.append("completed_at = ?")
            values.append(now_iso())
    if pr_url is not None:
        fields.append("pr_url = ?")
        values.append(pr_url)
    fields.append("last_polled_at = ?")
    values.append(now_iso())
    values.append(devin_session_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE sessions SET {', '.join(fields)} WHERE devin_session_id = ?",
            values,
        )


def list_sessions(status: str | None = None) -> list[dict[str, Any]]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def list_active_sessions() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE status IN ('new', 'running', 'suspended')"
        ).fetchall()
        return [dict(r) for r in rows]


def get_sessions_with_findings() -> list[dict[str, Any]]:
    """Join for the dashboard."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT s.*, f.cve_id, f.package, f.severity, f.github_issue_url
               FROM sessions s
               JOIN findings f ON s.finding_id = f.id
               ORDER BY s.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- runs ----------

def start_run(run_id: str, trigger: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO runs (run_id, trigger, started_at) VALUES (?,?,?)",
            (run_id, trigger, now_iso()),
        )


def finish_run(run_id: str, findings_count: int, sessions_spawned: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE runs SET finished_at = ?, findings_count = ?,
               sessions_spawned = ? WHERE run_id = ?""",
            (now_iso(), findings_count, sessions_spawned, run_id),
        )


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
