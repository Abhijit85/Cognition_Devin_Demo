# Superset Remediation Issue Set

Selected use case: remediate known Python dependency vulnerabilities in Apache Superset.

Source repository: `https://github.com/apache/superset`

Configured fork target: `Abhijit85/superset`

Local scan path: `./superset`

## Curated Demo Scope

The active Devin remediation demo focuses on three high-value issues:

1. `https://github.com/Abhijit85/superset/issues/1` - Flask
   - Why selected: core web framework dependency with broad request-handling impact.
   - Devin PR: `https://github.com/Abhijit85/superset/pull/20`
2. `https://github.com/Abhijit85/superset/issues/3` - PyArrow
   - Why selected: data-plane dependency used around analytics serialization and interchange.
   - Devin PR: `https://github.com/Abhijit85/superset/pull/19`
3. `https://github.com/Abhijit85/superset/issues/4` - PyJWT
   - Why selected: authentication/token dependency. The `2.13.0` bump should also cover the related PyJWT CVE cluster.
   - Devin PR: `https://github.com/Abhijit85/superset/pull/18`

The remaining findings are retained as scan evidence but deferred from the active demo. This keeps the story focused on meaningful application risk instead of spending Devin cycles on toolchain-only or lower-signal dependency findings.

## Status

The fork exists at `https://github.com/Abhijit85/superset`, and the local checkout points at that fork.

Issues are enabled on the fork. The selected issues are labeled `demo-selected` and `deep-importance`; deferred issues are labeled `demo-deferred`.

The selected findings are now `pr_open` in the orchestrator database:

- PyJWT: `https://github.com/Abhijit85/superset/pull/18`
- PyArrow: `https://github.com/Abhijit85/superset/pull/19`
- Flask: `https://github.com/Abhijit85/superset/pull/20`

To re-apply curation or resume the selected sessions:

```bash
set -a; source .env; set +a; .venv/bin/python scripts/curate_selected_issues.py
```

Then run the poller until PR URLs appear:

```bash
set -a; source .env; set +a; .venv/bin/python -c 'from orchestrator.poller import poll_once; poll_once()'
```

## Scan Evidence

1. `[UNKNOWN] CVE-2026-27205 in flask`
   - Issue: `https://github.com/Abhijit85/superset/issues/1`
   - Package: `flask`
   - Current version: `2.3.3`
   - Fixed version: `3.1.3`
   - Source: `pip-audit`
   - Demo status: selected

2. `[UNKNOWN] CVE-2026-44405 in paramiko`
   - Issue: `https://github.com/Abhijit85/superset/issues/2`
   - Package: `paramiko`
   - Current version: `3.5.1`
   - Fixed version: unavailable from scanner
   - Source: `pip-audit`
   - Demo status: deferred; no scanner-provided fixed version

3. `[UNKNOWN] CVE-2026-25087 in pyarrow`
   - Issue: `https://github.com/Abhijit85/superset/issues/3`
   - Package: `pyarrow`
   - Current version: `20.0.0`
   - Fixed version: `23.0.1`
   - Source: `pip-audit`
   - Demo status: selected

4. `[UNKNOWN] CVE-2026-48522 in pyjwt`
   - Issue: `https://github.com/Abhijit85/superset/issues/4`
   - Package: `pyjwt`
   - Current version: `2.12.0`
   - Fixed version: `2.13.0`
   - Source: `pip-audit`
   - Demo status: selected; represents the PyJWT CVE cluster

5. `[UNKNOWN] CVE-2026-48523 in pyjwt`
   - Issue: `https://github.com/Abhijit85/superset/issues/5`
   - Package: `pyjwt`
   - Current version: `2.12.0`
   - Fixed version: `2.12.1`
   - Source: `pip-audit`
   - Demo status: deferred; covered by the selected PyJWT dependency bump

6. `[UNKNOWN] CVE-2026-48524 in pyjwt`
   - Issue: `https://github.com/Abhijit85/superset/issues/6`
   - Package: `pyjwt`
   - Current version: `2.12.0`
   - Fixed version: `2.13.0`
   - Source: `pip-audit`
   - Demo status: deferred; covered by the selected PyJWT dependency bump

7. `[UNKNOWN] CVE-2026-48525 in pyjwt`
   - Issue: `https://github.com/Abhijit85/superset/issues/7`
   - Package: `pyjwt`
   - Current version: `2.12.0`
   - Fixed version: `2.13.0`
   - Source: `pip-audit`
   - Demo status: deferred; covered by the selected PyJWT dependency bump

8. `[UNKNOWN] CVE-2026-48526 in pyjwt`
   - Issue: `https://github.com/Abhijit85/superset/issues/8`
   - Package: `pyjwt`
   - Current version: `2.12.0`
   - Fixed version: `2.13.0`
   - Source: `pip-audit`
   - Demo status: deferred; covered by the selected PyJWT dependency bump

9. `[UNKNOWN] CVE-2026-23949 in jaraco-context`
   - Issue: `https://github.com/Abhijit85/superset/issues/9`
   - Package: `jaraco-context`
   - Current version: `6.0.1`
   - Fixed version: `6.1.0`
   - Source: `pip-audit`
   - Demo status: deferred

10. `[UNKNOWN] CVE-2026-8643 in pip`
    - Issue: `https://github.com/Abhijit85/superset/issues/10`
    - Package: `pip`
    - Current version: `25.1.1`
    - Fixed version: `26.1.2`
    - Source: `pip-audit`
    - Demo status: deferred; toolchain-only finding

11. `[UNKNOWN] CVE-2025-8869 in pip`
    - Issue: `https://github.com/Abhijit85/superset/issues/11`
    - Package: `pip`
    - Current version: `25.1.1`
    - Fixed version: `25.3`
    - Source: `pip-audit`
    - Demo status: deferred; toolchain-only finding

12. `[UNKNOWN] CVE-2026-3219 in pip`
    - Issue: `https://github.com/Abhijit85/superset/issues/12`
    - Package: `pip`
    - Current version: `25.1.1`
    - Fixed version: `26.1`
    - Source: `pip-audit`
    - Demo status: deferred; toolchain-only finding

13. `[UNKNOWN] CVE-2026-1703 in pip`
    - Issue: `https://github.com/Abhijit85/superset/issues/13`
    - Package: `pip`
    - Current version: `25.1.1`
    - Fixed version: `26.0`
    - Source: `pip-audit`
    - Demo status: deferred; toolchain-only finding

14. `[UNKNOWN] CVE-2026-6357 in pip`
    - Issue: `https://github.com/Abhijit85/superset/issues/14`
    - Package: `pip`
    - Current version: `25.1.1`
    - Fixed version: `26.1`
    - Source: `pip-audit`
    - Demo status: deferred; toolchain-only finding

15. `[UNKNOWN] CVE-2025-71176 in pytest`
    - Issue: `https://github.com/Abhijit85/superset/issues/15`
    - Package: `pytest`
    - Current version: `7.4.4`
    - Fixed version: `9.0.3`
    - Source: `pip-audit`
    - Demo status: deferred; test-only dependency

16. `[UNKNOWN] CVE-2026-48710 in starlette`
    - Issue: `https://github.com/Abhijit85/superset/issues/16`
    - Package: `starlette`
    - Current version: `0.49.1`
    - Fixed version: `1.0.1`
    - Source: `pip-audit`
    - Demo status: deferred; lower confidence for Superset's Flask-based runtime path
