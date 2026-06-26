# Sonar Follow-Up Action Items

Source report: `sonar-vulnerabilities.json` / `sonar-vulnerabilities.csv`

Scope note: this file summarizes the downloaded Sonar vulnerability export only. The current local report does not include the full reliability or maintainability issue export.

## Current Assessment

The vulnerability report does not show the project in a dangerous production-security state.

The export contains 82 open vulnerability findings:

- 1 production-code finding in `siem_backend.py`
- 81 test-only findings in `tests/`
- 72 `python:S2068` hardcoded credential keyword findings
- 10 `python:S6437` compromised-password literal findings

The production-code item was the Flask secret-key configuration warning in `siem_backend.py`. That has now been addressed with production fail-fast behavior when `SIEM_SECRET_KEY` / `SECRET_KEY` is missing.

## Items Already Addressed

### Production Flask Secret Key Guard

- File: `siem_backend.py`
- Sonar rule: `python:S2068`
- Original finding: `"SECRET_KEY" detected here, review this potentially hard-coded credential.`
- Assessment: low-risk production hardening item, not an actual leaked secret
- Status: fixed locally
- Result: production-like startup now raises a clear `RuntimeError` if no configured Flask secret key exists

## Remaining Findings That Do Not Need Code Fixes

These are test-only fake credentials used to exercise authentication/RBAC paths. They are not production secrets and should not trigger broad refactors.

Recommended handling in Sonar:

- Mark as false-positive or won't-fix with a comment such as:
  `Test-only credential literals used for isolated authentication/RBAC fixtures; no production secret is present.`

### Test Files With Findings

| File | Count | Notes |
| --- | ---: | --- |
| `tests/test_playbook_routes.py` | 14 | Test login/password fixture data |
| `tests/test_metrics_routes.py` | 10 | Test auth fixture payloads |
| `tests/test_playbook_metrics_routes.py` | 9 | Test auth fixture payloads |
| `tests/test_incident_routes.py` | 9 | Test auth fixture payloads |
| `tests/test_approval_routes.py` | 6 | Test auth fixture payloads |
| `tests/test_dead_letter_routes.py` | 5 | Test auth fixture payloads |
| `tests/test_integration_routes.py` | 5 | Test auth fixture payloads |
| `tests/test_auth_rbac.py` | 5 | Test auth/RBAC credential paths |
| `tests/test_notification_delivery_metrics_routes.py` | 3 | Test auth fixture payloads |
| `tests/test_notification_delivery_routes.py` | 3 | Test auth fixture payloads |
| `tests/test_soar_worker_admin_run_control.py` | 3 | Test fake viewer/analyst credentials |
| `tests/test_admin_api_contracts.py` | 3 | Test fake viewer/analyst credentials |
| `tests/test_soar_queue_visibility_api.py` | 2 | Test fake viewer/analyst credentials |
| `tests/test_backfill_reputation_api_contracts.py` | 2 | Test fake auth data |
| `tests/test_integration_adapters.py` | 1 | Test adapter credential fixture |
| `tests/test_playbook_step_executor.py` | 1 | Test adapter credential fixture |

## Optional Low-Risk Cleanup

These are optional hygiene changes only. They are not required for production safety.

### Centralize Test Credential Constants

Potentially safe cleanup:

- Create shared test constants for fake passwords, for example in `tests/conftest.py`
- Replace repeated literals like `viewerpass`, `analystpass`, and intentionally bad passwords with named constants
- Keep the constants clearly labeled as test-only

Risk:

- Low, but touches many tests
- Not worth doing unless the goal is reducing Sonar noise rather than improving actual security

### Sonar Exclusion for Test Credentials

Potentially safer than editing many tests:

- Configure Sonar to ignore `python:S2068` / `python:S6437` under `tests/**`
- Or mark the current test-only findings false-positive/won't-fix in SonarCloud

Risk:

- Low
- Avoids churn in stable test files

## Items That Should Not Trigger Refactors

Do not refactor these areas just to satisfy the current vulnerability export:

- SOAR worker lease/recovery logic
- Playbook execution paths
- Approval workflows
- Dead-letter storage/retry logic
- Queue semantics
- Integration guard behavior
- Ingestion or correlation logic
- Frontend UI
- Database schema

The remaining findings are credential-name/literal detection in tests, not evidence of unsafe orchestration behavior.

## Recommended Next Step

Safest next phase:

1. Let Sonar rerun after the `siem_backend.py` secret-key guard change.
2. Confirm the production `SECRET_KEY` finding is gone or no longer materially relevant.
3. Mark the 81 test-only findings as false-positive/won't-fix, or configure Sonar to ignore those rules under `tests/**`.
4. If you want a separate cleanup pass for the dashboard's Reliability/Maintainability counts, export those issue categories separately and audit them before changing code.
