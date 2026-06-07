# Demo Evidence

This file captures the externally visible proof that the orchestrator ran against a real Apache Superset fork and that Devin produced remediation PRs.

## Repositories

- Orchestrator: `https://github.com/Abhijit85/Cognition_Devin_Demo`
- Apache Superset fork: `https://github.com/Abhijit85/superset`
- Source upstream: `https://github.com/apache/superset`

## Dashboard

![Populated Devin CVE Remediation dashboard](screenshots/dashboard.png)

The dashboard screenshot is intentionally committed because `http://localhost:8501` only resolves on the machine running Streamlit.

## Selected Remediations

| Issue | Package | CVE | Devin session | PR |
|---|---|---|---|---|
| [`#1`](https://github.com/Abhijit85/superset/issues/1) | Flask | CVE-2026-27205 | [`a4e16e...`](https://app.devin.ai/sessions/a4e16eecda5547179937e01acfe84396) | [`#20`](https://github.com/Abhijit85/superset/pull/20) |
| [`#3`](https://github.com/Abhijit85/superset/issues/3) | PyArrow | CVE-2026-25087 | [`05d7c4...`](https://app.devin.ai/sessions/05d7c42c569548c0bf234f21a16bd28f) | [`#19`](https://github.com/Abhijit85/superset/pull/19) |
| [`#4`](https://github.com/Abhijit85/superset/issues/4) | PyJWT | CVE-2026-48522 | [`23df54...`](https://app.devin.ai/sessions/23df54a6837945feac34818bb563e2e7) | [`#18`](https://github.com/Abhijit85/superset/pull/18) |

## Scope Rationale

The active demo uses three high-signal findings:

- Flask: core web framework dependency.
- PyArrow: data-plane serialization and interchange dependency.
- PyJWT: authentication/token dependency; the selected bump covers the related PyJWT CVE cluster.

The other scanner findings remain in the Superset fork as evidence, but are labeled `demo-deferred` so the demo does not spend Devin cycles on toolchain-only or lower-confidence findings.

## Local Verification

```bash
DEVIN_MOCK=1 DEVIN_ORG_ID=test .venv/bin/pytest tests/ -v
```

Current result: `6 passed`.
