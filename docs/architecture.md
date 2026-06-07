# Architecture

## System diagram

```
   ┌────────────────────────────────────────────────────────────────┐
   │                       EVENT SOURCES                            │
   │                                                                │
   │  GitHub Action (cron)        GitHub Webhook         Manual    │
   │  .github/workflows/          (issue labeled         (curl /   │
   │   nightly-scan.yml           devin-remediate)       script)   │
   │       │                            │                  │       │
   └───────┼────────────────────────────┼──────────────────┼───────┘
           │ POST /scan/run             │ POST /github/    │ POST  │
           ▼                            ▼   webhook        ▼       │
   ┌──────────────────────────────────────────────────────────────┐
   │                    ORCHESTRATOR (FastAPI)                    │
   │                                                              │
   │  ┌────────────┐  ┌────────────┐  ┌─────────────────────┐    │
   │  │ scanner.py │  │  main.py   │  │   poller.py         │    │
   │  │ pip-audit  │─▶│ endpoints  │◀─│ asyncio task,       │    │
   │  │ + fixtures │  │ + workflow │  │ runs every POLL_    │    │
   │  └────────────┘  └─────┬──────┘  │ INTERVAL seconds    │    │
   │                        │         └──────────┬──────────┘    │
   │                        │                    │               │
   │                        ▼                    ▼               │
   │              ┌───────────────────────────────────┐          │
   │              │      db.py (SQLite at /data)      │          │
   │              │  findings · sessions · runs       │          │
   │              └───────────────────────────────────┘          │
   │                        │                    │               │
   │                        ▼                    ▼               │
   │              ┌────────────────┐  ┌────────────────────┐    │
   │              │ devin_client   │  │  github_client     │    │
   │              │  (v3 API)      │  │  (issues, comments)│    │
   │              └────────┬───────┘  └──────────┬─────────┘    │
   └───────────────────────┼─────────────────────┼───────────────┘
                           │                     │
                           ▼                     ▼
                ┌──────────────────┐  ┌──────────────────────┐
                │     DEVIN        │  │      GITHUB          │
                │                  │  │                      │
                │ POST /sessions   │  │ POST /issues         │
                │ GET  /sessions/  │  │ POST /issues/N/      │
                │       {id}      │  │   comments          │
                │ POST /playbooks  │  │                      │
                │ GET  /metrics/*  │  │ apache/superset      │
                │ GET  /consumption│  │  (your fork)         │
                └────────┬─────────┘  └──────────────────────┘
                         │
                         │ executes Playbook,
                         │ produces PR
                         ▼
                ┌──────────────────┐
                │  Pull Request    │ ──▶ Human review & merge
                │  on superset fork│
                └──────────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │                    DASHBOARD (Streamlit :8501)               │
   │                                                              │
   │  Reads from BOTH:                                            │
   │    • SQLite (workflow context: issue ↔ session ↔ PR)         │
   │    • Devin Metrics API (canonical: ACU, session counts)      │
   │                                                              │
   │  Renders: 4 headline metrics, funnel, in-flight table,       │
   │  ACU consumption chart, scan history.                        │
   └──────────────────────────────────────────────────────────────┘
```

## Sequence: from CVE discovery to merged PR

```
GH Action       Orchestrator      Devin            GitHub
   │                 │              │                │
   │─POST /scan/run─▶│              │                │
   │                 │              │                │
   │            scanner.py runs     │                │
   │            pip-audit on        │                │
   │            mounted repo        │                │
   │                 │              │                │
   │            for each finding:   │                │
   │                 │──POST /issues───────────────▶│
   │                 │◀─{issue_url, number}─────────│
   │                 │              │                │
   │                 │─POST /sessions──▶            │
   │                 │  (prompt = playbook + finding)│
   │                 │◀─{session_id, url, running}─│
   │                 │              │                │
   │                 │──POST /issues/N/comments────▶│
   │                 │   "Devin session started"    │
   │                 │              │                │
   │                 │              │ Devin works... │
   │                 │              │  reads issue,  │
   │                 │              │  bumps dep,    │
   │                 │              │  runs tests,   │
   │                 │              │  opens PR ────▶│
   │                 │              │                │
   │           poller.py (30s)      │                │
   │                 │─GET /sessions/{id}──▶        │
   │                 │◀─{status: exit, pr_url}──────│
   │                 │              │                │
   │                 │──POST /issues/N/comments────▶│
   │                 │   "✅ PR opened: …"          │
   │                 │              │                │
   │            DB updated:         │                │
   │            finding.status      │                │
   │              = pr_open         │                │
```

## Why this shape

**Stateless workers, stateful orchestrator.**
Devin sessions are ephemeral; the orchestrator holds the workflow state
that connects scan → issue → session → PR. The orchestrator is the
durable component, but it's small (~500 LOC) because Devin does the
hard work.

**Two sources of truth, by design.**
The dashboard pulls from both SQLite *and* Devin's Metrics API.
SQLite knows about the workflow (which issue spawned which session);
Devin knows the canonical facts (ACU spent, PR opened, session status).
This mirrors how a real partner deployment would split responsibilities
and prevents the orchestrator from re-implementing observability that
already exists in Devin.

**Polling, not webhooks (from Devin).**
We poll Devin every 30s for active sessions rather than depending on
Devin → orchestrator webhooks. Idempotent, easy to debug, survives
restarts. When first-class session-completed webhooks ship this becomes
two lines of code.

**Tags are the contract.**
Every session is tagged with `cve-remediation`, severity, package, and
source. This lets the dashboard slice by any dimension and, more
importantly, lets the partner's billing system attribute consumption to
specific customers / engagements / SOWs.

## Failure modes & handling

| Failure | Detection | Handling |
|---|---|---|
| Devin API 5xx on session create | `DevinAPIError` | Finding marked `failed`; logged; retry on next scan |
| Devin session ends in `error` | Poller sees `status=error` | Finding marked `failed`; GH issue gets ❌ comment |
| GitHub API rate-limited | 429 from `github_client` | Finding still gets a session; GH comments skipped |
| Scanner crashes | Try/except in `scan_repo` | Falls back to fixture findings; logged |
| Orchestrator restart | SQLite is volume-mounted | State preserved; poller resumes; no duplicate sessions |
| pip-audit unavailable | `FileNotFoundError` | Fixture findings; logged warning |
