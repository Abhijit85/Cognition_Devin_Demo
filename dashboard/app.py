"""
Streamlit dashboard backed by the FastAPI orchestrator API.

The dashboard calls the orchestrator for health, scans, findings, sessions,
and runs. If the API is unavailable, it falls back to local SQLite reads so
the UI still opens during development.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from orchestrator import db  # noqa: E402
from orchestrator.devin_client import get_client  # noqa: E402

st.set_page_config(
    page_title="Devin CVE Remediation",
    page_icon="Shield",
    layout="wide",
)

ORCHESTRATOR_URL = os.environ.get(
    "ORCHESTRATOR_URL", "http://localhost:8000"
).rstrip("/")
DEV_HOURLY_RATE = float(os.environ.get("DEV_HOURLY_RATE", "150"))
DEV_HOURS_PER_CVE_BASELINE = float(
    os.environ.get("DEV_HOURS_PER_CVE_BASELINE", "4")
)
ACU_COST = float(os.environ.get("ACU_COST", "2.25"))


def api_get(path: str) -> Any:
    response = httpx.get(f"{ORCHESTRATOR_URL}{path}", timeout=5.0)
    response.raise_for_status()
    return response.json()


def api_post(path: str) -> Any:
    response = httpx.post(f"{ORCHESTRATOR_URL}{path}", timeout=10.0)
    response.raise_for_status()
    return response.json()


def load_state() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, bool]:
    try:
        health = api_get("/healthz")
        if health.get("status") != "ok":
            raise RuntimeError(f"unexpected health response: {health}")
        findings = pd.DataFrame(api_get("/findings"))
        sessions = pd.DataFrame(api_get("/sessions"))
        runs = pd.DataFrame(api_get("/runs"))
        return findings, sessions, runs, True
    except Exception:
        db.init_db()
        findings = pd.DataFrame(db.list_findings())
        sessions = pd.DataFrame(db.get_sessions_with_findings())
        runs = pd.DataFrame(db.list_runs())
        return findings, sessions, runs, False


def render_empty_state(api_available: bool) -> None:
    st.info("No findings yet. Trigger a scan from the dashboard or API.")
    if not api_available:
        st.warning(
            f"Orchestrator API unavailable at `{ORCHESTRATOR_URL}`. "
            "Start it with `make api` or `docker compose up --build`."
        )


def render_controls(api_available: bool) -> None:
    c1, c2, c3 = st.columns([1, 1, 4])
    with c1:
        if st.button("Run scan", disabled=not api_available, use_container_width=True):
            try:
                result = api_post("/scan/run")
                st.success(f"Scan started: `{result['run_id']}`")
            except Exception as exc:
                st.error(f"Scan trigger failed: {exc}")
    with c2:
        if st.button("Refresh", use_container_width=True):
            st.rerun()
    with c3:
        status = "connected" if api_available else "local DB fallback"
        st.caption(f"API: `{ORCHESTRATOR_URL}` · {status}")


def render_metrics(findings: pd.DataFrame, sessions: pd.DataFrame) -> None:
    total_findings = len(findings)
    in_progress = int((findings["status"] == "in_progress").sum())
    pr_open = int((findings["status"] == "pr_open").sum())
    failed = int((findings["status"] == "failed").sum())
    sessions_total = len(sessions)

    gross_savings = pr_open * DEV_HOURS_PER_CVE_BASELINE * DEV_HOURLY_RATE
    estimated_acu_per_session = 2.0
    cost = sessions_total * estimated_acu_per_session * ACU_COST
    net_savings = gross_savings - cost

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Findings discovered", total_findings)
    c2.metric("Sessions in flight", in_progress)
    c3.metric("PRs open", pr_open, delta=f"{failed} failed" if failed else None)
    c4.metric(
        "Net $ saved",
        f"${net_savings:,.0f}",
        delta=f"-${cost:,.0f} ACU cost",
        delta_color="off",
    )


def render_funnel(findings: pd.DataFrame, sessions: pd.DataFrame) -> None:
    sessions_done = (
        int((sessions["status"] == "exit").sum()) if not sessions.empty else 0
    )
    pr_open = int((findings["status"] == "pr_open").sum())
    funnel_data = pd.DataFrame({
        "stage": [
            "Discovered",
            "Session spawned",
            "Session completed",
            "PR open",
            "Merged",
        ],
        "count": [len(findings), len(sessions), sessions_done, pr_open, 0],
    })
    st.subheader("Remediation funnel")
    st.bar_chart(funnel_data.set_index("stage"))


def render_sessions(sessions: pd.DataFrame) -> None:
    st.subheader("In-flight work")
    if sessions.empty:
        st.write("_No sessions yet._")
        return

    columns = [
        "devin_session_id",
        "cve_id",
        "package",
        "severity",
        "status",
        "pr_url",
        "devin_session_url",
        "created_at",
    ]
    display = sessions[[c for c in columns if c in sessions.columns]].copy()
    display = display.rename(columns={
        "devin_session_id": "Session",
        "cve_id": "CVE",
        "package": "Package",
        "severity": "Severity",
        "status": "Status",
        "pr_url": "PR",
        "devin_session_url": "Devin URL",
        "created_at": "Created",
    })
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "PR": st.column_config.LinkColumn("PR"),
            "Devin URL": st.column_config.LinkColumn("Devin URL"),
        },
    )


def render_consumption(sessions: pd.DataFrame) -> None:
    st.subheader("ACU consumption")
    try:
        client = get_client()
        end = dt.date.today()
        start = end - dt.timedelta(days=14)
        consumption = client.get_daily_consumption(
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )
        if isinstance(consumption, dict) and "items" in consumption:
            cdf = pd.DataFrame(consumption["items"])
            if not cdf.empty and "date" in cdf.columns:
                cdf["date"] = pd.to_datetime(cdf["date"])
                st.line_chart(cdf.set_index("date"))
                return
        st.json(consumption)
    except Exception as exc:
        st.warning(f"Live ACU metrics unavailable: `{exc}`")
        if not sessions.empty and "created_at" in sessions.columns:
            sessions["created_date"] = pd.to_datetime(
                sessions["created_at"]
            ).dt.date
            counts = sessions.groupby("created_date").size().rename("sessions")
            st.bar_chart(counts)


def render_runs(runs: pd.DataFrame) -> None:
    st.subheader("Scan history")
    if runs.empty:
        st.write("_No scan runs yet._")
        return
    columns = [
        "run_id",
        "trigger",
        "started_at",
        "finished_at",
        "findings_count",
        "sessions_spawned",
    ]
    st.dataframe(
        runs[[c for c in columns if c in runs.columns]],
        use_container_width=True,
        hide_index=True,
    )


def main() -> None:
    st.title("Devin CVE Remediation")
    st.caption("Event-driven dependency remediation pipeline powered by Devin")

    findings, sessions, runs, api_available = load_state()
    render_controls(api_available)

    if findings.empty:
        render_empty_state(api_available)
        return

    render_metrics(findings, sessions)
    st.divider()
    render_funnel(findings, sessions)
    st.divider()
    render_sessions(sessions)
    st.divider()
    render_consumption(sessions)
    st.divider()
    render_runs(runs)

    with st.expander("Cost model assumptions"):
        st.write(f"""
- Baseline developer cost: **${DEV_HOURLY_RATE}/hour** x **{DEV_HOURS_PER_CVE_BASELINE} hours per CVE**
- ACU price: **${ACU_COST}/ACU**, estimated **2.0 ACU/session**
- Configurable via `.env`: `DEV_HOURLY_RATE`, `DEV_HOURS_PER_CVE_BASELINE`, `ACU_COST`.
""")


if __name__ == "__main__":
    main()
