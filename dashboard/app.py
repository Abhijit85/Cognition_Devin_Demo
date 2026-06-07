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
import altair as alt
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
SELECTED_ISSUES = {
    int(value.strip())
    for value in os.environ.get("SELECTED_ISSUE_NUMBERS", "1,3,4").split(",")
    if value.strip()
}


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


def add_issue_number(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "github_issue_url" not in frame.columns:
        return frame

    result = frame.copy()
    result["issue_number"] = (
        result["github_issue_url"]
        .fillna("")
        .astype(str)
        .str.rstrip("/")
        .str.extract(r"/issues/(\d+)$")[0]
    )
    result["issue_number"] = pd.to_numeric(
        result["issue_number"], errors="coerce",
    ).astype("Int64")
    return result


def scoped_data(
    findings: pd.DataFrame,
    sessions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    findings = add_issue_number(findings)
    sessions = add_issue_number(sessions)

    real_findings = findings
    if "github_issue_url" in real_findings.columns:
        real_findings = real_findings[
            real_findings["github_issue_url"].fillna("").astype(str) != ""
        ]

    real_sessions = sessions
    if "devin_session_id" in real_sessions.columns:
        real_sessions = real_sessions[
            ~real_sessions["devin_session_id"].astype(str).str.startswith("devin-mock")
        ]
    if "github_issue_url" in real_sessions.columns:
        real_sessions = real_sessions[
            real_sessions["github_issue_url"].fillna("").astype(str) != ""
        ]

    selected_findings = real_findings[
        real_findings["issue_number"].isin(SELECTED_ISSUES)
    ]
    selected_sessions = real_sessions[
        real_sessions["issue_number"].isin(SELECTED_ISSUES)
    ]
    return real_findings, real_sessions, selected_findings, selected_sessions


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


def render_metrics(
    real_findings: pd.DataFrame,
    selected_findings: pd.DataFrame,
    selected_sessions: pd.DataFrame,
) -> None:
    selected_total = len(selected_findings)
    deferred = int((real_findings["status"] == "deferred").sum())
    in_progress = int((selected_findings["status"] == "in_progress").sum())
    pr_open = int((selected_findings["status"] == "pr_open").sum())
    failed = int((selected_findings["status"] == "failed").sum())
    sessions_total = len(selected_sessions)

    gross_savings = pr_open * DEV_HOURS_PER_CVE_BASELINE * DEV_HOURLY_RATE
    estimated_acu_per_session = 2.0
    cost = sessions_total * estimated_acu_per_session * ACU_COST
    net_savings = gross_savings - cost

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selected findings", selected_total)
    c2.metric("Deferred evidence", deferred)
    c3.metric("Selected PRs open", pr_open, delta=f"{in_progress} in flight")
    c4.metric(
        "Net $ saved",
        f"${net_savings:,.0f}",
        delta=f"-${cost:,.0f} ACU cost",
        delta_color="off",
    )


def render_funnel(
    real_findings: pd.DataFrame,
    selected_findings: pd.DataFrame,
    selected_sessions: pd.DataFrame,
) -> None:
    pr_open = int((selected_findings["status"] == "pr_open").sum())
    deferred = int((real_findings["status"] == "deferred").sum())
    funnel_data = pd.DataFrame({
        "stage": [
            "Selected",
            "Sessions spawned",
            "PRs open",
            "Deferred scan evidence",
        ],
        "count": [
            len(selected_findings),
            len(selected_sessions),
            pr_open,
            deferred,
        ],
    })
    st.subheader("Curated remediation funnel")
    chart = (
        alt.Chart(funnel_data)
        .mark_bar()
        .encode(
            x=alt.X(
                "stage:N",
                sort=funnel_data["stage"].tolist(),
                title=None,
                axis=alt.Axis(labelAngle=0),
            ),
            y=alt.Y("count:Q", title=None),
            tooltip=["stage", "count"],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def render_sessions(sessions: pd.DataFrame) -> None:
    st.subheader("Selected Devin PRs")
    if sessions.empty:
        st.write("_No sessions yet._")
        return

    columns = [
        "issue_number",
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
    if "pr_url" in display.columns and "status" in display.columns:
        display.loc[display["pr_url"].fillna("").astype(str) != "", "status"] = "pr_open"
    display = display.rename(columns={
        "issue_number": "Issue",
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
    st.caption("Curated Apache Superset dependency remediation powered by Devin")

    findings, sessions, runs, api_available = load_state()
    real_findings, real_sessions, selected_findings, selected_sessions = scoped_data(
        findings, sessions,
    )
    render_controls(api_available)

    if real_findings.empty:
        render_empty_state(api_available)
        return

    st.caption(
        "Selected scope: Flask, PyArrow, and PyJWT. Lower-signal scan findings are retained as deferred evidence."
    )
    render_metrics(real_findings, selected_findings, selected_sessions)
    st.divider()
    render_funnel(real_findings, selected_findings, selected_sessions)
    st.divider()
    render_sessions(selected_sessions)
    st.divider()
    render_consumption(real_sessions)
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
